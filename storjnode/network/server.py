import time
import threading
import btctxstore
import binascii
import logging
from storjnode import util
from storjnode.network.protocol import StorjProtocol
from twisted.internet import defer
from pycoin.encoding import a2b_hashed_base58
from kademlia.network import Server
from kademlia.storage import ForgetfulStorage
from twisted.internet.task import LoopingCall
from kademlia.node import Node
from kademlia.crawling import NodeSpiderCrawl


class StorjServer(Server):

    def __init__(self, key, ksize=20, alpha=3, storage=None,
                 message_timeout=30, max_messages=1024, default_hop_limit=64):
        """
        Create a server instance.  This will start listening on the given port.

        Args:
            key: bitcoin wif/hwif to be used as id and for signing/encryption
            ksize (int): The k parameter from the kademlia paper
            alpha (int): The alpha parameter from the kademlia paper
            storage: implements :interface:`~kademlia.storage.IStorage`
            message_timeout: Seconds until unprocessed messages are dropped.
        """
        self._message_timeout = message_timeout
        self._default_hop_limit = default_hop_limit

        # TODO validate key is valid wif/hwif for mainnet or testnet
        testnet = False  # FIXME get from wif/hwif
        self._btctxstore = btctxstore.BtcTxStore(testnet=testnet)

        # allow hwifs
        is_hwif = self._btctxstore.validate_wallet(key)
        self._key = self._btctxstore.get_key(key) if is_hwif else key

        # XXX Server.__init__ cannot call super because of StorjProtocol
        # passing the protocol class should be added upstream
        self.ksize = ksize
        self.alpha = alpha
        self.log = logging.getLogger(__name__)
        self.storage = storage or ForgetfulStorage()
        self.node = Node(self.get_id())
        self.protocol = StorjProtocol(
            self.node, self.storage, ksize, max_messages=max_messages,
            max_hop_limit=self._default_hop_limit
        )
        self.refreshLoop = LoopingCall(self.refreshTable).start(3600)

        # setup relay message thread
        self._relay_thread_stop = False
        self._relay_thread = threading.Thread(target=self._relay_loop)
        self._relay_thread.start()

        # setup cleanup thread (removes stale messages)
        self._cleanup_thread_stop = False
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop)
        self._cleanup_thread.start()

    def stop(self):
        self._relay_thread_stop = True
        self._cleanup_thread_stop = True
        self._relay_thread.join()
        self._cleanup_thread.join()
        # FIXME actually disconnect from port and stop properly

    def get_id(self):
        address = self._btctxstore.get_address(self._key)
        return a2b_hashed_base58(address)[1:]  # remove network prefix

    def has_messages(self):
        return self.protocol.has_messages()

    def get_messages(self):
        return self.protocol.get_messages()

    def send_relay_message(self, nodeid, message):
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
        """
        hexid = binascii.hexlify(nodeid)

        if nodeid == self.node.id:
            self.log.info("Dropping message to self.")
            return

        # add to message relay queue
        self.log.debug("Queuing relay messaging for %s: %s" % (hexid, message))
        self.protocol.queue_relay_message({
            "dest": nodeid, "message": message,
            "hop_limit": self._default_hop_limit
        })

    def _relay_message(self, entry):
        """Returns entry if failed to relay to a closer node or None"""

        dest_node = Node(entry["dest"])
        nearest = self.protocol.router.findNeighbors(dest_node,
                                                     exclude=self.node)
        for relay_node in nearest:
            dist_self = dest_node.distanceTo(self.node)
            dist_relay = dest_node.distanceTo(relay_node)
            if dist_self <= dist_relay:
                continue  # do not relay away from node

            hexid = binascii.hexlify(relay_node.id)
            self.log.debug("Attempting to relay message for %s" % hexid)
            defered = self.protocol.callRelayMessage(
                relay_node, entry["dest"], entry["hop_limit"], entry["message"]
            )
            defered = defered.addCallback(lambda r: r[0] and r[1] or None)
            result = util.blocking_call(lambda: defered)
            if result is not None:
                self.log.debug("Successfully relayed message to %s" % hexid)
                return  # relay to nearest peer, avoid amplification attacks

        self.log.debug("Failed to relay message for %s" % dest_node)

    def _relay_loop(self):
        while not self._relay_thread_stop:
            # FIXME use worker pool to process queue
            for entry in util.empty_queue(self.protocol.messages_relay):
                self._relay_message(entry)
            time.sleep(0.05)

    def _cleanup_loop(self):
        while not self._cleanup_thread_stop:
            for entry in self.get_messages():
                if time.time() - entry["timestamp"] < self._message_timeout:
                    self.protocol.queue_received_message(entry)
                else:
                    self.log.debug("Dropping stale received message")
            time.sleep(0.5)

    def send_direct_message(self, nodeid, message):
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
        hexid = binascii.hexlify(nodeid)
        self.log.debug("Direct messaging %s: %s" % (hexid, message))

        def found_callback(nodes):
            nodes = filter(lambda n: n.id == nodeid, nodes)
            if len(nodes) == 0:
                self.log.debug("Couldnt find destination node.")
                return defer.succeed(None)
            else:
                self.log.debug("found node %s" % binascii.hexlify(nodes[0].id))
                async = self.protocol.callDirectMessage(nodes[0], message)
                return async.addCallback(lambda r: r[0] and r[1] or None)

        node = Node(nodeid)
        nearest = self.protocol.router.findNeighbors(node)
        if len(nearest) == 0:
            self.log.warning("No known neighbors to find %s" % hexid)
            return defer.succeed(None)
        spider = NodeSpiderCrawl(self.protocol, node, nearest,
                                 self.ksize, self.alpha)
        return spider.find().addCallback(found_callback)

    def has_public_ip(self):
        def handle(ips):
            self.log.debug("Internet visible IPs: %s" % ips)
            ip = util.get_inet_facing_ip()
            self.log.debug("Internet facing IP: %s" % ip)
            is_public = ip is not None and ip in ips
            self.protocol.is_public = is_public  # update protocol state
            return is_public
        return self.inetVisibleIP().addCallback(handle)
