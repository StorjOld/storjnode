"""
Code that executes to handle bandwidth test requests
(messages from other nodes to request starting a test.)
"""
import storjnode
import logging
import time
from collections import OrderedDict
from storjnode.network.bandwidth.constants import ONE_MB
from storjnode.util import parse_node_id_from_unl
from storjnode.util import ordered_dict_to_list
from storjnode.util import list_to_ordered_dict
from storjnode.network.message import sign, verify_signature

_log = storjnode.log.getLogger(__name__)


def build_start_handler(self, msg):
    # Update start time for download test.
    def start_handler(client, con, start_contract_id):
        # Handler has expired.
        if start_handler not in self.handlers["start"]:
            _log.debug("IN BOB START HANDLER EXPIRED")
            return -1

        _log.debug("IN BOB START HANDLER")
        contract = self.transfer.contracts[start_contract_id]
        if contract[u"data_id"] != msg[u"data_id"]:
            _log.debug("Bob data id not equal!")
            _log.debug("\a")
            return -2

        # Determine direction.
        direction = self.transfer.get_direction(
            start_contract_id
        )

        # Determine test.
        if direction == u"send":
            test = "upload"
        else:
            test = "download"

        # Set start time.
        self.results[test]["start_time"] = time.time()

        _log.debug(test)
        _log.debug("Downlaod start handler")
        _log.debug("nl")

        return 1

    return start_handler


def build_completion_handler(self, msg, accept_handler):
    # Update download test results.
    def completion_handler(client, found, con):
        # Handler has expired.
        if completion_handler not in self.handlers["complete"]:
            _log.debug("IN BOB COMPLETION HANDLER EXPIRED\a")
            return -1

        _log.debug("IN BOB COMPLETION HANDLER")
        contract = self.transfer.contracts[found]
        if contract[u"data_id"] != msg[u"data_id"]:
            _log.debug("Bob completion: invalid data id")
            return -2

        if self.transfer.get_direction(found) == u"send":
            test = "upload"
            if contract[u"dest_unl"] != self.test_node_unl:
                _log.debug("Bob upload: invalid src unl")
                _log.debug("\a")
                return -3
        else:
            test = "download"
            if contract[u"src_unl"] != self.test_node_unl:
                _log.debug("Alice dl: src unl incorrect.")
                return -4

            # Send download request to remote host!
            contract_id = self.transfer.data_request(
                "download",
                msg[u"data_id"],
                msg[u"file_size"],
                self.test_node_unl
            )

            # Fire error.
            def errback(ret):
                if self.active_test is not None:
                    self.active_test.errback(ret)

                self.reset_state()

            # Register error handler for transfer.
            if contract_id in self.transfer.defers:
                self.transfer.defers[contract_id].addErrback(errback)

        test_data_size = (self.test_size * ONE_MB)
        self.results[test]["end_time"] = time.time()
        self.results[test]["transferred"] = test_data_size

        if test == "upload":
            self.test_node_unl = None
            if self.is_bad_test():
                if self.is_bad_results():
                    self.reset_state()
                else:
                    self.test_size = self.increase_test_size()
            else:
                self.reset_state()

        _log.debug("\a")
        _log.debug("Bob transfer complete!")
        _log.debug(self.results)

        return 1

    return completion_handler


def build_accept_handler(self, msg):
    # Accept transfers.
    def accept_handler(contract_id, src_unl, data_id, file_size):
        # Handler has expired.
        if accept_handler not in self.handlers["accept"]:
            _log.debug("IN BOB ACCEPT HANDLER EXPIRED")
            return -1

        _log.debug("In download accept handler!")
        _log.debug(data_id)
        _log.debug(msg[u"data_id"])
        _log.debug("nl")
        _log.debug(self.test_node_unl)
        _log.debug(src_unl)
        _log.debug("nl")
        _log.debug(msg[u"file_size"])

        if data_id != msg[u"data_id"]:
            _log.debug("data id not = in bob accept\a")
            return -2

        # Invalid node making this connection.
        if self.test_node_unl != src_unl:
            _log.debug("unl not = in bob accept\a")
            return -3

        # Invalid file_size request size for test.
        test_data_size = (self.test_size * ONE_MB)
        if msg[u"file_size"] > (test_data_size + 1024):
            _log.debug("file size not = in bob accept\a")
            return -4

        # Build completion handler.
        completion_handler = build_completion_handler(
            self,
            msg,
            accept_handler
        )

        # Register complete handler.
        self.add_handler("complete", completion_handler)

        return 1

    return accept_handler


def handle_requests_builder(self):
    # Handle bandwidth requests.
    def handle_requests(node, src_node_id, msg):
        _log.debug("In handle requests")

        # Check message type.
        msg = list_to_ordered_dict(msg)
        if msg[u"type"] != u"test_bandwidth_request":
            _log.debug("req: Invalid request")
            return -1

        # Drop request if test already active.
        if self.test_node_unl is not None:
            _log.debug("req: test already active")
            return -2

        # Check they got our node unl right.
        our_unl = self.transfer.net.unl.value
        if our_unl != msg[u"test_node_unl"]:
            _log.debug("req: they got our node unl wrong")
            return -3

        # Don't connect to ourself.
        if our_unl == msg[u"requester"]:
            _log.debug("req: cannot connect back to ourself")
            return -5

        # Check sig.
        src_node_id = parse_node_id_from_unl(msg[u"requester"])
        if not verify_signature(msg, self.wif, src_node_id):
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
        res = sign(res, self.wif)

        # Save their node ID!
        self.test_node_unl = msg[u"requester"]

        # Add accept handler for bandwidth tests.
        accept_handler = build_accept_handler(self, msg)
        self.add_handler("accept", accept_handler)

        # Add start handler.
        start_handler = build_start_handler(self, msg)
        self.add_handler("start", start_handler)

        # Set start time.
        self.start_time = time.time()

        # Save data id.
        self.data_id = msg[u"data_id"]

        # Send request back to source.
        res = ordered_dict_to_list(res)
        self.api.relay_message(src_node_id, res)
        _log.debug("req: got request")
        return res

    def try_wrapper(node, src_node_id, msg):
        try:
            return handle_requests(node, src_node_id, msg)
        except (ValueError, KeyError) as e:
            _log.debug(e)
            _log.debug("Error in req")

    return try_wrapper
