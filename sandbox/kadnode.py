import sys
from twisted.internet import reactor
from twisted.python import log
from storjkademlia.network import Server


import heapq
import operator
from storjkademlia.routing import RoutingTable
from storjkademlia.routing import TableTraverser
from storjnode.storage.dht import Storage


def _findNearest(self, node, k=None, exclude=None):
    k = k or self.ksize
    nodes = []
    for neighbor in TableTraverser(self, node):
        if exclude is None or not neighbor.sameHomeAs(exclude):
            heapq.heappush(nodes, (node.distanceTo(neighbor), neighbor))
        if len(nodes) == k:
            break

    return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))


RoutingTable.findNeighbors = _findNearest  # XXX monkey patch find neighbors


log.startLogging(sys.stdout)


bootstrap_nodes = [
    ("104.236.1.59", 4653),     # storj stable
    ("104.236.1.59", 59744),    # storj stable
    ("159.203.64.230", 4653),   # storj develop
    ("159.203.64.230", 25933),  # storj develop
    ("78.46.188.55", 4653),     # F483's server
    ("78.46.188.55", 16851),    # F483's server
    ("158.69.201.105", 6770),   # Rendezvous server 1
    ("158.69.201.105", 63076),  # Rendezvous server 1
    ("162.218.239.6", 35839),   # IPXCORE:
    ("162.218.239.6", 38682),   # IPXCORE:
    ("192.187.97.131", 10322),  # NAT test node
    ("192.187.97.131", 58825),  # NAT test node
    ("185.86.149.128", 20560),  # Rendezvous 2
    ("185.86.149.128", 56701),  # Rendezvous 2
    ("185.61.148.22", 18825),   # dht msg 2
    ("185.61.148.22", 25029),   # dht msg 2
]


server = Server(storage=Storage())
server.protocol.noisy = True
server.listen(8469)
server.bootstrap(bootstrap_nodes)

reactor.run()
