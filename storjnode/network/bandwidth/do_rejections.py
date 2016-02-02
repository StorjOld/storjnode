import storjnode
import time
import hashlib
from pyp2p.lib import parse_exception
from collections import OrderedDict
from storjnode.util import parse_node_id_from_unl
from storjnode.util import ordered_dict_to_list
from storjnode.util import list_to_ordered_dict
from storjnode.network.message import sign, verify_signature
import zlib
from ast import literal_eval

_log = storjnode.log.getLogger(__name__)


def handle_rejections_builder(bt):
    # Handle bandwidth rejections.
    def handle_rejections(node, msg):
        _log.debug("In handle Rejections")
        _log.debug("In handle Rejections")

        # Check message type.
        if type(msg) in [type(b"")]:
            msg = literal_eval(zlib.decompress(msg))
        msg = list_to_ordered_dict(msg)
        if msg[u"type"] != u"test_bandwidth_rejection":
            return -1

        # Drop request if test not already active.
        our_unl = bt.transfer.net.unl.value
        src_node_id = parse_node_id_from_unl(msg[u"requestee"])
        if bt.test_node_unl is None:
            return -2

        # Check message id.
        msg_id = hashlib.sha256(str(msg)).hexdigest()
        if msg_id not in bt.message_state:
            bt.message_state[msg_id] = "rejected"
        else:
            return -3

        # Check they got our node unl right.
        if bt.test_node_unl != msg[u"requestee"]:
            _log.debug("req: they got our node unl wrong")
            return -4

        # Check their sig.
        if not verify_signature(msg, bt.wif, src_node_id):
            _log.debug("req: Invalid sig")
            return -5

        # Check our signature.
        valid_sig = verify_signature(
            msg[u"request"],
            bt.wif,
            bt.api.get_id()
        )
        if not valid_sig:
            return -6

        # Reset test state and call errback.
        if bt.active_test is not None:
            msg = "Bandwidth request was rejected"
            _log.debug(msg)
            bt.active_test.errback(Exception(msg))
            bt.reset_state()

    def try_wrapper(node, msg):
        try:
            _log.debug("Waiting for handle requests mutex")
            _log.debug("Gote handle requests mutex")
            return handle_rejections(node, msg)
        except (ValueError, KeyError, TypeError, zlib.error) as e:
            pass  # expected failure if unmatching message

    return try_wrapper
