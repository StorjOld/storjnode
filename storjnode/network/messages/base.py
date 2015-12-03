import binascii
import base64
import umsgpack
from collections import namedtuple
from storjnode.util import node_id_to_address, address_to_node_id
from storjnode.common import PROTOCOL_VERSION
from storjnode.common import MAX_PACKAGE_DATA


MAX_MESSAGE_DATA = MAX_PACKAGE_DATA - 29  # max data - message call overhead


Message = namedtuple('Message', [
    'sender',   # 20 byte node id
    'version',  # protocol version of storjnode
    'token',    # to identify a specific message or message type
    'body',     # the message body
    'rawsig'    # 65 byte unencoded signature
])


class MaxSizeExceeded(Exception):
    pass


def create(btctxstore, node_wif, token, body):

    # FIXME make sure body does not contain dicts

    # sign message data (version + token + body)
    data = binascii.hexlify(umsgpack.packb([PROTOCOL_VERSION, token, body]))
    signature = btctxstore.sign_data(node_wif, data)

    # use compact unencoded data to conserve package bytes
    nodeid = address_to_node_id(btctxstore.get_address(node_wif))
    rawsig = base64.b64decode(signature)
    message = Message(nodeid, PROTOCOL_VERSION, token, body, rawsig)

    # check if message to large
    packed_message = umsgpack.packb(message)
    if len(packed_message) > MAX_MESSAGE_DATA:
        txt = "Message size {0} > {1} allowed."
        raise MaxSizeExceeded(
            txt.format(len(packed_message), MAX_MESSAGE_DATA)
        )

    return message


def read(btctxstore, message):
    # FIXME make sure body does not contain dicts

    if not isinstance(message, list):
        return None
    if len(message) != 5:
        return None
    msg = Message(*message)
    if not isinstance(msg.sender, bytes):
        return None
    if len(msg.sender) != 20:
        return None
    if not isinstance(msg.version, int):
        return None
    if msg.version < 0:
        return None
    # token and body must be checked by caller
    if not isinstance(msg.rawsig, bytes):
        return None
    if len(msg.rawsig) != 65:
        return None

    # verify signature
    address = node_id_to_address(msg.sender)
    signature = base64.b64encode(msg.rawsig)
    data = binascii.hexlify(umsgpack.packb([msg.version, msg.token, msg.body]))
    if btctxstore.verify_signature(address, signature, data):
        return msg
    return None
