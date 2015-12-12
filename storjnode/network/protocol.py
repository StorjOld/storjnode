import heapq
import operator
try:
    from Queue import Queue, Full  # py2
except ImportError:
    from queue import Queue, Full  # py3
from kademlia.protocol import KademliaProtocol
from kademlia.routing import RoutingTable
from kademlia.routing import TableTraverser
from kademlia.node import Node
import storjnode


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


_log = storjnode.log.getLogger(__name__)


class Protocol(KademliaProtocol):

    def __init__(self, *args, **kwargs):
        max_messages = kwargs.pop("max_messages")
        self.max_hop_limit = kwargs.pop("max_hop_limit")
        self.messages_relay = Queue(maxsize=max_messages)
        self.messages_received = Queue(maxsize=max_messages)
        KademliaProtocol.__init__(self, *args, **kwargs)
        self.log = storjnode.log.getLogger("kademlia.protocol")
        self.log.setLevel(60)
        self.noisy = False

    def has_messages(self):
        return not self.messages_received.empty()

    def get_messages(self):
        return storjnode.util.empty_queue(self.messages_received)

    def queue_relay_message(self, entry):
        try:
            self.messages_relay.put_nowait(entry)
            return True
        except Full:
            msg = "Relay message queue full, dropping message for %s"
            address = storjnode.util.node_id_to_address(entry["dest"])
            self.log.warning(msg % address)
            return False

    def queue_received_message(self, entry):
        try:
            self.messages_received.put_nowait(entry)
            return True
        except Full:
            self.log.warning("Received message queue full, dropping message.")
            return False

    def rpc_relay_message(self, sender, sender_id, dest_id,
                          hop_limit, message):
        # FIXME self.welcomeIfNewNode(Node(sender_id, sender[0], sender[1]))

        logargs = (sender, storjnode.util.node_id_to_address(sender_id),
                   storjnode.util.node_id_to_address(dest_id), hop_limit)
        msg = "Got relay message from {1} at {0} for {2} with limit {3}."
        self.log.debug(msg.format(*logargs))

        # message is for this node
        if dest_id == self.sourceNode.id:
            queued = self.queue_received_message({
                "source": None, "message": message
            })
            return (sender[0], sender[1]) if queued else None

        # invalid hop limit
        if not (0 < hop_limit <= self.max_hop_limit):
            msg = "Dropping relay message, bad hop limit {0}."
            self.log.debug(msg.format(hop_limit))
            return None

        # do not relay away from dest
        sender_distance = Node(sender_id).distanceTo(Node(dest_id))
        our_distance = self.sourceNode.distanceTo(Node(dest_id))
        if our_distance >= sender_distance:
            self.log.debug("Dropping relay message, self not closer to dest.")
            return None

        # add to relay queue
        queued = self.queue_relay_message({
            "dest": dest_id, "message": message, "hop_limit": hop_limit - 1
        })
        return (sender[0], sender[1]) if queued else None

    def rpc_direct_message(self, sender, sender_id, message):
        self.log.debug("Got direct message from {0} at {1}".format(
            storjnode.util.node_id_to_address(sender_id), sender
        ))
        source = Node(sender_id, sender[0], sender[1])
        # FIXME self.welcomeIfNewNode(source)
        queued = self.queue_received_message({
            "source": source, "message": message
        })
        return (sender[0], sender[1]) if queued else None

    def callRelayMessage(self, nodeToAsk, destid, hop_limit, message):
        address = (nodeToAsk.ip, nodeToAsk.port)
        self.log.debug("Sending relay message to {0}:{1}".format(*address))
        d = self.relay_message(address, self.sourceNode.id, destid,
                               hop_limit, message)
        return d.addCallback(self.handleCallResponse, nodeToAsk)

    def callDirectMessage(self, nodeToAsk, message):
        address = (nodeToAsk.ip, nodeToAsk.port)
        self.log.debug("Sending direct message to {0}:{1}".format(*address))
        d = self.direct_message(address, self.sourceNode.id, message)
        return d.addCallback(self.handleCallResponse, nodeToAsk)
