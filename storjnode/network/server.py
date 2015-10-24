import btctxstore
import binascii
import logging
from storjnode.network.protocol import StorjProtocol
from twisted.internet import defer
from pycoin.encoding import a2b_hashed_base58
from kademlia.network import Server
from kademlia.storage import ForgetfulStorage
from twisted.internet.task import LoopingCall
from kademlia.node import Node
from kademlia.crawling import NodeSpiderCrawl


class StorjServer(Server):

    def __init__(self, key, ksize=20, alpha=3, storage=None):
        """
        Create a server instance.  This will start listening on the given port.

        Args:
            key: bitcoin wif/hwif to be used as id and for signing/encryption
            ksize (int): The k parameter from the kademlia paper
            alpha (int): The alpha parameter from the kademlia paper
            storage: implements :interface:`~kademlia.storage.IStorage`
        """

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
        self.protocol = StorjProtocol(self.node, self.storage, ksize)
        self.refreshLoop = LoopingCall(self.refreshTable).start(3600)

    def get_id(self):
        address = self._btctxstore.get_address(self._key)
        return a2b_hashed_base58(address)[1:]  # remove network prefix

    def has_messages(self):
        return not self.protocol.messages_received.empty()

    def get_messages(self):
        messages = []
        while self.has_messages():
            received = self.protocol.messages_received.get()
            # TODO reformat ?
            messages.append(received)
        return messages

    def send_message(self, nodeid, message):
        """
        Send a message to a given node on the network.
        """
        hexid = binascii.hexlify(nodeid)
        self.log.debug("messaging '%s' '%s'" % (hexid, message))
        node = Node(nodeid)

        def found_callback(nodes):
            self.log.debug("nearest nodes %s" % list(map(str, nodes)))
            nodes = filter(lambda n: n.id == nodeid, nodes)
            if len(nodes) == 0:
                self.log.debug("couldnt find destination node")
                return defer.succeed(None)
            else:
                self.log.debug("found node %s" % binascii.hexlify(nodes[0].id))
                async = self.protocol.callMessage(nodes[0], message)
                return async.addCallback(lambda r: r[0] and r[1] or None)

        nearest = self.protocol.router.findNeighbors(node)
        if len(nearest) == 0:
            self.log.warning("There are no known neighbors to find %s" % hexid)
            return defer.succeed(None)
        spider = NodeSpiderCrawl(self.protocol, node, nearest,
                                 self.ksize, self.alpha)
        return spider.find().addCallback(found_callback)
