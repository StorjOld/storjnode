from storjnode.common import CONFIG_PATH
from storjnode import util
from storjnode.network import message
from storjnode.storage import manager
from storjnode import config
from collections import namedtuple


Info = namedtuple('Info', ['request', 'capacity', 'peers'])  # TODO add version
Capacity = namedtuple('Capacity', ['total', 'used', 'free'])


def create_request(btctxstore, wif):
    return message.create(btctxstore, wif, "inforequest", None)


def read_request(btctxstore, msg):
    msg = message.read(btctxstore, msg)
    if msg is None or msg.kind != "inforequest" or msg.body is not None:
        return None
    return msg


def create_response(btctxstore, wif, request, total, used, free, peers):
    capacity = [total, used, free]
    return message.create(btctxstore, wif, "info", [request, capacity, peers])


def read_respones(btctxstore, address, msg):
    msg = message.read(btctxstore, msg)
    if msg is None or msg.kind != "info":
        return None

    # check info given
    if not isinstance(msg.body, list) or len(msg.body) != 3:
        return None
    msg.body = Info(*msg.body)

    # invalid request
    msg.body.request = read_request(btctxstore, msg.body.request)
    if msg.body.request is None:
        return None

    # we did not send the original request
    if msg.body.request.sender != address:
        return None

    # check capacity given
    if not isinstance(msg.body.capacity, list) or len(msg.body.capacity) != 3:
        return None

    # check capacity values >= 0
    if not all(isinstance(i, int) and i >= 0 for i in msg.body.capacity):
        return None
    msg.body.capacity = Capacity(*msg.body.capacity)

    # peers must be a list of valid addresses
    if not isinstance(msg.body.peers, list):
        return None
    if not all(btctxstore.validate_address(p) for p in msg.body.peers):
        return None

    return msg


def send_request(node, target):
    body = "inforequest"
    msg = message.create(node.server.btctxstore, node.get_key(), body)
    return node.relay_message(util.address_to_node_id(target), msg)


def send_response(node, request, config_path=CONFIG_PATH):
    target = request["sender"]
    store_config = config.get(node.server.btctxstore, config_path).get("store")
    body = {
        "type": "info_response",
        "request": request,
        "capacity": manager.capacity(store_config),
    }
    msg = message.create(node.server.btctxstore, node.get_key(), body)
    return node.relay_message(util.address_to_node_id(target), msg)


def enable(node, config_path=CONFIG_PATH):

    class _Handler(object):

        def __init__(self, config_path=CONFIG_PATH):
            self.config_path = config_path

        def __call__(self, node, source_id, msg):
            if valid_request(node, msg):
                send_response(node, msg, self.config_path)

    return node.add_message_handler(_Handler(config_path=config_path))
