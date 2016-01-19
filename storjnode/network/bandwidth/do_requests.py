"""
Code that executes to handle bandwidth test requests
(messages from other nodes to request starting a test.)
"""
import storjnode
import time
import hashlib
from collections import OrderedDict
from storjnode.network.bandwidth.constants import ONE_MB
from storjnode.util import parse_node_id_from_unl
from storjnode.util import ordered_dict_to_list
from storjnode.util import list_to_ordered_dict
from storjnode.network.message import sign, verify_signature
import zlib
from ast import literal_eval

_log = storjnode.log.getLogger(__name__)


def build_start_handler(bandwidth_test, msg):
    # Update start time for download test.
    def start_handler(client, con, start_contract_id):
        # Handler has expired.
        if start_handler not in bandwidth_test.handlers["start"]:
            _log.debug("IN BOB START HANDLER EXPIRED")
            return -1

        _log.debug("IN BOB START HANDLER")
        contract = bandwidth_test.transfer.contracts[start_contract_id]
        if contract[u"data_id"] != msg[u"data_id"]:
            _log.debug("Bob data id not equal!")
            _log.debug("\a")
            return -2

        # Determine direction.
        direction = bandwidth_test.transfer.get_direction(
            start_contract_id
        )

        # Determine test.
        if direction == u"send":
            test = "upload"
        else:
            test = "download"

        # Set start time.
        bandwidth_test.results[test]["start_time"] = time.time()

        _log.debug(test)
        _log.debug("Downlaod start handler")
        _log.debug("nl")

        return 1

    return start_handler


def build_completion_handler(bandwidth_test, msg, accept_handler):
    # Update download test results.
    def completion_handler(client, found, con):
        # Handler has expired.
        if completion_handler not in bandwidth_test.handlers["complete"]:
            _log.debug("IN BOB COMPLETION HANDLER EXPIRED\a")
            return -1

        _log.debug("IN BOB COMPLETION HANDLER")
        contract = bandwidth_test.transfer.contracts[found]
        if contract[u"data_id"] != msg[u"data_id"]:
            _log.debug("Bob completion: invalid data id")
            return -2

        if bandwidth_test.transfer.get_direction(found) == u"send":
            test = "upload"
            if contract[u"dest_unl"] != bandwidth_test.test_node_unl:
                _log.debug("Bob upload: invalid src unl")
                _log.debug("\a")
                return -3
        else:
            test = "download"
            if contract[u"src_unl"] != bandwidth_test.test_node_unl:
                _log.debug("Alice dl: src unl incorrect.")
                return -4

            # Send download request to remote host!
            contract_id = bandwidth_test.transfer.data_request(
                "download",
                msg[u"data_id"],
                msg[u"file_size"],
                bandwidth_test.test_node_unl
            )

            # Fire error.
            def errback(err):
                _log.debug("do requests errback 1")
                _log.debug(repr(err))
                if bandwidth_test.active_test is not None:
                    bandwidth_test.active_test.errback(err)

                bandwidth_test.reset_state()
                return err

            # Complete.
            def success(ret):
                bandwidth_test.reset_state()
                return ret

            # Register error handler for transfer.
            if contract_id in bandwidth_test.transfer.defers:
                bandwidth_test.transfer.defers[contract_id].addErrback(errback)
                #bandwidth_test.transfer.defers[contract_id].addCallback(success)

        test_data_size = (bandwidth_test.test_size * ONE_MB)
        bandwidth_test.results[test]["end_time"] = time.time()
        bandwidth_test.results[test]["transferred"] = test_data_size

        if test == "upload":
            # Is there a need to schedule a new test?
            if bandwidth_test.is_bad_test():
                if bandwidth_test.is_bad_results():
                    bandwidth_test.reset_state()
                else:
                    # If it's already maxed: it won't accept
                    # any new requests.
                    bandwidth_test.test_size = bandwidth_test.increase_test_size()
            else:
                bandwidth_test.reset_state()

        _log.debug("\a")
        _log.debug("Bob transfer complete!")
        _log.debug(bandwidth_test.results)

        return 1

    return completion_handler


