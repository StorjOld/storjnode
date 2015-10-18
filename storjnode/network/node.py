import time
import copy
import threading
import btctxstore
from storjnode import util
from twisted.internet import reactor
from pycoin.encoding import b2a_hashed_base58
from pycoin.encoding import a2b_hashed_base58
from kademlia.network import Server


DEFAULT_NODE_ADDRESS = ("127.0.0.1", 4653)


class BlockingNode(object):

    def __init__(self, config):
        """Create a node instance with the given config. Behaves like a dict
        regarding DHT functionality. All calls are blocking for ease of use.

        example_config = {
            "node_key": "BITCOIN_WIF_OR_HWIF",
            "node_address": ("127.0.0.1", 4653),
            "bootstrap_nodes": [
                ("127.0.0.1", 1234),
                ("FE80:0000:0000:0000:0202:B3FF:FE1E:8329", 1234),
            ],
        }
        """
        config = copy.deepcopy(config)  # use copy for safety
        self._validate_config(config)
        self._config = config
        self._config_mutex = threading.RLock()
        testnet = False  # FIXME get from node_key
        self._btctxstore = btctxstore.BtcTxStore(testnet=testnet)
        self._dht = None
        self._reactor_thread = None

    def _cfg(self, *args, **kwargs):
        with self._config_mutex:
            return self._config.get(*args, **kwargs)

    def _validate_config(self, config):

        # validate node_key
        node_key = config.get("node_key")
        assert(node_key is not None)
        # TODO test node_key is valid wif/hwif for mainnet or testnet

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

    def get_nodeid(self):
        """Return the id of this node (bitcoin address as int)."""
        # use public key as nodeid instead?
        node_key = self._cfg("node_key")
        if self._btctxstore.validate_wallet(node_key):
            node_key = self._btctxstore.get_key(node_key)
        address = self._btctxstore.get_address(node_key)
        address_bytes = a2b_hashed_base58(address)
        return btctxstore.common.num_from_bytes(21, address_bytes)

    def start(self, start_reactor=True):
        """Start node and join the network.

        Arguments:
          start_reactor: Start twisted reactor, True by default.
        """
        if self.is_running():
            return

        # start dht node
        self._dht = Server()
        ip, port = self._cfg("node_address")
        self._dht.listen(port)
        bootstrap_nodes = self._cfg("bootstrap_nodes", [])
        if len(bootstrap_nodes) > 0:
            self._dht.bootstrap(bootstrap_nodes)

        # start twisted reactor
        if start_reactor:
            self._reactor_thread = threading.Thread(
                target=reactor.run,
                kwargs={"installSignalHandlers": False}
            )
            self._reactor_thread.start()

    def is_running(self):
        """Returns true if the node is running."""
        return self._dht is not None  # FIXME better implementation

    def is_linked(self):
        """Returns true the node is linked to the network."""
        return self.is_running()  # FIXME actually check for links

    def stop(self, stop_reactor=True):
        """Stop node and leave the network.

        Arguments:
            stop_reactor: Stop twisted reactor, True by default.
        """
        if not self.is_running():
            return

        # stop dht node
        del self._dht
        self.dht = None

        # stop reactor
        if stop_reactor:
            reactor.stop()
            self.reactor_thread.join()
            self.reactor_thread = None

    def restart(self, new_config=None, restart_reactor=True):
        """Restart node.

        Arguments:
          new_config: Optionaly update the node config during restart.
          restart_reactor: Optionaly restart twisted reactor.
        """

        # update config
        if new_config is not None:
            with self._config_mutex:
                config = copy.deepcopy(config)  # use copy for safety
                self._validate_config(config)
                self._config = config

        # restart node
        self.stop(stop_reactor=restart_reactor)
        self.start(start_reactor=restart_reactor)

    ##########################################
    # DHT Funcions mostly like a normal dict #
    ##########################################

    def __getitem__(self, key):
        """x.__getitem__(y) <==> x[y]"""
        result = self.get(key, KeyError(key))
        if isinstance(result, KeyError):
            raise result
        return result

    def __setitem__(self, key, value):
        """x.__setitem__(i, y) <==> x[i]=y"""
        if not self.is_linked():
            raise Exception("Node must be linked to store data!")
        finished = threading.Event()
        def callback(result):
            finished.set()
        self._dht.set(key, value).addCallback(callback)
        finished.wait()  # block until added

    def get(self, key, default=None):
        """D.get(k[,d]) -> D[k] if k in D, else d.  d defaults to None."""
        if not self.is_linked():
            raise Exception("Node must be linked to store data!")
        finished = threading.Event()
        values = []
        def callback(result):
            values.append(result)
            finished.set()
        # FIXME update kademlia to accept a default, to know if not found.
        self._dht.get(key).addCallback(callback)
        finished.wait()  # block until found
        result = values[0]
        # FIXME return default if not found
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

    def __repr__(self):
        """x.__repr__() <==> repr(x)"""
        # FIXME return internal state so that eval(repr(x)) is valid
        raise NotImplementedError("FIXME implement!")

    def values(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def viewitems(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def viewkeys(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def viewvalues(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __cmp__(self, other):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __eq__(self, other):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __ge__(self, other):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __gt__(self, other):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __le__(self, other):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __len__(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __lt__(self, other):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __ne__(self, other):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def clear(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def copy(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def items(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def iteritems(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def iterkeys(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def itervalues(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def keys(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __iter__(self):
        """Not implemented by design, keyset to big."""
        raise NotImplementedError("Not implemented by design, keyset to big.")

    def __delitem__(self, y):
        """Not implemented by design, write only."""
        raise NotImplementedError("Not implemented by design, write only.")

    def pop(self, k, d=None):
        """Not implemented by design, write only."""
        raise NotImplementedError("Not implemented by design, write only.")

    def popitem(self):
        """Not implemented by design, write only."""
        raise NotImplementedError("Not implemented by design, write only.")
