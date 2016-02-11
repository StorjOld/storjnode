import time
import threading
import traceback
import uuid
import hashlib
import zlib
from ast import literal_eval
import storjnode
from storjnode.common import THREAD_SLEEP
from twisted.internet import defer
from collections import OrderedDict
from crochet import wait_for, run_in_reactor
from storjnode import util
from storjnode.util import get_nonce
from storjnode.network.repeat_relay import RepeatRelay
from storjnode.network.message import sign, verify_signature
from storjnode.network.server import Server, QUERY_TIMEOUT, WALK_TIMEOUT
from pyp2p.unl import UNL
from twisted.internet.task import LoopingCall


# File transfer.
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.process_transfers import process_transfers
from storjnode.network.process_transfers import do_upkeep
from storjnode.network.process_transfers import process_dht_messages
from storjnode.network.bandwidth.test import BandwidthTest
from storjnode.network.bandwidth.limit import BandwidthLimit
from storjnode.common import DEFAULT_BOOTSTRAP_NODES
import storjnode.network
from pyp2p.net import Net


_log = storjnode.log.getLogger(__name__)


class Node(object):
    """Storj network layer implementation.

    Provides a blocking dict like interface to the DHT for ease of use.
    """

    def __init__(self,
                 # kademlia DHT args
                 key, ksize=20, port=None,
                 dht_storage=None, max_messages=1024,

                 # data transfer args
                 disable_data_transfer=True,  # FIXME get from config instead
                 config=None,
                 passive_port=None,
                 passive_bind=None,  # FIXME use utils.get_inet_facing_ip ?
                 node_type="unknown",  # FIMME what is this ?
                 nat_type="unknown",  # FIXME what is this ?
                 bandwidth=None,
                 wan_ip=None  # Get it if it isn't set
                 ):
        """Create a blocking storjnode instance.

        Args:
            key (str): Bitcoin wif/hwif for auth, encryption and node id.
            ksize (int): The k parameter from the kademlia paper.
            port (port): Port to for incoming packages, randomly by default.
            dht_storage: implements :interface:`~kademlia.storage.IStorage`
            max_messages (int): Max unprecessed messages, additional dropped.

            disable_data_transfer: Disable data transfer for this node.
            config: Dict of storage paths to optional attributes.
                          limit: The dir size limit in bytes, 0 for no limit.
                          use_folder_tree: Files organized in a folder tree
                                           (always on for fat partitions).

            passive_port (int): Port to receive inbound TCP connections on.
            passive_bind (ip): LAN IP to receive inbound TCP connections on.
            node_type: TODO doc string
            nat_type: TODO doc string
        """

        # config must be givin
        if config is None:
            raise Exception("Config required")
        self.config = config

        self.bandwidth = None
        self.disable_data_transfer = bool(disable_data_transfer)
        self._transfer_request_handlers = set()
        self._transfer_complete_handlers = set()
        self._transfer_start_handlers = set()
        self._data_transfer = None
        self.latency_tests = None

        # validate port (randomish user port by default)
        port = util.get_unused_port(port)
        assert(util.valid_port(port))
        self.port = port

        # passive port (randomish user port by default)
        passive_port = util.get_unused_port(passive_port)
        assert(util.valid_port(passive_port))

        # passive bind
        # FIXME just use storjnode.util.get_inet_facing_ip ?
        passive_bind = passive_bind or "0.0.0.0"
        assert(util.valid_ip(passive_bind))

        # start services
        self._setup_server(key, ksize, dht_storage, max_messages)

        # Process incoming messages.
        self._setup_message_dispatcher()

        # Rebroadcast relay messages.
        self.repeat_relay = RepeatRelay(self)

        if not self.disable_data_transfer:
            self.bandwidth = bandwidth or BandwidthLimit(self.config)
            self._setup_data_transfer_client(
                passive_port, passive_bind, node_type, nat_type, wan_ip
            )
            self.latency_tests = self._data_transfer.latency_tests
            self.bandwidth_test = BandwidthTest(
                self.get_key(), self._data_transfer, self, 1
            )

        _log.info("Started storjnode on port {0} with address {1}".format(
            self.port, self.get_address())
        )

    def _setup_message_dispatcher(self):
        self._message_handlers = set()
        self._message_dispatcher_thread_stop = False
        self._message_dispatcher_thread = threading.Thread(
            target=self._message_dispatcher_loop
        )
        self._message_dispatcher_thread.start()

    def _setup_server(self, key, ksize, storage, max_messages):
        interval = self.config["network"]["refresh_neighbours_interval"]

        bootstrap_nodes = self.config["network"]["bootstrap_nodes"]
        if not bootstrap_nodes:
            bootstrap_nodes = DEFAULT_BOOTSTRAP_NODES  # pragma: no cover

        # make sure transport address is a tuple
        bootstrap_nodes = [(addr[0], addr[1]) for addr in bootstrap_nodes]

        self.server = Server(
            key, self.port, ksize=ksize, storage=storage,
            max_messages=max_messages,
            refresh_neighbours_interval=interval
        )
        port_handler = self.server.listen(self.port)
        self.server.set_port_handler(port_handler)
        self.server.bootstrap(bootstrap_nodes)

    def _setup_data_transfer_client(self, passive_port,
                                    passive_bind, node_type, nat_type, wan_ip):

        # Setup handlers for callbacks registered via the API.
        handlers = {
            "complete": self._transfer_complete_handlers,
            "accept": self._transfer_request_handlers,
            "start": self._transfer_start_handlers
        }

        wif = self.get_key()
        dht_node = self

        self._data_transfer = FileTransfer(
            Net(
                net_type="direct",
                node_type=node_type,
                nat_type=nat_type,
                dht_node=dht_node,
                debug=1,
                passive_port=passive_port,
                passive_bind=passive_bind,
                wan_ip=wan_ip
            ),
            self.bandwidth,
            wif=wif,
            store_config=self.config["storage"],
            handlers=handlers,
            api=self
        )

        # Setup success callback values.
        self._data_transfer.success_value = True
        self.process_data_transfers()

    def stop(self):
        """Stop storj node."""
        self._message_dispatcher_thread_stop = True
        self._message_dispatcher_thread.join()
        self.server.stop()
        self.repeat_relay.stop()
        if not self.disable_data_transfer:
            self._data_transfer.net.stop()

    ##################
    # node interface #
    ##################

    def refresh_neighbours(self):
        self.server.refresh_neighbours()

    def get_known_peers(self):
        """Returns list of know peers.

        Returns: iterable of kademlia.node.Node
        """
        return self.server.get_known_peers()

    def get_neighbours(self):
        return self.server.get_neighbours()

    def get_storage_contents(self):
        """Returns the contents of this nodes DHT storage."""
        return self.server.storage.iteritems()

    def get_key(self):
        """Returns Bitcoin wif for auth, encryption and node id"""
        return self.server.key

    def get_id(self):
        """Returns 160bit node id as bytes."""
        return self.server.get_id()

    def get_address(self):
        return self.server.get_address()

    ########################
    # networking interface #
    ########################

    @wait_for(timeout=QUERY_TIMEOUT)
    def sync_has_public_ip(self):
        """Find out if this node has a public IP or is behind a NAT.

        The may false positive if you run other nodes on your local network.

        Returns:
            True if local IP is internet visible, otherwise False.

        Raises:
            crochet.TimeoutError after storjnode.network.server.QUERY_TIMEOUT
        """
        return self.async_has_public_ip()

    def async_has_public_ip(self):
        """Find out if this node has a public IP or is behind a NAT.

        The may false positive if you run other nodes on your local network.

        Returns:
            A twisted.internet.defer.Deferred that resloves to
            True if local IP is internet visible, otherwise False.
        """

        def on_success(result):
            if result is None:
                return False
            return result["is_public"]

        def on_error(err):
            _log.error(repr(err))
            return err

        deferred = self.async_get_transport_info(add_unl=False)
        return deferred.addCallback(on_success).addErrback(on_error)

    @wait_for(timeout=QUERY_TIMEOUT)
    def sync_get_wan_ip(self):
        """Get the WAN IP of this Node.

        Retruns:
            The WAN IP or None.

        Raises:
            crochet.TimeoutError after storjnode.network.server.QUERY_TIMEOUT
        """
        return self.async_get_wan_ip()

    def async_get_wan_ip(self):
        """Get the WAN IP of this Node.

        Retruns:
            A twisted.internet.defer.Deferred that resloves to
            The WAN IP or None.
        """

        def on_success(result):
            return result["wan"][0]

        def on_error(err):
            _log.error(repr(err))
            return err

        deferred = self.async_get_transport_info(add_unl=False)
        return deferred.addCallback(on_success).addErrback(on_error)

    def async_get_transport_info(self, add_unl=True):
        # FIXME remove add_unl option when data transfer always enabled
        if add_unl:
            return self.server.get_transport_info(unl=self.get_unl())
        return self.server.get_transport_info()

    @wait_for(timeout=QUERY_TIMEOUT)
    def sync_get_transport_info(self, add_unl=True):
        return self.async_get_transport_info(add_unl=add_unl)

    ###########################
    # data transfer interface #
    ###########################

    def get_unl_by_node_id(self, nodeid):
        """Get the WAN IP of this Node.

        Returns:
            A twisted.internet.defer.Deferred that resolves to
            The UNL on success or None.
        """

        # UNL request.
        _log.debug("In get UNL by node id")
        unl_req = OrderedDict([
            (u"type", u"unl_request"),
            (u"nonce", get_nonce()),
            (u"requester", self.get_address())
        ])

        # Sign UNL request.
        unl_req = sign(unl_req, self.get_key())

        # Record start time.
        future_timeout = time.time() + 10

        # Handle responses for this request.
        def handler_builder(self, d, their_node_id, wif):
            def handler(node, msg):
                # Is this a response to our request?
                remove_handler = 0
                try:
                    if type(msg) in [type(b"")]:
                        msg = literal_eval(zlib.decompress(msg))
                    msg = util.list_to_ordered_dict(msg)

                    # Not a response to our request.
                    if msg[u"request"] != unl_req:
                        return

                    # Not a UNL response.
                    if msg[u"type"] != u"unl_response":
                        _log.debug("unl response: type !=")
                        return

                    # Invalid UNL.
                    their_unl = UNL(value=msg[u"unl"]).deconstruct()
                    if their_unl is None:
                        _log.debug("unl response:their unl !=")
                        return

                    # Invalid signature.
                    if not verify_signature(msg, wif, their_node_id):
                        _log.debug("unl response: their sig")
                        return

                    remove_handler = 1

                    # Everything passed: fire callback.
                    d.callback(msg[u"unl"])
                except (ValueError, KeyError):
                    _log.debug("unl response:val or key er")
                    pass  # not a unl response
                finally:
                    if remove_handler:
                        # Remove this callback.
                        node.remove_message_handler(handler)

            return handler

        # Build message handler.
        d = defer.Deferred()
        handler = handler_builder(self, d, nodeid, self.get_key())

        # Expire this request.
        def expire_old_unl_request(node, msg):
            if time.time() >= future_timeout:
                _log.debug("Get unl request timed out")
                node.remove_message_handler(expire_old_unl_request)
                if handler in self._message_handlers:
                    node.remove_message_handler(handler)
                    d.errback(Exception("Get unl request timed out"))

        # Register new handler for this UNL request.
        self.add_message_handler(expire_old_unl_request)
        self.add_message_handler(handler)

        # Send our get UNL request to node.
        msg = util.ordered_dict_to_list(unl_req)
        msg = zlib.compress(str(msg))
        self.repeat_relay_message(nodeid, msg)

        # Return a new deferred.
        return d

    def get_unl(self):
        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")
        return self._data_transfer.net.unl.value

    @run_in_reactor
    def process_data_transfers(self):
        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")

        def process_transfers_error(err):
            txt = "An unknown error occured in process_transfers: %s"
            _log.error(txt % repr(err))
            return err

    def test_bandwidth(self, nodeid):
        """Tests the bandwidth between yourself and a remote peer.
        Only one test can be active at any given time! If a test
        is already active: the deferred will call an errback that
        resolves to an exception (the callback won't be called)
        and the request won't go through.

        :param nodeid: binary nodeid as returned from get_id.
        :return: a deferred that returns this:
        {'download': 1048576, 'upload': 1048576} to a callback
        or raises an error to an errback on failure.

        ^ Note that the units are in bytes so if you
        want fancy measurement in kbs or mbs you will have
        to convert it.

        E.g.:
        def show_bandwidth(results):
            print(results)

        def handle_error(err):
            print(err)
            return err

        d = test_bandwidth ...
        d.addCallback(show_bandwidth).addErrback(handle_error)

        Todo: I am basically coding this function in a hurry so I
        don't delay your work Fabian. There should probably be a
        decorator to wrap functions that need a UNL (as the code
        bellow is similar to the request_data_transfer function.)
        """

        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")

        # Get a deferred for their UNL.
        d = self.get_unl_by_node_id(nodeid)

        # Make data request when we have their UNL.
        def on_success(peer_unl):
            return self.bandwidth_test.start(peer_unl)

        # Add callback to UNL deferred.
        d.addCallback(on_success)

        # Return deferred.
        return d

    def async_request_data_transfer(self, shardid, nodeid, direction):
        """Request data be transfered to or from a peer.

        Args:
            shardid: The sha256 sum of the data to be transfered.
            nodeid: Binary node id of the target to receive message.
            direction: "send" to peer or "receive" from peer

        Returns:
            A twisted.internet.defer.Deferred that resloves to
            own transport address (ip, port) if successfull else None

        Raises:
            RequestDenied: If the peer denied your request to transfer data.
            TransferError: If the data not transfered for other reasons.
        """

        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")

        # Get a deferred for their UNL.
        d = self.get_unl_by_node_id(nodeid)

        # Make data request when we have their UNL.
        def callback_builder(shardid, direction):
            def callback(peer_unl):
                # Deferred.
                return self._data_transfer.simple_data_request(
                    shardid, peer_unl, direction
                )

            return callback

        def on_error(err):
            _log.error(repr(err))
            return err

        # Add callback to UNL deferred.
        on_success = callback_builder(shardid, direction)
        return d.addCallback(on_success).addErrback(on_error)

    @wait_for(timeout=QUERY_TIMEOUT)
    def sync_request_data_transfer(self, shardid, peer_unl, direction):
        """Request data be transfered to or from a peer.

        This call will block until the data has been
         transferred full or failed.

        Maybe this should be changed to match the params for
        the other handlers. No - because the contract isn't
        available yet -- that's what accept determines.

        Args:
            shardid: The sha256 sum of the data to be transfered.
            peer_unl: The node UNL of the peer to get the data from.
            direction: "send" to peer or "receive" from peer

        Raises:
            RequestDenied: If the peer denied your request to transfer data.
            TransferError: If the data not transfered for other reasons.
        """
        self.async_request_data_transfer(shardid, peer_unl, direction)

    def add_transfer_start_handler(self, handler):
        self._transfer_start_handlers.add(handler)

    def remove_transfer_start_handler(self, handler):
        self._transfer_start_handlers.remove(handler)

    def add_transfer_request_handler(self, handler):
        """Add an allow transfer request handler.

        If any handler returns True the transfer request will be accepted.
        The handler must be callable and accept four arguments
        (nodeid, shardid, direction, file_size).

        nodeid = The id of the source node sending the transfer request
        shardid = The shard ID of the data to download or upload
        direction = Direction from the perspective of the requester:
         e.g. send (upload shardid to requester) or receive
         (download shardid from requester)
        file_size = The size of the file they wish to transfer

        Example:
            def on_transfer_request(nodeid, shardid, direction, file_size):
                # This handler  will accept everything but send nothing.
                if direction == "receive":
                    print("Accepting data: {0}".format(shardid))
                    return True
                elif direction == "send":
                    print("Refusing to send data {0}.".format(shardid))
                    return False

            node = Node()
            node.add_allow_transfer_handler(on_transfer_request)
        """
        # FIXME change direction to more clear "push" and "pull"
        self._transfer_request_handlers.add(handler)

    def remove_transfer_request_handler(self, handler):
        """Remove a allow transfer request handler from the Node.

        Raises:
            KeyError if handler was not previously added.
        """
        self._transfer_request_handlers.remove(handler)

    def add_transfer_complete_handler(self, handler):
        """Add a transfer complete handler.

        The handler must be callable and accept four arguments
        (nodeid, shardid, direction).

        TO DO: this has changed completely.

        nodeid = The node_ID we sent the transfer request to.
        (May be our nodeid if the request was sent to us.)
        shardid = The shard to download or upload.
        direction = The direction of the transfer (e.g. send or receive.)

        Example:
            def on_transfer_complete(nodeid, shardid, direction):
                if direction == "receive":
                    print("Received: {0}".format(shardid))
                elif direction == "send":
                    print("Sent: {0}".format(shardid))
            node = Node()
            node.add_transfer_complete_handler(on_transfer_complete)
        """
        self._transfer_complete_handlers.add(handler)

    def remove_transfer_complete_handler(self, handler):
        """Remove a transfer complete handler.

        Raises:
            A twisted.internet.defer.Deferred that resloves to
            KeyError if handler was not previously added.
        """
        self._transfer_complete_handlers.remove(handler)

    #######################
    # messaging interface #
    #######################

    def repeat_relay_message(self, nodeid, message):
        return self.repeat_relay.relay(nodeid, message)

    def relay_message(self, nodeid, message):
        """Send relay message to a node.

        Queues a message to be relayed accross the network. Relay messages are
        sent to the node nearest the receiver in the routing table that accepts
        the relay message. This continues until it reaches the destination or
        the nearest node to the receiver is reached.

        Because messages are always relayed only to reachable nodes in the
        current routing table, there is a fare chance nodes behind a NAT can
        be reached if it is connected to the network.

        Args:
            nodeid: 160bit nodeid of the reciever as bytes
            message: iu-msgpack-python serializable message data

        Returns:
            True if message was added to relay queue, otherwise False.
        """

        return self.server.relay_message(nodeid, message)

    def _dispatch_message(self, message, handler):
        try:
            return handler(self, message)
        except Exception as e:
            txt = """Message handler raised exception: {0}\n\n{1}"""
            _log.error(txt.format(repr(e), traceback.format_exc()))

    def _message_dispatcher_loop(self):
        count_a = 0
        count_b = 0
        count_c = 0
        sleep_time = 0.0001
        timestamp = time.time()
        one_sec = 1 / sleep_time
        five_sec = 5 / sleep_time
        one_hundred_ms = 0.1 / sleep_time
        while not self._message_dispatcher_thread_stop:
            for message in self.server.get_messages():
                for handler in self._message_handlers.copy():
                    self._dispatch_message(message, handler)

            # Synchronize
            if count_c >= five_sec:
                if self._data_transfer is not None:
                    pass

                count_c = 0

            # Process new DHT messages.
            if count_a >= one_hundred_ms:
                if self._data_transfer is not None:
                    process_dht_messages(self._data_transfer)

                count_a = 0

            # Reset count and do upkeep.
            if count_b >= one_sec:
                if self._data_transfer is not None:
                    do_upkeep(self._data_transfer, timestamp)
                count_b = 0
                timestamp = time.time()

            # (Message-handler thread-safe
            # Process any file transfers.
            speed_up = False
            if self._data_transfer is not None:
                # Give latency test hooks chance to be enabled.
                duration = timestamp - self._data_transfer.start_time

                # If context switching or threading is
                # especially unfavourable
                # The algorithm won't be !@##ed.
                if duration >= 5:
                    # Get which sockets send / recv.
                    alive = process_transfers(
                        self._data_transfer,
                        timestamp
                    )

                    # Update alive time.
                    for con in list(alive):
                        if alive[con]:
                            con.alive = timestamp

                    # Speed up.
                    # if self._data_transfer.are_running():
                    #    speed_up = True

            # if not speed_up:
            #    time.sleep(THREAD_SLEEP)
            time.sleep(sleep_time)
            count_a += 1
            count_b += 1
            count_c += 1

    def add_message_handler(self, handler):
        """Add message handler to be call when a message is received.

        The handler must be callable and accept two arguments. The first is the
        calling node itself, the second argument is the message.

        Returns:
            The given handler.

        Example:
           node = Node()
           def on_message(node, message):
               print("Received message: {0}".format(message))
           node.add_message_handler(handler)
        """
        self._message_handlers.add(handler)
        return handler

    def remove_message_handler(self, handler):
        """Remove a message handler from the Node.

        Raises:
            KeyError if handler was not previously added.
        """
        self._message_handlers.remove(handler)

    ##############################
    # non blocking DHT interface #
    ##############################

    def async_get(self, key, default=None):
        """Get a key if the network has it.

        Returns:
            A twisted.internet.defer.Deferred that resloves to
            None if not found, the value otherwise.
        """
        # FIXME return default if not found (add to kademlia)
        return self.server.get(key)

    def async_set(self, key, value):
        """Set the given key to the given value in the network.

        Returns:
            A twisted.internet.defer.Deferred that resloves when set.
        """
        return self.server.set(key, value)

    ###############################
    # blocking DHT dict interface #
    ###############################

    @wait_for(timeout=WALK_TIMEOUT)
    def get(self, key, default=None):
        """D.get(k[,d]) -> D[k] if k in D, else d.  d defaults to None.

        Raises:
            crochet.TimeoutError after storjnode.network.server.WALK_TIMEOUT
        """
        return self.async_get(key, default=default)

    @wait_for(timeout=WALK_TIMEOUT)
    def put(self, key, value):
        """Insert a key value pair into the DHT.

        Returns:
            True on success, otherwise False.

        Raises:
            crochet.TimeoutError after storjnode.network.server.WALK_TIMEOUT
        """
        return self.async_set(key, value)

    @wait_for(timeout=WALK_TIMEOUT)
    def __setitem__(self, key, value):
        """x.__setitem__(i, y) <==> x[i]=y

        Raises:
            crochet.TimeoutError after storjnode.network.server.WALK_TIMEOUT
        """
        self.async_set(key, value)

    def __getitem__(self, key):
        """x.__getitem__(y) <==> x[y]"""
        result = self.get(key, KeyError(key))
        if isinstance(result, KeyError):
            raise result
        return result

    def __contains__(self, k):
        """D.__contains__(k) -> True if D has a key k, else False"""
        try:
            self[k]
            return True
        except KeyError:
            return False

    def has_key(self, k):
        """D.has_key(k) -> True if D has a key k, else False"""
        return k in self

    def setdefault(self, key, default=None):
        """D.setdefault(k[,d]) -> D.get(k,d), also set D[k]=d if k not in D"""
        if key not in self:
            self[key] = default
        return self[key]

    def update(self, e=None, **f):
        """D.update([e, ]**f) -> None.  Update D from dict/iterable e and f.
        If e present and has a .keys() method, does: for k in e: D[k] = e[k]
        If e present and lacks .keys() method, does: for (k, v) in e: D[k] = v
        In either case, this is followed by: for k in f: D[k] = f[k]
        """
        if e and "keys" in dir(e):
            for k in e:
                self[k] = e[k]
        else:
            for (k, v) in e:
                self[k] = v
        for k in f:
            self[k] = f[k]