def build_accept_handler(bandwidth_test, msg):
    # Accept transfers.
    def accept_handler(contract_id, src_unl, data_id, file_size):
        # Handler has expired.
        if accept_handler not in bandwidth_test.handlers["accept"]:
            _log.debug("IN BOB ACCEPT HANDLER EXPIRED")
            return -1

        _log.debug("In download accept handler!")
        _log.debug(data_id)
        _log.debug(msg[u"data_id"])
        _log.debug("nl")
        _log.debug(bandwidth_test.test_node_unl)
        _log.debug(src_unl)
        _log.debug("nl")
        _log.debug(msg[u"file_size"])

        if data_id != msg[u"data_id"]:
            _log.debug("data id not = in bob accept\a")
            return -2

        # Invalid node making this connection.
        if bandwidth_test.test_node_unl != src_unl:
            _log.debug("unl not = in bob accept\a")
            return -3

        # Invalid file_size request size for test.
        test_data_size = (bandwidth_test.test_size * ONE_MB)
        if msg[u"file_size"] > (test_data_size + 1024):
            _log.debug(str(msg[u"file_size"]))
            _log.debug(str(test_data_size))
            _log.debug("file size not = in bob accept\a")
            return -4

        # Build completion handler.
        completion_handler = build_completion_handler(
            bandwidth_test,
            msg,
            accept_handler
        )

        # Register complete handler.
        bandwidth_test.add_handler("complete", completion_handler)

        # Remove this accept handler.
        bandwidth_test.api.remove_transfer_request_handler(accept_handler)
        bandwidth_test.remove_handler("accept", accept_handler)

        return 1

    return accept_handler


def handle_requests_builder(bandwidth_test):
    # Handle bandwidth requests.
    def handle_requests(node, msg):
        _log.debug("In handle requests")

        # Check message type.
        if type(msg) in [type(b"")]:
            msg = literal_eval(zlib.decompress(msg))
        msg = list_to_ordered_dict(msg)
        if msg[u"type"] != u"test_bandwidth_request":
            return -1

        # Drop request if test already active.
        if bandwidth_test.test_node_unl is not None:
            if bandwidth_test.test_node_unl != msg[u"requester"]:
                _log.debug("req: test already active")
                return -2

        # Check message id.
        msg_id = hashlib.sha256(str(msg)).hexdigest()
        if msg_id not in bandwidth_test.message_state:
           bandwidth_test.message_state[msg_id] = "pending_transfer"
        else:
            return -5

        # Check they got our node unl right.
        our_unl = bandwidth_test.transfer.net.unl.value
        if our_unl != msg[u"test_node_unl"]:
            _log.debug("req: they got our node unl wrong")
            return -3

        # Check sig.
        src_node_id = parse_node_id_from_unl(msg[u"requester"])
        if not verify_signature(msg, bandwidth_test.wif, src_node_id):
            _log.debug("req: Invalid sig")
            return -4

        # Build response.
        res = OrderedDict([
            (u"type", u"test_bandwidth_response"),
            (u"timestamp", time.time()),
            (u"requestee", our_unl),
            (u"request", msg)
        ])

        # Sign response
        res = sign(res, bandwidth_test.wif)

        # Save their node ID!
        bandwidth_test.test_node_unl = msg[u"requester"]

        # Add accept handler for bandwidth tests.
        accept_handler = build_accept_handler(bandwidth_test, msg)
        bandwidth_test.add_handler("accept", accept_handler)

        # Add start handler.
        start_handler = build_start_handler(bandwidth_test, msg)
        bandwidth_test.add_handler("start", start_handler)

        # Set start time.
        bandwidth_test.start_time = time.time()

        # Save data id.
        bandwidth_test.data_id = msg[u"data_id"]

        # Send request back to source.
        res = ordered_dict_to_list(res)
        res = zlib.compress(str(res))
        bandwidth_test.api.repeat_relay_message(src_node_id, res)
        _log.debug("req: got request")

        # Return results.
        return res

    def try_wrapper(node, msg):
        try:
            _log.debug("Waiting for handle requests mutex")
            with bandwidth_test.mutex:
                _log.debug("Got handle requests mutex")
                return handle_requests(node, msg)
        except (ValueError, KeyError, TypeError, zlib.error) as e:
            _log.error("Error in req: {0}".format(repr(e)))

    return try_wrapper
