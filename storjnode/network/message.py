from collections import OrderedDict
from btctxstore import BtcTxStore
from storjnode.util import node_id_to_address


def sign(msg, wif):
    assert(isinstance(msg, OrderedDict))
    assert("signature" not in msg)  # must be unsigned
    api = BtcTxStore(testnet=False, dryrun=True)
    msg[u"signature"] = api.sign_unicode(wif, str(msg))
    return msg


def verify_signature(msg, wif, node_id=None):
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
