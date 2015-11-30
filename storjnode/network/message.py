import base64
import umsgpack
import binascii
from collections import OrderedDict
from collections import namedtuple
from btctxstore import BtcTxStore
from storjnode.util import node_id_to_address, address_to_node_id


Message = namedtuple('Message', ['sender', 'kind', 'body', 'rawsig'])


def create(btctxstore, node_wif, kind, body):

    # sign data in serialized form so unpacking is not required
    data = binascii.hexlify(umsgpack.packb([kind, body]))
    signature = btctxstore.sign_data(node_wif, data)

    # use compact unencoded data to conserve package bytes
    nodeid = address_to_node_id(btctxstore.get_address(node_wif))
    rawsig = base64.b64decode(signature)

    return Message(nodeid, kind, body, rawsig)


def read(btctxstore, message):
    # FIXME make sure body does not contain dicts
    if not isinstance(message, list) or len(message) != 4:
        return None
    msg = Message(*message)

    data = binascii.hexlify(umsgpack.packb([msg.kind, msg.body]))

    # check if valid nodeid
    if not isinstance(msg.sender, bytes) or len(msg.sender) != 20:
        return None

    # check if valid rawsig
    if not isinstance(msg.rawsig, bytes) or len(msg.rawsig) != 65:
        return None

    # verify signature
    address = node_id_to_address(msg.sender)
    signature = base64.b64encode(msg.rawsig)
    if btctxstore.verify_signature(address, signature, data):
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
