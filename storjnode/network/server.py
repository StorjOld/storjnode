import btctxstore
from storjnode.network.protocol import StorjProtocol
from twisted.internet import defer
from pycoin.encoding import a2b_hashed_base58
from kademlia.network import Server
from kademlia.log import Logger
from kademlia.storage import ForgetfulStorage
from kademlia.utils import digest
from twisted.internet.task import LoopingCall
from kademlia.node import Node
from kademlia.crawling import ValueSpiderCrawl


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
        self.log = Logger(system=self)
        self.storage = storage or ForgetfulStorage()
        self.node = Node(self.get_id())
        self.protocol = StorjProtocol(self.node, self.storage, ksize)
        self.refreshLoop = LoopingCall(self.refreshTable).start(3600)

    def get_id(self):
        # key to id FIXME use public key with network prefix instead!
        address = self._btctxstore.get_address(self._key)
        return a2b_hashed_base58(address)

    def messages_received(self):
        # TODO implement
        return []

    def message_send(self, nodeid, message):
        # TODO implement
        return defer.succeed(None)
