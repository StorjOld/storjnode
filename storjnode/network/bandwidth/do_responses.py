"""
Handle responses from bandwidth test requests.
If we're getting responses it means we attempted to
initiate the request.
"""

from ast import literal_eval
import storjnode
import time
import copy
import zlib
import hashlib
from pyp2p.lib import parse_exception
from twisted.internet import reactor
from storjnode.network.bandwidth.constants import ONE_MB
import storjnode.storage.manager
from storjnode.network.message import verify_signature
from storjnode.util import parse_node_id_from_unl
from storjnode.util import list_to_ordered_dict
from timeit import default_timer as timer

_log = storjnode.log.getLogger(__name__)


def build_accept_handler(bt, req):
    # Handle accept transfer (for download requests.)
    def accept_handler(contract_id, src_unl, data_id, file_size):
        # Handler has expired.
        if accept_handler not in bt.handlers["accept"]:
            _log.debug("ALICE accept HANDLER EXPIRED")
            return -1

        if data_id != req[u"data_id"]:
            _log.debug("Data id != \a")
            return -2

        if src_unl != bt.test_node_unl:
            _log.debug("SRC UNL != \a")
            return -3

        # Invalid file_size request size for test.
        max_test_size = bt.increases[bt.max_increase]
        if req[u"file_size"] > max_test_size or not req[u"file_size"]:
            _log.debug("file size != \a")
            return -4

        # Remove this accept handler.
        bt.remove_handler("accept", accept_handler)

        return 1

    return accept_handler


def build_start_handler(bt, req):
    # Handle start transfer.
    def start_handler(client, con, contract_id):
        # Handler has expired.
        if start_handler not in bt.handlers["start"]:
            _log.debug("ALICE start HANDLER EXPIRED")
            return -1

        _log.debug("In upload start handler!")
        _log.debug("IN ALICE start handler")

        contract = bt.transfer.contracts[contract_id]
        _log.debug(contract)
        _log.debug(req[u"data_id"])

        # Check this corrosponds to something.
        if contract[u"data_id"] != req[u"data_id"]:
            _log.debug("Alice start: invalid data id")
            return -2

        # Determine test.
        if bt.transfer.get_direction(contract_id) == u"send":
            test = "upload"
            if contract[u"dest_unl"] != bt.test_node_unl:
                _log.debug("Alice upload: invalid src unl")
                return -3
        else:
            test = "download"

        # Set start time.
        bt.results[test]["start_time"] = timer()
        _log.debug(bt.results)

        return 1

    return start_handler


def build_completion_handler(bt, req, accept_handler):
    def completion_handler(client, found_contract_id, con):
        # Handler has expired.
        if completion_handler not in bt.handlers["complete"]:
            _log.debug("ALICE completion HANDLER EXPIRED")
            return -1

        # What test is this for?
        _log.debug("IN ALICE completion handler")
        contract = bt.transfer.contracts[found_contract_id]
        if contract[u"data_id"] != req[u"data_id"]:
            _log.debug("Alice data id not equal")
            return -2

        # Get direction of transfer.
        direction = bt.transfer.get_direction(
            found_contract_id
        )

        # Process test.
        if direction == u"send":
            _log.debug("\a")
            _log.debug("Upload transfer complete!")
            test = "upload"
            if contract[u"dest_unl"] != bt.test_node_unl:
                _log.debug("Alice dl: src unl incorrect.")
                return -3

            # Delete our copy of the file.
            storjnode.storage.manager.remove(
                bt.transfer.store_config,
                req[u"data_id"]
            )
        else:
            # Check the source of the request.
            _log.debug(contract[u"src_unl"])
            _log.debug(bt.test_node_unl)
            test = "download"
            if contract[u"src_unl"] != bt.test_node_unl:
                _log.debug("Alice dl: src unl incorrect.")
                return -4

            bt.transfer.remove_handler("accept", accept_handler)

            _log.debug("Alice download")

        bt.results[test]["end_time"] = timer()
        bt.results[test]["transferred"] = req[u"file_size"]
        _log.debug(bt.results)

        def finish_test():
            # Cleanup.
            _log.debug("TRANSFER ALL DONE!")
            _log.debug(bt.results)
            print(bt.results)

            # Convert results to bytes per second.
            results = bt.interpret_results()
            _log.debug("IN SUCCESS CALLBACK FOR BAND TESTS")
            _log.debug(results)
            _log.debug(bt.results)

            # Find latency (if available.)
            con = bt.transfer.net.con_by_unl(bt.test_node_unl)
            latency = None
            if con is not None:
                latency_test = bt.transfer.latency_tests.by_con(con)
                if latency_test is not None:
                    latency = latency_test.latency

            # Return results.
            active_test = bt.active_test
            bt.reset_state()
            results["latency"] = latency
            active_test.callback(results)

        if test == "download":
            # Check results.
            if bt.is_bad_results():
                _log.debug("Alice bad results.")
                return -1

            # Schedule next call if it returned too fast.
            if bt.is_bad_test() and bt.increasing_tests:
                # Calculate next test size.
                new_size = bt.increase_test_size()
                print("new size = " + str(new_size))
                if new_size == bt.test_size:
                    # Avoid DoS / endless loop.
                    _log.debug("DoS")
                    finish_test()
                    return -5

                # Increase max test size.
                if new_size > bt.max_increase:
                    bt.max_increase = new_size

                # Reset test state.
                _log.debug("SCHEDUALING NEW TRANSFER!")
                node_unl = copy.deepcopy(bt.test_node_unl)
                active_test = bt.active_test
                bt.reset_state()

                # Start new transfer.
                bt.start(
                    node_unl,
                    test_size=new_size
                )
                bt.active_test = active_test
            else:
                finish_test()

        return 1

    return completion_handler


