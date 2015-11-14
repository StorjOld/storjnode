import time
import logging
import binascii
from kademlia.node import Node
from crochet import TimeoutError
from threading import Thread
from threading import RLock
from storjnode import util
from storjnode.network.server import QUERY_TIMEOUT


_log = logging.getLogger(__name__)


class NetworkMapper(object):  # will not scale but good for now

    def __init__(self, server, initial_node=None, worker_num=32):
        self.nodes_toscan = {}  # {id: (ip, port)}
        self.nodes_scanning = {}  # {id: (ip, port)}

        # {id: {"transport": (ip, port), "neighbours": [(id, ip, port)]}
        self.nodes_scanned = {}

        self.mutex = RLock()
        self.server = server
        self.worker_num = worker_num

        # initial state
        node = initial_node or self.server.node
        self.nodes_toscan[node.id] = (node.ip, node.port)

    def _get_next_node(self):
        with self.mutex:
            if len(self.nodes_toscan) > 0:
                node_id, transport_address = self.nodes_toscan.popitem()
                self.nodes_scanning[node_id] = transport_address
                return Node(node_id, transport_address[0], transport_address[1])
            else:
                return None

    def _processed(self, node, neighbours):
        with self.mutex:
            del self.nodes_scanning[node.id]
            self.nodes_scanned[node.id] = {
                "transport": (node.ip, node.port), "neighbours": neighbours
            }
            for peer in neighbours:
                peer = Node(peer)
                if(peer.id not in self.nodes_scanning and
                        peer.id not in self.nodes_scanned):
                    self.nodes_toscan[peer.id] = (peer.ip, peer.port)

    def _worker(self):
        while True:

            # get next node to scan
            with self.mutex:
                node = self._get_next_node()
                num_scanning = len(self.nodes_scanning)
            if node is None or num_scanning == 0:
                return  # finished mapping the network

            hexid = binascii.hexlify(node.id)
            msg = "Finding neighbors of {0} at {1}:{2}"
            _log.info(msg.format(hexid, node.ip, node.port))

            # get neighbors
            d = self.server.protocol.callFindNode(node, node)
            d = util.default_defered(d, [])
            try:
                neighbours = util.wait_for_defered(d, timeout=QUERY_TIMEOUT)
            except TimeoutError:  # pragma: no cover
                msg = "Timeout when getting neighbors of %s"  # pragma: no cover
                self.log.debug(msg % hexid)  # pragma: no cover
                neighbours = []  # pragma: no cover

            # add to results and neighbours to scan
            self._processed(node, neighbours)

            time.sleep(0.002)

    def crawl_network(self):
        workers = [Thread(target=self._worker) for i in range(self.worker_num)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        return self.nodes_scanned
