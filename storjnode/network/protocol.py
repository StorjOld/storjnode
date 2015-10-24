try:
    from Queue import Queue  # py2
except ImportError:
    from queue import Queue  # py3
from kademlia.protocol import KademliaProtocol
from kademlia.routing import RoutingTable
from kademlia.routing import TableTraverser
from kademlia.node import Node
import heapq
import operator
import logging


def _findNearest(self, node, k=None, exclude=None):
    k = k or self.ksize
    nodes = []
    for neighbor in TableTraverser(self, node):
        if exclude is None or not neighbor.sameHomeAs(exclude):
            heapq.heappush(nodes, (node.distanceTo(neighbor), neighbor))
        if len(nodes) == k:
            break

    return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))


RoutingTable.findNeighbors = _findNearest  # XXX hack find neighbors


class StorjProtocol(KademliaProtocol):

    def __init__(self, *args, **kwargs):
        self.messages_received = Queue()
        KademliaProtocol.__init__(self, *args, **kwargs)
        self.log = logging.getLogger(__name__)

    def rpc_message(self, sender, nodeid, message):
        source = Node(nodeid, sender[0], sender[1])
        self.messages_received.put({"source": source, "message": message})
        return (sender[0], sender[1])  # return (ip, port)

    def callMessage(self, nodeToAsk, message):
        address = (nodeToAsk.ip, nodeToAsk.port)
        self.log.debug("sending message to {0}:{1}".format(*address))
        d = self.message(address, self.sourceNode.id, message)
        return d.addCallback(self.handleCallResponse, nodeToAsk)
