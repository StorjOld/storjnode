"""
Handle responses from bandwidth test requests.
If we're getting responses it means we attempted to
initiate the request.
"""

import storjnode
import logging
import time
import copy
from storjnode.network.bandwidth.constants import ONE_MB
import storjnode.storage.manager
from storjnode.network.message import verify_signature
from storjnode.util import parse_node_id_from_unl
from storjnode.util import list_to_ordered_dict

_log = storjnode.log.getLogger(__name__)


def build_accept_handler(self, req):
    # Handle accept transfer (for download requests.)
    def accept_handler(contract_id, src_unl, data_id, file_size):
        # Handler has expired.
        if accept_handler not in self.handlers["accept"]:
            _log.debug("ALICE accept HANDLER EXPIRED")
            return -1

        if src_unl != self.test_node_unl:
            _log.debug("SRC UNL != \a")
            return 0

        if data_id != req[u"data_id"]:
            _log.debug("Data id != \a")
            return 0

        # Invalid file_size request size for test.
        test_data_size = (self.test_size * ONE_MB)
        if req[u"file_size"] > (test_data_size + 1024):
            _log.debug("file size != \a")
            return 0

        return 1

    return accept_handler


def build_start_handler(self, req):
    # Handle start transfer.
    def start_handler(client, con, contract_id):
        # Handler has expired.
        if start_handler not in self.handlers["start"]:
            _log.debug("ALICE start HANDLER EXPIRED")
            return -1

        _log.debug("In upload start handler!")
        _log.debug("IN ALICE start handler")

        contract = self.transfer.contracts[contract_id]
        _log.debug(contract)
        _log.debug(req[u"data_id"])

        # Check this corrosponds to something.
        if contract[u"data_id"] != req[u"data_id"]:
            _log.debug("Alice start: invalid data id")
            return 0

        # Determine test.
        if self.transfer.get_direction(contract_id) == u"send":
            test = "upload"
            if contract[u"dest_unl"] != self.test_node_unl:
                _log.debug("Alice upload: invalid src unl")
                return 0
        else:
            test = "download"

        # Set start time.
        self.results[test]["start_time"] = time.time()
        _log.debug(self.results)
        return 1

    return start_handler


def build_completion_handler(self, req, accept_handler):
    def completion_handler(client, found_contract_id, con):
        # Handler has expired.
        if completion_handler not in self.handlers["complete"]:
            _log.debug("ALICE completion HANDLER EXPIRED")
            return -1

        # What test is this for?
        _log.debug("IN ALICE completion handler")
        contract = self.transfer.contracts[found_contract_id]
        if contract[u"data_id"] != req[u"data_id"]:
            _log.debug("Alice data id not equal")
            return

        # Get direction of transfer.
        direction = self.transfer.get_direction(
            found_contract_id
        )

        # Process test.
        if direction == u"send":
            _log.debug("\a")
            _log.debug("Upload transfer complete!")
            test = "upload"
            if contract[u"dest_unl"] != self.test_node_unl:
                _log.debug("Alice dl: src unl incorrect.")
                return

            # Delete our copy of the file.
            storjnode.storage.manager.remove(
                self.transfer.store_config,
                req[u"data_id"]
            )
        else:
            # Check the source of the request.
            _log.debug(contract[u"src_unl"])
            _log.debug(self.test_node_unl)
            test = "download"
            if contract[u"src_unl"] != self.test_node_unl:
                _log.debug("Alice dl: src unl incorrect.")
                return

            self.transfer.remove_handler("accept", accept_handler)

            _log.debug("Alice download")

        self.results[test]["end_time"] = time.time()
        self.results[test]["transferred"] = req[u"file_size"]
        _log.debug(self.results)

        if test == "download":
            # Check results.
            if self.is_bad_results():
                _log.debug("Alice bad results.")
                return -1

            # Schedule next call if it returned too fast.
            if self.is_bad_test() and self.increasing_tests:
                # Reset test state.
                _log.debug("SCHEDUALING NEW TRANSFER!")
                node_unl = copy.deepcopy(self.test_node_unl)
                self.reset_state()

                # Calculate test size.
                new_size = self.increase_test_size()
                if new_size == self.test_size:
                    # Avoid DoS.
                    return
                else:
                    self.test_size = new_size

                # Start new transfer.
                self.start(
                    node_unl,
                    size=new_size
                )
            else:
                # Cleanup.
                _log.debug("TRANSFER ALL DONE!")
                _log.debug(self.results)

                # Convert results to bytes per second.
                speeds = self.interpret_results()

                # Return results.
                self.active_test.callback(speeds)

                # Reset test state.
                self.reset_state()

                # Reset active test.
                self.active_test = None

        return 1

    return completion_handler


def handle_responses_builder(self):
    def handle_responses(node, src_node_id, msg):
        # Check message type.
        msg = list_to_ordered_dict(msg)
        if msg[u"type"] != u"test_bandwidth_response":
            _log.debug("res: Invalid response")
            return

        # Transfer already active.
        if self.test_node_unl is not None:
            _log.debug("res: transfer already active")
            return

        # Check we sent the request.
        req = msg[u"request"]
        _log.debug(req)

        # Check signature.
        valid_sig = verify_signature(
            msg[u"request"],
            self.wif,
            self.api.get_id()
        )

        # Quit if sig is invalid.
        if not valid_sig:
            _log.debug("res: our request sig was invalid")
            return

        # Check node IDs match.
        if req[u"test_node_unl"] != msg[u"requestee"]:
            _log.debug("res: node ids don't match")
            return

        # Check their sig.
        src_node_id = parse_node_id_from_unl(msg[u"requestee"])
        if not verify_signature(msg, self.wif, src_node_id):
            _log.debug("res: their sig did not match")
            return

        # Set active node ID.
        self.test_node_unl = msg[u"requestee"]

        # Register accept handler.
        accept_handler = build_accept_handler(self, req)
        self.add_handler("accept", accept_handler)

        # Register start handler.
        start_handler = build_start_handler(self, req)
        self.add_handler("start", start_handler)

        # Send upload request to remote host!
        contract_id = self.transfer.data_request(
            "download",
            req[u"data_id"],
            req[u"file_size"],
            req[u"test_node_unl"]
        )

        # Fire error.
        def errback(ret):
            if self.active_test is not None:
                self.active_test.errback(ret)

            self.reset_state()

        # Register error handler for transfer.
        self.transfer.defers[contract_id].addErrback(errback)

        # Build completion handler.
        completion_handler = build_completion_handler(
            self,
            req,
            accept_handler
        )

        # Register completion handler.
        self.add_handler("complete", completion_handler)

        _log.debug("res: got response")

    def try_wrapper(node, src_node_id, msg):
        try:
            return handle_responses(node, src_node_id, msg)
        except (ValueError, KeyError) as e:
            _log.debug("Error in res")
            _log.debug(e)
            return

    return try_wrapper
