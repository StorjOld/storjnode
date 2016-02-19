"""
Not complete, don't add to __init__
"""

import hashlib
import storjnode
from decimal import Decimal
from collections import OrderedDict
import logging
import time
import zlib
import tempfile
import copy
import pyp2p
import storjnode.storage.manager
from storjnode.network.bandwidth.do_requests \
    import handle_requests_builder
from storjnode.network.bandwidth.do_responses \
    import handle_responses_builder
from storjnode.network.bandwidth.do_rejections \
    import handle_rejections_builder
from storjnode.storage.shard import get_hash
from storjnode.network.process_transfers import process_transfers
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.message import sign
from storjnode.util import address_to_node_id, parse_node_id_from_unl
from storjnode.util import generate_random_file, ordered_dict_to_list
from twisted.internet import defer
from btctxstore import BtcTxStore
from twisted.internet.task import LoopingCall
from storjnode.util import get_nonce


_log = storjnode.log.getLogger(__name__)


class BandwidthTest:
    def __init__(self, wif, transfer, api, increasing_tests=1, ONE_MB=1048576):
        # Binary wallet import key.
        self.wif = wif

        # A Node instance object (can also be pyp2p.dht_msg.DHT)
        self.api = api

        # A FileTransfer object.
        self.transfer = transfer

        # Boolean - whether to do successive tests if a test returns
        # too soon (i.e. increase size for fast connections.)
        self.increasing_tests = increasing_tests

        # The UNL of the remote node we're testing our bandwidth with.
        self.test_node_unl = None

        # A deferred representing the future result for the active test.
        self.active_test = defer.Deferred()

        # The data_id / hash of the current random file being transferred.
        self.data_id = None

        # Size of a MB.
        self.ONE_MB = ONE_MB

        # Size in MB of current test - will increase if increasing_tests
        # is enabled.
        self.test_size = self.ONE_MB  # MB

        # Stored in BYTES per second.
        self.results = self.setup_results()

        # Record old handlers for cleanup purposes.
        self.handlers = {
            "start": set(),
            "complete": set(),
            "accept": set()
        }

        # Listen for bandwidth requests + responses.
        self.handle_requests = handle_requests_builder(self)
        self.handle_responses = handle_responses_builder(self)
        self.handle_rejections = handle_rejections_builder(self)

        # When was the test first started?
        self.start_time = time.time()

        # Timeout bandwidth test after N seconds.
        self.test_timeout = 60 * 60

        # Based on passed tests.
        self.max_increase = self.ONE_MB

        # Protocol state.
        self.message_state = {}

        # Response timeout.
        self.response_timeout = None

        # Increase table for MB transfer size.
        self.increases = OrderedDict([
            [1 * self.ONE_MB, 5 * self.ONE_MB],
            [5 * self.ONE_MB, 10 * self.ONE_MB],
            [10 * self.ONE_MB, 20 * self.ONE_MB],
            [20 * self.ONE_MB, 50 * self.ONE_MB],
            [50 * self.ONE_MB, 100 * self.ONE_MB],
            [100 * self.ONE_MB, 200 * self.ONE_MB],
            [200 * self.ONE_MB, 512 * self.ONE_MB],
            [512 * self.ONE_MB, 1000 * self.ONE_MB],
            [1000 * self.ONE_MB, 2000 * self.ONE_MB],
            [2000 * self.ONE_MB, 3000 * self.ONE_MB],
            [3000 * self.ONE_MB, 4000 * self.ONE_MB],
            [4000 * self.ONE_MB, 5000 * self.ONE_MB],
            [5000 * self.ONE_MB, 10000 * self.ONE_MB],
            [10000 * self.ONE_MB, 10000 * self.ONE_MB],
        ])

    # Handle timeouts.
    def handle_timeout(self):
        # Response timed out.
        response_timeout = False
        if self.response_timeout is not None:
            if time.time() >= self.response_timeout:
                _log.debug("Response timeout = true")
                response_timeout = True

        # Test has been running too long - some other error occurred.
        duration = time.time() - self.start_time
        if duration >= self.test_timeout or response_timeout:
            _log.debug("ERROR: bandwidth test timed out!")
            if self.active_test is not None:
                _log.debug("active bandwidth test timeout!")
                self.active_test.errback(Exception("Timed out"))

            self.reset_state()

    # Allow this node to respond to bandwidth tests.
    def enable(self):
        self.api.add_message_handler(self.handle_requests)
        self.api.add_message_handler(self.handle_responses)
        self.api.add_message_handler(self.handle_rejections)

        return self

    def disable(self):
        self.api.remove_message_handler(self.handle_requests)
        self.api.remove_message_handler(self.handle_responses)
        self.api.remove_message_handler(self.handle_rejections)

        return self

    def increase_test_size(self):
        # Sanity check.
        if self.test_size not in self.increases:
            print("NOT IN INCREASES" + str(self.test_size))
            return self.test_size

        return self.increases[self.test_size]

    def add_handler(self, obj_type, handler):
        # Unknown handler.
        if obj_type not in self.handlers:
            raise Exception("Unknown handler.")

        # Record a copy of the handler for our records.
        self.handlers[obj_type].add(handler)

        # Now enable the handler for real.
        self.transfer.add_handler(obj_type, handler)

    def remove_handler(self, obj_type, handler):
        # Unknown handler.
        if obj_type not in self.handlers:
            raise Exception("Unknown handler.")

        # Record a copy of the handler for our records.
        if handler in self.handlers[obj_type]:
            self.handlers[obj_type].remove(handler)

        # Now enable the handler for real.
        if handler in self.transfer.handlers[obj_type]:
            self.transfer.remove_handler(obj_type, handler)

    def setup_results(self):
        results = {
            "upload": {
                "transferred": int(0),
                "start_time": int(0),
                "end_time": int(0)
            },
            "download": {
                "transferred": int(0),
                "start_time": int(0),
                "end_time": int(0)
            }
        }

        return results

    def reset_state(self):
        # Reset init state.
        self.test_size = self.ONE_MB
        self.active_test = None
        self.response_timeout = None
        self.results = self.setup_results()
        self.test_node_unl = None
        self.start_time = time.time()
        self.handlers = {
            "accept": set(),
            "complete": set(),
            "start": set()
        }

        self.cleanup_test_shards()
        self.transfer.bandwidth.save_monthly_usage()

    def cleanup_test_shards(self):
        # Cleanup test shard.
        if self.data_id is not None:
            storjnode.storage.manager.remove(
                self.transfer.store_config,
                self.data_id
            )

            self.data_id = None

    def interpret_results(self):
        speeds = {}
        for test in list(self.results):
            # Seconds.
            start_time = self.results[test]["start_time"]
            end_time = self.results[test]["end_time"]
            seconds = Decimal(end_time - start_time)
            if seconds == Decimal(0):
                # Avoid divide by zero.
                seconds = 1
            transferred = Decimal(self.results[test]["transferred"])
            speeds[test] = int(transferred / seconds)

        return speeds

    def is_bad_results(self):
        for test in list(self.results):
            # Bad start time.
            start_time = self.results[test]["start_time"]
            if not start_time:
                return 1

            # Bad end time.
            end_time = self.results[test]["end_time"]
            if not end_time:
                return 1

            # Bad transfer size.
            transferred = self.results[test]["transferred"]
            if not transferred:
                return 1

        return 0

    def is_bad_test(self, threshold=20):
        for test in list(self.results):
            start_time = self.results[test]["start_time"]
            end_time = self.results[test]["end_time"]
            if not start_time:
                _log.debug("Invalid start time")
                print("invalid start time !" + str(start_time))
                return 0

            if not end_time:
                _log.debug("Invalid end time")
                print("invalid end time" + str(end_time))
                return 0

            duration = end_time - start_time
            print("Btest duration" + str(duration))
            if duration < threshold:
                return 1

        return 0

    def start(self, node_unl, test_size=None, timeout=None):
        """
        :param node_unl: UNL of target
        :param test_size: MB to send in transfer
        :param timeout: when should a test be considered a failure?
        :return: deferred with test results
        """

        _log.debug("attempting to start btest")

        # Any tests currently in progress?
        if self.test_node_unl is not None:
            print("test already in progress")
            _log.debug("test already in progress")
            d = defer.Deferred()
            d.errback(Exception("Test already in progress"))
            return d
        else:
            self.test_node_unl = node_unl

        # Reset test state
        self.test_size = test_size or self.ONE_MB

        # Set timeout.
        self.test_timeout = timeout or self.test_timeout

        # Generate random file to upload.
        shard = generate_random_file(self.test_size)

        # Hash partial content.
        self.data_id = get_hash(shard).decode("utf-8")
        _log.debug("FINGER_log.debug HASH")
        _log.debug(self.data_id)

        # Reset deferred.
        self.active_test = defer.Deferred()

        # File meta data.
        meta = OrderedDict([
            (u"file_size", self.test_size),
            (u"algorithm", u"sha256"),
            (u"hash", self.data_id.decode("utf-8"))
        ])

        _log.debug("UNL")
        _log.debug(self.transfer.net.unl.value)

        _log.debug("META")
        _log.debug(meta)

        # Sign meta data.
        sig = sign(meta, self.wif)[u"signature"]

        _log.debug("SIG")
        _log.debug(sig)

        # Add file to storage.
        try:
            storjnode.storage.manager.add(
                self.transfer.store_config,
                shard,
                self.data_id.encode("ascii"),
                "move"
            )
        except MemoryError:
            _log.debug("memory error")
            self.reset_state()
            return

        # Build bandwidth test request.
        req = OrderedDict([
            (u"type", u"test_bandwidth_request"),
            (u"timestamp", int(time.time())),
            (u"nonce", get_nonce()),
            (u"requester", self.transfer.net.unl.value),
            (u"test_node_unl", node_unl),
            (u"data_id", self.data_id),
            (u"file_size", self.test_size)
        ])

        # Sign request.
        req = sign(req, self.wif)

        # Identify request.
        msg_id = hashlib.sha256(str(req)).hexdigest()
        self.message_state[msg_id] = "pending_response"

        # Pack request.
        node_id = parse_node_id_from_unl(node_unl)
        req = ordered_dict_to_list(req)
        req = zlib.compress(str(req))
        self.api.repeat_relay_message(node_id, req)

        # Set start time.
        self.start_time = time.time()

        # Set response timeout time.
        self.response_timeout = time.time() + 120

        _log.debug("btest scheduled")

        # Return deferred.
        return self.active_test
