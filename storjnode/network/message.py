from collections import OrderedDict
from btctxstore import BtcTxStore
from storjnode.util import node_id_to_address
import sys
import binascii


def sign(contract, wif):
    if sys.version_info >= (3, 0, 0):
        msg = str(contract).encode("ascii")
    else:
        msg = str(contract)

    # This shouldn't already exist.
    if u"signature" in contract:
        del contract[u"signature"]

    api = BtcTxStore(testnet=False, dryrun=True)
    msg = binascii.hexlify(msg).decode("utf-8")
    sig = api.sign_data(wif, msg)

    if sys.version_info >= (3, 0, 0):
        contract[u"signature"] = sig.decode("utf-8")
    else:
        contract[u"signature"] = unicode(sig)

    return contract


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