def handle_responses_builder(bt):
    def handle_responses(node, msg):
        # Check message type.
        if type(msg) in [type(b"")]:
            msg = literal_eval(zlib.decompress(msg))
        msg = list_to_ordered_dict(msg)
        if msg[u"type"] != u"test_bandwidth_response":
            _log.debug("res: Invalid response")
            return -1

        # Transfer already active.
        if bt.test_node_unl != msg[u"requestee"]:
            _log.debug("res: transfer already active")
            return -2

        # Check we sent the request.
        req = msg[u"request"]
        _log.debug(req)
        msg_id = hashlib.sha256(str(req)).hexdigest()
        if msg_id not in bt.message_state:
            return -10
        if bt.message_state[msg_id] == "pending_response":
            bt.message_state[msg_id] = "pending_transfer"
        else:
            return -6
        msg_id = hashlib.sha256(str(msg)).hexdigest()
        if msg_id not in bt.message_state:
            bt.message_state[msg_id] = "pending_transfer"
        else:
            return -7

        # Check node IDs match.
        if req[u"test_node_unl"] != msg[u"requestee"]:
            _log.debug("res: node ids don't match")
            return -4

        # Check signature.
        valid_sig = verify_signature(
            msg[u"request"],
            bt.wif,
            bt.api.get_id()
        )

        # Quit if sig is invalid.
        if not valid_sig:
            _log.debug("res: our request sig was invalid")
            return -3

        # Check their sig.
        src_node_id = parse_node_id_from_unl(msg[u"requestee"])
        if not verify_signature(msg, bt.wif, src_node_id):
            _log.debug("res: their sig did not match")
            return -5

        # Set active node ID.
        bt.test_node_unl = msg[u"requestee"]

        # Clear response timeout.
        bt.response_timeout = None

        # Register accept handler.
        accept_handler = build_accept_handler(bt, req)
        bt.add_handler("accept", accept_handler)

        # Register start handler.
        start_handler = build_start_handler(bt, req)
        bt.add_handler("start", start_handler)

        # Send upload request to remote host!
        bt.transfer.bandwidth_tests[req[u"data_id"]] = 1
        contract_id = bt.transfer.data_request(
            "download",
            req[u"data_id"],
            req[u"file_size"],
            req[u"test_node_unl"]
        )

        # Fire error.
        def errback(err):
            _log.debug("do responses errback 1")
            _log.debug(repr(err))
            if bt.active_test is not None:
                bt.active_test.errback(err)

            bt.reset_state()
            return err

        # Register error handler for transfer.
        bt.transfer.defers[contract_id].addErrback(errback)

        # Build completion handler.
        completion_handler = build_completion_handler(
            bt,
            req,
            accept_handler
        )

        # Register completion handler.
        bt.add_handler("complete", completion_handler)

        _log.debug("res: got response")

    def try_wrapper(node, msg):
        try:
            _log.debug("Waiting for handle resposnes mutex")
            _log.debug("Got handle resposnes mutex")
            return handle_responses(node, msg)
        except (ValueError, KeyError, TypeError, zlib.error) as e:
            # _log.debug(e)
            # _log.debug(parse_exception(e))
            pass  # expected failure if unmatching message

    return try_wrapper
