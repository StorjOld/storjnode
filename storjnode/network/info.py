# from storjnode.common import CONFIG_PATH
# from storjnode import util
from storjnode import __version__
from storjnode.network import message
# from storjnode.storage import manager
# from storjnode import config
from collections import namedtuple


Info = namedtuple('Info', [
    'version',  # version of storgnode
    'total',  # total disc space reserved
    'used',  # disc space used reserved
    'peers'  # concatenated peer ids (one every 20 bytes)
])


def create_request(btctxstore, wif):
    return message.create(btctxstore, wif, "inforequest")


def read_request(btctxstore, msg):
    msg = message.read(btctxstore, msg)
    if msg is None or msg.body != "inforequest":
        return None
    return msg


def create_response(btctxstore, node_wif, total, used, peers):
    peers = reduce(lambda a, b: a + b, peers, b"")
    info = Info(__version__, total, used, peers)
    return message.create(btctxstore, node_wif, info)


def read_respones(btctxstore, nodeid, msg):

    # not a valid message
    if message.read(btctxstore, msg) is None:
        return None

    # check info given
    info = msg[1]
    if not isinstance(info, list) or len(info) != 4:
        return None
    # TODO version = info[0]

    total = info[1]
    used = info[2]

    # check capacity values
    if not all(isinstance(i, int) and i >= 0 for i in [total, used]):
        return None
    if used > total:
        return None

    # peers must be a list of valid node ids
    peers = info[3]
    if not isinstance(peers, bytes) and len(peers) % 20 == 0:
        return None

    msg[1] = Info(*info)
    return message.Message(*msg)


# def send_request(node, target):
#     body = "inforequest"
#     msg = message.create(node.server.btctxstore, node.get_key(), body)
#     return node.relay_message(util.address_to_node_id(target), msg)
#
#
# def send_response(node, request, config_path=CONFIG_PATH):
#     target = request["sender"]
#     config = config.get(node.server.btctxstore, config_path)
#     store_config = config.get("store")
#     body = {
#         "type": "info_response",
#         "request": request,
#         "capacity": manager.capacity(store_config),
#     }
#     msg = message.create(node.server.btctxstore, node.get_key(), body)
#     return node.relay_message(util.address_to_node_id(target), msg)
#
#
# def enable(node, config_path=CONFIG_PATH):
#
#     class _Handler(object):
#
#         def __init__(self, config_path=CONFIG_PATH):
#             self.config_path = config_path
#
#         def __call__(self, node, source_id, msg):
#             if valid_request(node, msg):
#                 send_response(node, msg, self.config_path)
#
#     return node.add_message_handler(_Handler(config_path=config_path))
