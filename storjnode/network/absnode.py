import abc
import threading
import btctxstore
from storjnode import util


DEFAULT_NODE_ADDRESS = ("127.0.0.1", 4653)


class AbstractNode(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, config):
        """Create a network node instance with the given config. 
        All calls are blocking for ease of use.

        example_config = {
            "nodekey": "BITCOIN_WIF_OR_HWIF",
            "node_address": ("127.0.0.1", 4653),
            "bootstrap_nodes": [
                ("127.0.0.1", 1234),
                ("FE80:0000:0000:0000:0202:B3FF:FE1E:8329", 1234),
            ],
        }
        """
        self._validate_config(config)
        self._config = config
        self._config_mutex = threading.RLock()
        testnet = False  # FIXME get from nodekey
        self._btctxstore = btctxstore.BtcTxStore(testnet=testnet)

    def cfg(self, *args, **kwargs):
        with self._config_mutex:
            return self._config.get(*args, **kwargs)

    def _validate_config(self, config):

        # validate nodekey
        nodekey = config.get("nodekey")
        assert(nodekey is not None)
        # TODO test nodekey is valid wif/hwif for mainnet or testnet

        # validate node_address
        address = config.get("node_address")
        if address is None:
            config["node_address"] = DEFAULT_NODE_ADDRESS
            address = config.get("node_address")
        self._validate_address(address)

        # validate bootstrap_nodes
        bootstrap_nodes = config.get("bootstrap_nodes", [])
        for address in bootstrap_nodes:
            self._validate_address(address)

    def _validate_address(self, address):
        assert(isinstance(address, tuple) or isinstance(address, tuple))
        assert(len(address) == 2)
        ip, port = address
        assert(util.valid_ip(ip))
        assert(isinstance(port, int))
        assert(port >= 0 and port <= 2**16)

    def update_config(self, config):
        """Safely update the config while the node is running."""
        with self._config_mutex:
            self._config = config

    def get_nodeid(self):
        """Return the id of this node."""
        # use public key as nodeid instead?
        nodekey = self.cfg("nodekey")
        if self._btctxstore.validate_wallet(nodekey):
            nodekey = self._btctxstore.get_key(nodekey)
        address = self._btctxstore.get_address(nodekey)

        addr_bytes = b"TODO"  # decode to bytes
        return btctxstore.common.num_from_bytes(21, addr_bytes)

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        return self.put(key, value)

    @abc.abstractmethod
    def put(self, key, value):
        """Store key->data in the DHT."""
        return

    @abc.abstractmethod
    def get(self, key):
        """Return data from the DHT for given key or None"""
        return

    @abc.abstractmethod
    def start(self):
        """Start node and join the network."""
        return

    @abc.abstractmethod
    def is_running(self):
        """Returns true if the node is running."""
        return

    @abc.abstractmethod
    def is_linked(self):
        """Returns true the node is linked to the network."""
        return

    @abc.abstractmethod
    def stop(self):
        """Stop node and leave the network."""
        return

    def restart(self):
        self.stop()
        self.start()
