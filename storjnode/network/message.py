import umsgpack
import binascii
from collections import OrderedDict
from collections import namedtuple
from btctxstore import BtcTxStore
from storjnode.util import node_id_to_address
import sys
import binascii


Message = namedtuple('Message', ['sender', 'kind', 'body', 'signature'])


def create(btctxstore, wif, kind, body):
    address = btctxstore.get_address(wif)
    data = binascii.hexlify(umsgpack.packb([kind, body]))
    signature = btctxstore.sign_data(wif, data)
    return Message(address, kind, body, signature)


def read(btctxstore, message):
    # FIXME make sure body does not contain dicts
    if not isinstance(message, list) or len(message) != 4:
        return None
    msg = Message(*message)
    data = binascii.hexlify(umsgpack.packb([msg.kind, msg.body]))
    if btctxstore.verify_signature(msg.sender, msg.signature, data):
        return msg
    return None


def sign(dict_obj, wif):  # FIXME use create instead
    assert(isinstance(dict_obj, OrderedDict))
    if "signature" in dict_obj:
        del dict_obj["signature"]

    if sys.version_info >= (3, 0, 0):
        msg = str(dict_obj).encode("ascii")
    else:
        msg = str(dict_obj)

    # assert("signature" not in msg)  # must be unsigned
    # todo: fix this

    api = BtcTxStore(testnet=False, dryrun=True)
    msg = binascii.hexlify(msg).decode("utf-8")
    sig = api.sign_data(wif, msg)

    if sys.version_info >= (3, 0, 0):
        dict_obj[u"signature"] = sig.decode("utf-8")
    else:
        dict_obj[u"signature"] = unicode(sig)

    return dict_obj


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
