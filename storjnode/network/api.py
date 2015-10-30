from storjnode.util import valid_ip, blocking_call
from storjnode.network.server import StorjServer


DEFAULT_PORT = 4653
DEFAULT_BOOTSTRAP_NODES = [

    # storj stable  7b489cbfd61e675b86ac6469b6acd0a197da7f2c
    ("104.236.1.59", 4653),

    # storj develop 3f9f80fdfce32a08048193e3ba31393c0777ab21
    ("159.203.64.230", 4653),

    # F483's server 4c2acf7bdbdc57a3ae512ffba3ccf4f72a0367f9
    ("78.46.188.55", 4653),
]


class BlockingNode(object):
    """Blocking storj network layer implementation.

    DHT functions like a dict and all calls are blocking for ease of use.
    """

    def __init__(self, key, port=DEFAULT_PORT,
                 start_reactor=True, bootstrap_nodes=None,
                 storage=None, message_timeout=30, max_messages=1024):
        """Create a blocking storjnode instance.

        Args:
            key: Bitcoin wif/hwif to use for auth, encryption and node id.
            port: Port to use for incoming packages.
            start_reactor: Starts twisted reactor if True
            bootstrap_nodes: Known network node addresses as [(ip, port), ...]
            storage: implements :interface:`~kademlia.storage.IStorage`
            message_timeout: Seconds until unprocessed messages are dropped.
            max_messages: Maximum unprecessed messages, additional are dropped.
        """

        # validate message timeout
        assert(isinstance(message_timeout, int))
        assert(isinstance(max_messages, int))

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
        self._server = StorjServer(key, storage=storage,
                                   message_timeout=message_timeout,
                                   max_messages=max_messages)
        self._server.listen(port)
        if len(bootstrap_nodes) > 0:
            self._server.bootstrap(bootstrap_nodes)

    def stop(self):
        """Stop storj node."""
        self._server.stop()

    def get_id(self):
        """Returs 160bit node id as bytes."""
        return self._server.get_id()

    def has_public_ip(self):
        """Returns True if local IP is internet visible, otherwise False.

        The may false positive if you run other nodes on your local network.
        """
        return blocking_call(self._server.has_public_ip)

    def has_messages(self):
        """Returns True if this node has received messages."""
        return self._server.has_messages()

    def get_messages(self):
        """Get list of messages received since this method was last called.

        Returns:
            [{"source": kademlia.node.Node, "massage": message_data}, ...]
        """
        return self._server.get_messages()

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
        self._server.send_relay_message(nodeid, message)

    def send_direct_message(self, nodeid, message):
        """Send direct message to a node.

        Spidercrawls the network to find the node and sends the message
        directly. This will fail if the node is behind a NAT and doesn't
        have a public ip.

        Args:
            nodeid: 160bit nodeid of the reciever as bytes
            message: iu-msgpack-python serializable message data

        Returns:
            Own transport address (ip, port) if successfull else None
        """
        async_method = self._server.send_direct_message
        return blocking_call(async_method, nodeid, message)

    def __getitem__(self, key):
        """x.__getitem__(y) <==> x[y]"""
        result = self.get(key, KeyError(key))
        if isinstance(result, KeyError):
            raise result
        return result

    def __setitem__(self, key, value):
        """x.__setitem__(i, y) <==> x[i]=y"""
        blocking_call(self._server.set, key, value)

    def get(self, key, default=None):
        """D.get(k[,d]) -> D[k] if k in D, else d.  d defaults to None."""
        # FIXME return default if not found (add to kademlia)
        return blocking_call(self._server.get, key)

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
