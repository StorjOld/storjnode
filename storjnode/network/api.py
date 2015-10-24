import threading
from storjnode.util import valid_ip
from twisted.internet import reactor
from storjnode.network.server import StorjServer


DEFAULT_PORT = 4653
DEFAULT_BOOTSTRAP_NODES = [
    ("104.236.1.59", 4653),    # storj stable  7b489cbfd61e675b86ac6469b6acd0a197da7f2c
    ("159.203.64.230", 4653),  # storj develop 3f9f80fdfce32a08048193e3ba31393c0777ab21
    ("78.46.188.55", 4653),    # F483's server 4c2acf7bdbdc57a3ae512ffba3ccf4f72a0367f9
]


class BlockingNode(object):

    def __init__(self, key, port=DEFAULT_PORT,
                 start_reactor=True, bootstrap_nodes=None):
        """Create a node instance, DHT functions like a dict.
        All calls are blocking for ease of use.
        """

        # validate port
        assert(isinstance(port, int))
        assert(port >= 0 and port <= 2**16)

        # validate bootstrap_nodes
        if bootstrap_nodes is None:
            bootstrap_nodes = DEFAULT_BOOTSTRAP_NODES
        for address in bootstrap_nodes:
            assert(isinstance(address, tuple) or isinstance(address, list))
            assert(len(address) == 2)
            other_ip, other_port = address
            assert(valid_ip(other_ip))
            assert(isinstance(other_port, int))
            assert(other_port >= 0 and other_port <= 2**16)

        # start dht node
        self._server = StorjServer(key)
        self._server.listen(port)
        if len(bootstrap_nodes) > 0:
            self._server.bootstrap(bootstrap_nodes)

        # start twisted reactor
        if start_reactor:
            self._reactor_thread = threading.Thread(
                target=reactor.run,
                kwargs={"installSignalHandlers": False}
            )
            self._reactor_thread.start()
        else:
            self._reactor_thread = None

    def stop_reactor(self):
        """Stop twisted rector if it was started by this node."""
        if self._reactor_thread is not None:
            reactor.stop()
            self._reactor_thread.join()
            self._reactor_thread = None

    def get_id(self):
        return self._server.get_id()

    def has_messages(self):
        return self._server.has_messages()

    def get_messages(self):
        return self._server.get_messages()

    def _blocking_call(self, async_method, *args, **kwargs):
        finished = threading.Event()
        return_values = []

        def callback(*args, **kwargs):
            assert(len(args) == 1)
            return_values.append(args[0])
            finished.set()

        async_method(*args, **kwargs).addCallback(callback)
        finished.wait()  # block until callback called
        return return_values[0] if len(return_values) == 1 else None

    def send_message(self, nodeid, message):
        return self._blocking_call(self._server.send_message, nodeid, message)

    def __getitem__(self, key):
        """x.__getitem__(y) <==> x[y]"""
        result = self.get(key, KeyError(key))
        if isinstance(result, KeyError):
            raise result
        return result

    def __setitem__(self, key, value):
        """x.__setitem__(i, y) <==> x[i]=y"""
        self._blocking_call(self._server.set, key, value)

    def get(self, key, default=None):
        """D.get(k[,d]) -> D[k] if k in D, else d.  d defaults to None."""
        # FIXME return default if not found (add to kademlia)
        return self._blocking_call(self._server.get, key)

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
