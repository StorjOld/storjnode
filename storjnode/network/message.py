from collections import OrderedDict
from collections import namedtuple
from btctxstore import BtcTxStore
from storjnode.util import node_id_to_address


Message = namedtuple('Message', ['sender', 'kind', 'body', 'signature'])


def create(btctxstore, wif, kind, body):
    address = btctxstore.get_address(wif)
    signature = btctxstore.sign_unicode(wif, str(kind) + str(body))
    return Message(address, kind, body, signature)


def read(btctxstore, message):
    # FIXME make sure body does not contain dicts
    if not isinstance(message, list) or len(message) != 4:
        return None
    msg = Message(*message)
    if btctxstore.verify_signature_unicode(msg.sender, msg.signature,
                                           str(msg.kind) + str(msg.body)):
        return msg
    return None


def sign(msg, wif):  # FIXME use create instead
    assert(isinstance(msg, OrderedDict))
    assert("signature" not in msg)  # must be unsigned
    api = BtcTxStore(testnet=False, dryrun=True)
    msg[u"signature"] = api.sign_unicode(wif, str(msg))
    return msg


def verify_signature(msg, wif, node_id=None):  # FIXME use read instead
    assert(isinstance(msg, OrderedDict))

    if u"signature" not in msg:
        return 0

    msg = msg.copy()  # work on a copy for thread saftey
    sig = msg.pop("signature")

    # Use our address.
    api = BtcTxStore(testnet=False, dryrun=True)
    try:
        if node_id is None:
            address = api.get_address(wif)
            ret = api.verify_signature_unicode(address, sig, str(msg))
        else:
            address = node_id_to_address(node_id)
            ret = api.verify_signature_unicode(address, sig, str(msg))
    except TypeError:
        return 0

    return ret
