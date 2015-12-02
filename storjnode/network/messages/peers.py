from storjnode.network.messages import base


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
