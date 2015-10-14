import threading
from kad import DHT
from storjnode.network.absnode import AbstractNode


class KadPyNode(AbstractNode):

    def __init__(self, config):
        super(KadPyNode, self).__init__(config)
        self._dht = None
        self._dht_mutex = threading.RLock()

    def put(self, key, data):
        # FIXME check key and data limitations
        if not self.is_linked():
            raise Exception("Node must be linked to store data!")
        with self._dht_mutex:
            self._dht[key] = data

    def get(self, key):
        # FIXME check key limitations
        if not self.is_linked():
            raise Exception("Node must be linked to store data!")
        with self._dht_mutex:
            return self._dht[key]

    def start(self):
        if self.is_running():
            return
        with self._dht_mutex:
            nodeid = self.get_nodeid()
            ip, port = self.cfg("node_address")
            self._dht = DHT(ip, port, # FIXME id=nodeid, # str ^ str => error
                            bootstrap_nodes=self.cfg("bootstrap_nodes", []))

    def is_running(self):
        with self._dht_mutex:
            return self._dht is not None

    def is_linked(self):
        with self._dht_mutex:
            return self._dht is not None  # FIXME actually check for links

    def stop(self):
        if not self.is_running():
            return
        with self._dht_mutex:
            del self._dht
            self.dht = None
