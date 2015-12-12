import time
import umsgpack
import datetime
import threading
import btctxstore
import storjnode
from kademlia.network import Server as KademliaServer
from kademlia.storage import ForgetfulStorage
from kademlia.node import Node as KademliaNode
from kademlia.routing import TableTraverser
from kademlia.crawling import NodeSpiderCrawl
from storjnode.network.protocol import Protocol
from twisted.internet import defer
from twisted.internet.task import LoopingCall
from crochet import TimeoutError
from storjnode.network.messages.base import MAX_MESSAGE_DATA


QUERY_TIMEOUT = 5.0
WALK_TIMEOUT = QUERY_TIMEOUT * 24


_log = storjnode.log.getLogger(__name__)


class Server(KademliaServer):

    def __init__(self, key, port, ksize=20, alpha=3, storage=None,
                 max_messages=1024, default_hop_limit=64,
                 refresh_neighbours_interval=0.0):
        """
        Create a server instance.  This will start listening on the given port.

        Args:
            key (str): Bitcoin wif/hwif for auth, encryption and node id.
            ksize (int): The k parameter from the kademlia paper.
            alpha (int): The alpha parameter from the kademlia paper
            storage: implements :interface:`~kademlia.storage.IStorage`
            refresh_neighbours_interval (float): Auto refresh neighbours.
        """
        self.port = port
        self.thread_sleep_time = 0.02
        self._default_hop_limit = default_hop_limit
        self._refresh_neighbours_interval = refresh_neighbours_interval
        self._cached_address = None

        self.btctxstore = btctxstore.BtcTxStore(testnet=False)

        # allow hwifs
        is_hwif = self.btctxstore.validate_wallet(key)
        self.key = self.btctxstore.get_key(key) if is_hwif else key

        # XXX kademlia.network.Server.__init__ cant use super because Protocol
        # passing the protocol class should be added upstream
        self.ksize = ksize
        self.alpha = alpha
        self.log = storjnode.log.getLogger("kademlia.network")
        self.log.setLevel(60)

        self.storage = storage or ForgetfulStorage()
        self.node = KademliaNode(self.get_id())
        self.protocol = Protocol(
            self.node, self.storage, ksize, max_messages=max_messages,
            max_hop_limit=self._default_hop_limit
        )
        self.refreshLoop = LoopingCall(self.refreshTable).start(3600)

        self._start_threads()

    def _start_threads(self):

        # setup relay message thread
        self._relay_thread_stop = False
        self._relay_thread = threading.Thread(target=self._relay_loop)
        self._relay_thread.start()

        # setup refresh neighbours thread
        if self._refresh_neighbours_interval > 0.0:
            self._refresh_thread_stop = False
            self._refresh_thread = threading.Thread(target=self._refresh_loop)
            self._refresh_thread.start()

    def stop(self):
        if self._refresh_neighbours_interval > 0.0:
            self._refresh_thread_stop = True
            self._refresh_thread.join()

        self._relay_thread_stop = True
        self._relay_thread.join()

        # FIXME actually disconnect from port and stop properly

    def refresh_neighbours(self):
        _log.debug("Refreshing neighbours ...")
        self.bootstrap(self.bootstrappableNeighbors())

    def get_id(self):
        return storjnode.util.address_to_node_id(self.get_address())

    def get_address(self):
        if self._cached_address is not None:
            return self._cached_address
        self._cached_address = self.btctxstore.get_address(self.key)
        return self._cached_address

    def get_known_peers(self):
        """Returns list of known node."""
        return TableTraverser(self.protocol.router, self.node)

    def get_neighbours(self):
        return self.protocol.router.findNeighbors(self.node, exclude=self.node)

    def has_messages(self):
        return self.protocol.has_messages()

    def get_messages(self):
        return self.protocol.get_messages()

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

        # check max message size
        packed_message = umsgpack.packb(message)
        assert(len(packed_message) <= MAX_MESSAGE_DATA)
        message = umsgpack.unpackb(packed_message)  # sanatize abstract types

        if nodeid == self.node.id:
            _log.info("Adding message to self to received queue!.")
            return self.protocol.queue_received_message({
                "source": None, "message": message
            })
        else:
            txt = "Queuing relay messaging for %s: %s"
            address = storjnode.util.node_id_to_address(nodeid)
            _log.debug(txt % (address, message))
            return self.protocol.queue_relay_message({
                "dest": nodeid, "message": message,
                "hop_limit": self._default_hop_limit
            })

    def _relay_message(self, entry):
        """Returns entry if failed to relay to a closer node or None"""

        dest = KademliaNode(entry["dest"])
        nearest = self.protocol.router.findNeighbors(dest, exclude=self.node)
        _log.debug("Relaying to nearest: %s" % repr(nearest))
        for relay_node in nearest:

            # do not relay away from node
            if dest.distanceTo(self.node) <= dest.distanceTo(relay_node):
                msg = "Skipping %s, farther then self."
                _log.debug(msg % repr(relay_node))
                continue

            # relay message
            address = storjnode.util.node_id_to_address(relay_node.id)
            _log.debug("Attempting to relay message for %s" % address)
            defered = self.protocol.callRelayMessage(
                relay_node, entry["dest"], entry["hop_limit"], entry["message"]
            )
            defered = storjnode.util.default_defered(defered, None)

            # wait for relay result
            try:
                result = storjnode.util.wait_for_defered(defered,
                                                         timeout=QUERY_TIMEOUT)
            except TimeoutError:  # pragma: no cover
                msg = "Timeout while relayed message to %s"  # pragma: no cover
                _log.debug(msg % address)  # pragma: no cover
                result = None  # pragma: no cover

            # successfull relay
            if result is not None:
                _log.debug("Successfully relayed message to %s" % address)
                return  # relay to nearest peer, avoid amplification attacks

        # failed to relay message
        dest_address = storjnode.util.node_id_to_address(entry["dest"])
        _log.debug("Failed to relay message for %s" % dest_address)

    def _refresh_loop(self):
        last_refresh = datetime.datetime.now()
        delta = datetime.timedelta(seconds=self._refresh_neighbours_interval)
        while not self._refresh_thread_stop:
            if (datetime.datetime.now() - last_refresh) > delta:
                self.refresh_neighbours()
                last_refresh = datetime.datetime.now()
            time.sleep(self.thread_sleep_time)

    def _relay_loop(self):
        while not self._relay_thread_stop:
            # FIXME use worker pool to process queue
            q = self.protocol.messages_relay
            for entry in storjnode.util.empty_queue(q):
                self._relay_message(entry)
            time.sleep(self.thread_sleep_time)

    def direct_message(self, nodeid, message):
        """Send direct message to a node.

        Spidercrawls the network to find the node and sends the message
        directly. This will fail if the node is behind a NAT and doesn't
        have a public ip.

        Args:
            nodeid: 160bit nodeid of the reciever as bytes
            message: iu-msgpack-python serializable message data

        Returns:
            Defered own transport address (ip, port) if successfull else None
        """

        def found_callback(nodes):
            nodes = filter(lambda n: n.id == nodeid, nodes)
            if len(nodes) == 0:
                return defer.succeed(None)
            else:
                async = self.protocol.callDirectMessage(nodes[0], message)
                return async.addCallback(lambda r: r[0] and r[1] or None)

        node = KademliaNode(nodeid)
        nearest = self.protocol.router.findNeighbors(node)
        if len(nearest) == 0:
            return defer.succeed(None)
        spider = NodeSpiderCrawl(
            self.protocol, node, nearest, self.ksize, self.alpha
        )
        return spider.find().addCallback(found_callback)

    def get_transport_info(self):
        def handle(results):
            results = filter(lambda r: r[0], results)  # filter successful
            if not results:
                _log.warning("No successful stun!")
                return None

            # FIXME check all entries as some nodes may be on the local net
            result = results[0][1]

            if not result:
                _log.warning("No stun result!")
                return None

            wan = (result[0], result[1])
            lan = (storjnode.util.get_inet_facing_ip(), self.port)
            return {"wan": wan, "lan": lan}

        ds = []
        for neighbor in self.bootstrappableNeighbors():
            ds.append(self.protocol.stun(neighbor))
        return defer.gatherResults(ds).addCallback(handle)
