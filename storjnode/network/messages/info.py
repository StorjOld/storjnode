import re
from collections import namedtuple
from storjnode.util import valid_ip, valid_port
from storjnode.network.messages import base
from storjnode.network.messages import signal
from storjnode.storage import manager
from storjnode import __version__
from storjnode.log import getLogger


_log = getLogger(__name__)

Storage = namedtuple('Storage', ['total', 'used', 'free'])


Network = namedtuple('Network', [
    'transport',  # (ip, port)
    'is_public',  # True if node is publicly reachable otherwise False
])


Info = namedtuple('Info', [
    'version',  # storjnode version
    'storage',
    'network',
    # TODO add platform (window, linux, mac, etc)
])


def create(btctxstore, node_wif, capacity, transport, is_public):
    storage = Storage(**capacity)
    network = Network(transport, is_public)
    info = Info(__version__, storage, network)
    return base.create(btctxstore, node_wif, "info", info)


def _validate_network(network):
    if not isinstance(network, list):
        return False
    if len(network) != 2:
        return False
    transport, is_public = network
    if not isinstance(is_public, bool):
        return False
    if not isinstance(transport, list):
        return False
    if len(transport) != 2:
        return False
    ip, port = transport
    if not valid_ip(ip):
        return False
    if not valid_port(port):
        return False
    return True


def _validate_storage(storage):
    if not isinstance(storage, list):
        return False
    if len(storage) != 3:
        return False
    if not all(isinstance(i, int) for i in storage):
        return False
    if not all(i >= 0 for i in storage):
        return False
    total, used, free = storage
    if used > total:
        return False
    if total - used != free:
        return False
    return True


def read(btctxstore, msg):

    # not a valid message
    if base.read(btctxstore, msg) is None:
        return None

    # check token
    if msg[2] != "info":
        return None

    # check info given
    info = msg[3]
    if not isinstance(info, list):
        return None
    if len(info) != 3:
        return None
    version, storage, network = info

    # check version
    if not isinstance(version, str):
        return None
    if not re.match("^\d+\.\d+.\d+$", version):
        return None

    if not _validate_storage(storage):
        return None
    if not _validate_network(network):  # TODO test it
        return None

    msg[3] = Info(version, Storage(*storage), Network(*network))
    return base.Message(*msg)


def request(node, receiver):
    msg = signal.create(node.server.btctxstore, node.get_key(), "request_info")
    return node.relay_message(receiver, msg)


def _respond(node, receiver, store_config):

    def handler(result):
        if not result:
            _log.warning("Couldn't get info for requested info message!")
            return
        capacity = manager.capacity(store_config)
        msg = create(node.server.btctxstore, node.get_key(),
                     capacity, result["wan"], result["wan"] == result["lan"])
        return node.relay_message(receiver, msg)

    node.async_get_transport_info().addCallback(handler)


def enable(node, store_config):

    class _Handler(object):

        def __init__(self, store_config):
            self.store_config = store_config

        def __call__(self, node, source_id, msg):
            request = signal.read(node.server.btctxstore, msg, "request_info")
            if request is not None:
                _respond(node, request.sender, self.store_config)

    return node.add_message_handler(_Handler(store_config))
