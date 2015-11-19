import time
import threading
import binascii
import random
import logging
import storjnode
from btctxstore import BtcTxStore
from crochet import wait_for, run_in_reactor
from twisted.internet.task import LoopingCall
from storjnode.util import valid_ip, address_to_node_id
from storjnode.network.server import StorjServer, QUERY_TIMEOUT, WALK_TIMEOUT


# File transfer.
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.process_transfers import process_transfers
from pyp2p.net import Net
from pyp2p.dht_msg import DHT as SimDHT


_log = logging.getLogger(__name__)


DEFAULT_BOOTSTRAP_NODES = [

    # storj stable  7b489cbfd61e675b86ac6469b6acd0a197da7f2c
    ("104.236.1.59", 4653),

    # storj develop 3f9f80fdfce32a08048193e3ba31393c0777ab21
    ("159.203.64.230", 4653),

    # F483's server 4c2acf7bdbdc57a3ae512ffba3ccf4f72a0367f9
    ("78.46.188.55", 4653),
]


log = logging.getLogger(__name__)


class Node(object):
    """Storj network layer implementation.

    Provides a blocking dict like interface to the DHT for ease of use.
    """

    def __init__(self,
                 # kademlia DHT args
                 key, ksize=20, port=None, bootstrap_nodes=None,
                 dht_storage=None, max_messages=1024,
                 refresh_neighbours_interval=WALK_TIMEOUT,

                 # data transfer args
                 disable_data_transfer=True, store_config=None,
                 passive_port=None,
                 passive_bind=None,  # FIXME use utils.get_inet_facing_ip ?
                 node_type="unknown",  # FIMME what is this ?
                 nat_type="unknown",  # FIXME what is this ?
                 wan_ip=None):  # FIXME replace with sync_get_wan_ip calls
        """Create a blocking storjnode instance.

        Args:
            key (str): Bitcoin wif/hwif for auth, encryption and node id.
            ksize (int): The k parameter from the kademlia paper.
            port (port): Port to for incoming packages, randomly by default.
            bootstrap_nodes [(ip, port), ...]: Known network node addresses as.
            dht_storage: implements :interface:`~kademlia.storage.IStorage`
            max_messages (int): Max unprecessed messages, additional dropped.
            refresh_neighbours_interval (float): Auto refresh neighbours.

            disable_data_transfer: Disable data transfer for this node.
            store_config: Dict of storage paths to optional attributes.
                          limit: The dir size limit in bytes, 0 for no limit.
                          use_folder_tree: Files organized in a folder tree
                                           (always on for fat partitions).

            passive_port (int): Port to receive inbound TCP connections on.
            passive_bind (ip): LAN IP to receive inbound TCP connections on.
            node_type: TODO doc string
            nat_type: TODO doc string
            wan_ip: TODO doc string
        """
        self.disable_data_transfer = bool(disable_data_transfer)
        self._transfer_request_handlers = set()
        self._transfer_complete_handlers = set()

        # set default store config if None given
        if store_config is None:
            store_config = storjnode.storage.manager.DEFAULT_STORE_CONFIG

        # validate port (randomish user port by default)
        port = port or random.choice(range(1024, 49151))
        assert(0 <= port < 2 ** 16)
        self.port = port

        # passive port (randomish user port by default)
        passive_port = passive_port or random.choice(range(1024, 49151))
        assert(0 <= port < 2 ** 16)

        # FIXME chance of same port and passive_port being the same
        # FIXME exclude ports already being used on the machine

        # passive bind
        # FIXME just use storjnode.util.get_inet_facing_ip ?
        passive_bind = passive_bind or "0.0.0.0"
        assert(valid_ip(passive_bind))

        # validate bootstrap_nodes
        if bootstrap_nodes is None:
            bootstrap_nodes = DEFAULT_BOOTSTRAP_NODES  # pragma: no cover
        for address in bootstrap_nodes:
            assert(isinstance(address, tuple) or isinstance(address, list))
            assert(len(address) == 2)
            other_ip, other_port = address
            assert(valid_ip(other_ip))
            assert(isinstance(other_port, int))
            assert(0 <= other_port < 2 ** 16)

        # start services
        self._setup_server(key, ksize, dht_storage, max_messages,
                           refresh_neighbours_interval, bootstrap_nodes)

        self._setup_message_dispatcher()

        if not self.disable_data_transfer:
            self._setup_data_transfer_client(
                store_config, passive_port, passive_bind,
                node_type, nat_type, wan_ip
            )

    def _setup_message_dispatcher(self):
        self._message_handlers = set()
        self._message_dispatcher_thread_stop = False
        self._message_dispatcher_thread = threading.Thread(
            target=self._message_dispatcher_loop
        )
        self._message_dispatcher_thread.start()

    def _setup_server(self, key, ksize, storage, max_messages,
                      refresh_neighbours_interval, bootstrap_nodes):
        self.server = StorjServer(
            key, ksize=ksize, storage=storage, max_messages=max_messages,
            refresh_neighbours_interval=refresh_neighbours_interval
        )
        self.server.listen(self.port)
        self.server.bootstrap(bootstrap_nodes)

    def _setup_data_transfer_client(self, store_config, passive_port,
                                    passive_bind, node_type, nat_type, wan_ip):
        # Setup handlers for callbacks registered via the API.
        handlers = {
            "complete": self._transfer_complete_handlers,
            "accept": self._transfer_request_handlers
        }

        wallet = BtcTxStore(testnet=False, dryrun=True)
        wif = self.get_key()
        node_id = address_to_node_id(wallet.get_address(wif))
        #dht_node = SimDHT(node_id=node_id)
        dht_node = self

        self._data_transfer = FileTransfer(
            net=Net(
                net_type="direct",
                node_type=node_type,
                nat_type=nat_type,
                dht_node=dht_node,
                debug=1,
                passive_port=passive_port,
                passive_bind=passive_bind,
                wan_ip=wan_ip
            ),
            wif=wif,
            store_config=store_config,
            handlers=handlers
        )

        # Setup success callback values.
        self._data_transfer.success_value = (self.sync_get_wan_ip(), self.port)
        self.process_data_transfers()

    def stop(self):
        """Stop storj node."""
        self._message_dispatcher_thread_stop = True
        self._message_dispatcher_thread.join()
        self.server.stop()
        if not self.disable_data_transfer:
            self._data_transfer.net.stop()

    ##################
    # node interface #
    ##################

    def refresh_neighbours(self):
        self.server.refresh_neighbours()

    def get_known_peers(self):
        """Returns list of hex encoded node ids."""
        peers = list(self.server.get_known_peers())
        return list(map(lambda n: binascii.hexlify(n.id), peers))

    def get_key(self):
        """Returns Bitcoin wif for auth, encryption and node id"""
        return self.server.key

    def get_id(self):
        """Returns 160bit node id as bytes."""
        return self.server.get_id()

    def get_hex_id(self):
        return self.server.get_hex_id()

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
        return self.server.has_public_ip()

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
        return self.server.get_wan_ip()

    ######################################
    # depricated data transfer interface #
    ######################################

    def move_to_storage(self, path):
        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")
        # FIXME remove and have callers use storage service instead
        return self._data_transfer.move_file_to_storage(path)

    def get_unl(self):
        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")
        return self._data_transfer.net.unl.value

    @run_in_reactor
    def process_data_transfers(self):
        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")

        time.sleep(5)  # Give enough time to copy UNL.
        LoopingCall(process_transfers, self._data_transfer).start(0.002,
                                                                  now=True)

    ###########################
    # data transfer interface #
    ###########################

    def async_request_data_transfer(self, data_id, peer_unl, direction):
        """Request data be transfered to or from a peer.

        Args:
            data_id: The sha256 sum of the data to be transfered.
            peer_unl: The node UNL of the peer to get the data from.
            direction: "send" to peer or "receive" from peer

        Returns:
            A twisted.internet.defer.Deferred that resloves to
            own transport address (ip, port) if successfull else None

        Raises:
            RequestDenied: If the peer denied your request to transfer data.
            TransferError: If the data not transfered for other reasons.
        """
        return self._data_transfer.simple_data_request(data_id, peer_unl,
                                                       direction)

        if self.disable_data_transfer:
            raise Exception("Data transfer disabled!")

    @wait_for(timeout=QUERY_TIMEOUT)
    def sync_request_data_transfer(self, data_id, peer_unl, direction):
        """Request data be transfered to or from a peer.

        This call will block until the data has been transfered full or failed.

        Args:
            data_id: The sha256 sum of the data to be transfered.
            peer_unl: The node UNL of the peer to get the data from.
            direction: "send" to peer or "receive" from peer

        Raises:
            RequestDenied: If the peer denied your request to transfer data.
            TransferError: If the data not transfered for other reasons.
        """
        self.async_request_data_transfer(data_id, peer_unl, direction)

    def add_transfer_request_handler(self, handler):
        """Add an allow transfer request handler.

        If any handler returns True the transfer request will be accepted.
        The handler must be callable and accept four arguments
        (node_id, data_id, direction).

        node_id = The source node ID sending the transfer request
        data_id = The shard ID of the data to download or upload
        direction = Direction from the perspective of the requester: e.g. send (upload data_id to requester) or receive (download data_id from requester)

        Example:
            def on_transfer_request(node_id, data_id, direction):
                # This handler  will accept everything but send nothing.
                if direction == "receive":
                    print("Accepting data: {0}".format(data_id))
                    return True
                elif direction == "send":
                    print("Refusing to send data {0}.".format(data_id))
                    return False

            node = Node()
            node.add_allow_transfer_handler(on_transfer_request)
        """
        self._transfer_request_handlers.add(handler)

    def remove_transfer_request_handler(self, handler):
        """Remove a allow transfer request handler from the Node.

        Raises:
            KeyError if handler was not previously added.
        """
        self._transfer_complete_handlers.remove(handler)

    def add_transfer_complete_handler(self, handler):
        """Add a transfer complete handler.

        The handler must be callable and accept four arguments
        (node_id, data_id, direction).

        node_id = The node_ID we sent the transfer request to. (May be our node_id if the request was sent to us.)
        data_id = The shard to download or upload.
        direction = The direction of the transfer (e.g. send or receive.)

        Example:
            def on_transfer_complete(node_id, data_id, direction):
                if direction == "receive":
                    print("Received: {0}".format(data_id)
                elif direction == "send":
                    print("Sent: {0}".format(data_id)
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

    def async_direct_message(self, nodeid, message):
        """Send direct message to a node and return a defered result.

        Spidercrawls the network to find the node and sends the message
        directly. This will fail if the node is behind a NAT and doesn't
        have a public ip.

        Args:
            nodeid: 160bit nodeid of the reciever as bytes
            message: iu-msgpack-python serializable message data

        Returns:
            A twisted.internet.defer.Deferred that resloves to
            own transport address (ip, port) if successfull else None
        """
        return self.server.direct_message(nodeid, message)

    @wait_for(timeout=WALK_TIMEOUT)
    def direct_message(self, nodeid, message):
        """Send direct message to a node and block until complete.

        Spidercrawls the network to find the node and sends the message
        directly. This will fail if the node is behind a NAT and doesn't
        have a public ip.

        Args:
            nodeid: 160bit nodeid of the reciever as bytes
            message: iu-msgpack-python serializable message data

        Returns:
            Own transport address (ip, port) if successfull else None

        Raises:
            crochet.TimeoutError after storjnode.network.server.WALK_TIMEOUT
        """
        return self.server.direct_message(nodeid, message)

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

    def _dispatch_message(self, received, handler):
        try:
            source = received["source"].id if received["source"] else None
            handler(source, received["message"])
        except Exception as e:
            msg = "Message handler raised exception: {0}"
            log.error(msg.format(repr(e)))

    def _message_dispatcher_loop(self):
        while not self._message_dispatcher_thread_stop:
            for received in self.server.get_messages():
                for handler in self._message_handlers:
                    self._dispatch_message(received, handler)
            time.sleep(0.002)

    def add_message_handler(self, handler):
        """Add message handler to be call when a message is received.

        The handler must be callable and accept two arguments. The first
        argument is the source id and the second the message. The source id
        will be None if it was a relay message.

        Example:
           node = Node()
           def on_message(source_id, message):
               t = "relay" if source_id is None else "direct"
               print("Received {0} message: {1}".format(t, message))
           node.add_message_handler(handler)
        """
        self._message_handlers.add(handler)

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
        self.server.set(key, value)

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
