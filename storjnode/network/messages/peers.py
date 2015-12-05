from storjnode.network.messages import base
from storjnode.network.messages import signal


def create(btctxstore, node_wif, peers):
    peers = reduce(lambda a, b: a + b, peers, b"")
    return base.create(btctxstore, node_wif, "peers", peers)


def read(btctxstore, msg):

    # not a valid message
    msg = base.read(btctxstore, msg)
    if msg is None:
        return None

    # correct token
    if msg.token != "peers":
        return None

    peers = msg.body

    # must be a byte array of concatenated peer ids
    if not isinstance(peers, bytes):
        return None

    # one peer every 20 bytes
    if len(peers) % 20 != 0:
        return None

    return msg


def request(node, receiver):
    msg = signal.create(node.server.btctxstore,
                        node.get_key(), "request_peers")
    return node.relay_message(receiver, msg)


def enable(node):
    def handler(node, source_id, msg):
        request = signal.read(node.server.btctxstore, msg, "request_peers")
        if request is not None:
            peers = list(map(lambda n: n.id, node.get_neighbours()))
            msg = create(node.server.btctxstore, node.get_key(), peers)
            node.relay_message(request.sender, msg)
    return node.add_message_handler(handler)
