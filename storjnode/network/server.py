import os
import time
import umsgpack
import datetime
import threading
import btctxstore
import storjnode
from storjnode.util import safe_log_var
from storjnode.common import THREAD_SLEEP
from kademlia.network import Server as KademliaServer
from kademlia.storage import ForgetfulStorage
from kademlia.node import Node as KademliaNode
from kademlia.routing import TableTraverser
from storjnode.network.protocol import Protocol
from twisted.internet import defer
from twisted.internet.task import LoopingCall
from crochet import run_in_reactor
from storjnode.network.messages.base import MAX_MESSAGE_DATA


if os.environ.get("STORJNODE_QUERY_TIMEOUT"):
    QUERY_TIMEOUT = float(os.environ.get("STORJNODE_QUERY_TIMEOUT"))
else:
    QUERY_TIMEOUT = 5.0  # default seconds
WALK_TIMEOUT = QUERY_TIMEOUT * 24.0


_log = storjnode.log.getLogger(__name__)


class MessageRelayer(object):

    def __init__(self, server, dest, hop_limit, message):
        self.server = server
        self.node = self.server.node
        self.dest = KademliaNode(dest)
        self.hop_limit = hop_limit
        self.message = message
        self.nearest = None

    @run_in_reactor
    def start(self):
        self.nearest = self.server.protocol.router.findNeighbors(
            self.dest, exclude=self.server.node
        )
        txt = "{1}: Relaying to nearest peers: {0}"
        _log.debug(txt.format(repr(self.nearest), self.server.get_address()))
        self.nearest.reverse()  # reverse so you can pop the next
        self.attempt_relay([True, None])

    def __call__(self, result):
        self.attempt_relay(result)

    def attempt_relay(self, result):
        success = bool(result[0] and result[1])
        dest_address = storjnode.util.node_id_to_address(self.dest.id)

        if success:
            txt = "{1}: Successfully relayed message for {0}"
            _log.debug(txt.format(dest_address, self.server.get_address()))
            return  # relay only to nearest peer, avoid amplification attacks!

        elif not self.nearest:
            txt = "{1}: Failed to relay message for {0}"
            _log.debug(txt.format(dest_address, self.server.get_address()))
            return

        relay_node = self.nearest.pop()
        address = storjnode.util.node_id_to_address(relay_node.id)

        # do not relay away from node
        if self.dest.distanceTo(self.node) <= self.dest.distanceTo(relay_node):
            txt = "{1}: Aborting relay attempt, {0} farther then self."
            _log.debug(txt.format(address, self.get_address()))
            return

        # attempt to relay message
        txt = "{1}: Attempting to relay message for {0}"
        _log.debug(txt.format(address, self.server.get_address()))
        self.server.protocol.callRelayMessage(
            relay_node, self.dest.id, self.hop_limit, self.message
        ).addCallback(self)


class Server(KademliaServer):

    def __init__(self, key, port, ksize=20, alpha=3, storage=None,
                 max_messages=1024, default_hop_limit=64,
                 refresh_neighbours_interval=WALK_TIMEOUT):
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
        self._default_hop_limit = default_hop_limit
        self._refresh_neighbours_interval = refresh_neighbours_interval
        self._cached_address = None

        self.port_handler = None

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

    @run_in_reactor
    def set_port_handler(self, port_handler):
        self.port_handler = port_handler

    def stop(self):
        if self._refresh_neighbours_interval > 0.0:
            self._refresh_thread_stop = True
            self._refresh_thread.join()

        self._relay_thread_stop = True
        self._relay_thread.join()

        # disconnect from port and stop properly
        if self.port_handler is not None:
            self.port_handler.stopListening()

    @run_in_reactor
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
        if len(packed_message) > MAX_MESSAGE_DATA:
            raise Exception("Message to large {0} > {1}: {2}".format(
                len(packed_message), MAX_MESSAGE_DATA, repr(message)
            ))
        message = umsgpack.unpackb(packed_message)  # sanatize abstract types

        if nodeid == self.node.id:
            _log.debug("Adding message to self to received queue!.")
            return self.protocol.queue_received_message(message)
        else:
            txt = "Queuing relay messaging for %s: %s"
            address = storjnode.util.node_id_to_address(nodeid)
            if type(message) in (type(b""), type(u"")):
                safe_msg = safe_log_var(message)
            else:
                safe_msg = message
            _log.debug(txt % (address, safe_msg))
            return self.protocol.queue_relay_message({
                "dest": nodeid, "message": message,
                "hop_limit": self._default_hop_limit
            })

    def _refresh_loop(self):
        last_refresh = datetime.datetime.now()
        delta = datetime.timedelta(seconds=self._refresh_neighbours_interval)
        while not self._refresh_thread_stop:
            if (datetime.datetime.now() - last_refresh) > delta:
                self.refresh_neighbours()
                last_refresh = datetime.datetime.now()
            time.sleep(THREAD_SLEEP)

    def _relay_loop(self):
        while not self._relay_thread_stop:
            q = self.protocol.messages_relay
            for entry in storjnode.util.empty_queue(q):
                message_relayer = MessageRelayer(self, **entry)
                message_relayer.start()
            time.sleep(THREAD_SLEEP)

    def get_transport_info(self, unl=None):
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
            transport_info = {
                "wan": wan, "lan": lan, "unl": unl, "is_public": wan == lan
            }
            return transport_info

        ds = []
        for neighbor in self.bootstrappableNeighbors():
            ds.append(self.protocol.stun(neighbor))
        return defer.gatherResults(ds).addCallback(handle)
