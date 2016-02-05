import re
import random
import six
import platform
from collections import namedtuple
from storjnode import util
from storjnode.network.messages import base
from storjnode.network.messages import signal
from storjnode.storage import manager
from storjnode import __version__
from storjnode.log import getLogger


_log = getLogger(__name__)


Storage = namedtuple('Storage', ['total', 'used', 'free'])
Platform = namedtuple('Platform', ['system', 'release', 'version', 'machine'])


Network = namedtuple('Network', [
    'transport',  # (ip, port)
    'unl',        # unl string
    'is_public',  # True if node is publicly reachable otherwise False
])


Info = namedtuple('Info', [
    'version',  # storjnode version
    'storage',
    'network',
    'platform',
    'btcaddress',  # unencoded bytes
])


def create(btctxstore, node_wif, capacity,
           transport, unl, is_public, btcaddress):
    storage = Storage(**capacity)
    network = Network(transport, unl, is_public)
    plat = Platform(platform.system(), platform.release(),
                    platform.version(), platform.machine())
    info = Info(__version__, storage, network, plat,
                util.address_to_node_id(btcaddress))
    return base.create(btctxstore, node_wif, "info", info)


def _validate_network(network):
    if not isinstance(network, list):
        return False
    if len(network) != 3:
        return False
    transport, unl, is_public = network

    if not isinstance(is_public, bool):
        return False
    if not isinstance(unl, six.string_types):
        return False

    # check transport
    if not isinstance(transport, list):
        return False
    if len(transport) != 2:
        return False
    ip, port = transport
    if not util.valid_ip(ip):
        return False
    if not util.valid_port(port):
        return False

    return True


def _validate_storage(storage):
    if not isinstance(storage, list):
        return False
    if len(storage) != 3:
        return False
    if not all(isinstance(i, (int, long)) for i in storage):
        return False
    if not all(i >= 0 for i in storage):
        return False
    total, used, free = storage
    if used > total:
        return False
    if total - used != free:
        return False
    return True


def _validate_platform(plat):
    if not isinstance(plat, list):
        return False
    if len(plat) != 4:
        return False
    if not all([isinstance(prop, six.string_types) for prop in plat]):
        return False
    return True


def _validate_version(version):
    if not isinstance(version, six.string_types):
        return False
    if not re.match("^\d+\.\d+.\d+$", version):
        return False
    return True


def _validate_btcaddress(btcaddress):
    if not isinstance(btcaddress, six.binary_type):
        return False
    if len(btcaddress) != 20:  # 160 bytes
        return False
    return True


def read(btctxstore, msg):

    # not a valid message
    if base.read(btctxstore, msg) is None:
        return None

    # check token
    if msg[3] != "info":
        return None

    # check info given
    info = msg[4]
    if not isinstance(info, list):
        return None
    if len(info) != 5:
        return None
    version, storage, network, plat, btcaddress = info

    if not _validate_version(version):
        return None
    if not _validate_storage(storage):
        return None
    if not _validate_network(network):
        return None
    if not _validate_platform(plat):
        return None
    if not _validate_btcaddress(btcaddress):
        return None

    msg[4] = Info(version, Storage(*storage),
                  Network(*network), Platform(*plat), btcaddress)
    return base.Message(*msg)


def request(node, receiver):
    msg = signal.create(node.server.btctxstore, node.get_key(), "request_info")
    return node.relay_message(receiver, msg)


def _respond(node, receiver, config):
    print("In info respond")

    def on_error(err):
        print("In info respond unable to get transport info")
        _log.error(repr(err))
        return err

    def on_success(result):
        print("Info respond success: " + str(result))

        if not result:
            _log.warning("Couldn't get info for requested info message!")
            return
        capacity = manager.capacity(config["storage"])

        # get btcaddress
        if len(config["cold_storage"]) > 0:
            btcaddress = random.choice(config["cold_storage"])
        else:
            btcaddress = node.get_address()

        msg = create(node.server.btctxstore, node.get_key(),
                     capacity, result["wan"], result["unl"],
                     result["is_public"], btcaddress)
        return node.relay_message(receiver, msg)

    add_unl = not config["network"]["disable_data_transfer"]
    deferred = node.async_get_transport_info(add_unl=add_unl)
    return deferred.addCallback(on_success).addErrback(on_error)


def enable(node, config):

    class _Handler(object):

        def __init__(self, config):
            self.config = config

        def __call__(self, node, msg):
            request = signal.read(node.server.btctxstore, msg, "request_info")
            if request is not None:
                _respond(node, request.sender, self.config)
            else:
                print("request info is none")

    return node.add_message_handler(_Handler(config))
