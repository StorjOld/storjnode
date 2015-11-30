"""
Not complete, don't add to __init__
"""


from decimal import Decimal
from collections import OrderedDict
import json
import logging
import time
import tempfile
import pyp2p
import copy
import os
import storjnode.storage.manager
from storjnode.storage.shard import get_hash
from storjnode.network.process_transfers import process_transfers
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.message import sign, verify_signature
from storjnode.util import address_to_node_id, parse_node_id_from_unl, address_to_node_id, parse_node_id_from_unl, generate_random_file
from twisted.internet import defer
from btctxstore import BtcTxStore
from twisted.internet.task import LoopingCall
from crochet import setup
setup()

_log = logging.getLogger(__name__)
_log.setLevel("DEBUG")

ONE_MB = 1048576


class BandwidthTest():
    def __init__(self, wif, transfer, api):
        self.wif = wif
        self.api = api
        self.transfer = transfer
        self.test_node_unl = None
        self.active_test = defer.Deferred()
        self.test_size = 1 # MB

        # Stored in BYTES per second.
        self.results = {
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

        # Listen for bandwidth requests + responses.
        handle_requests = self.handle_requests_builder()
        handle_responses = self.handle_responses_builder()
        self.api.add_message_handler(handle_requests)
        self.api.add_message_handler(handle_responses)

        # Timeout bandwidth test after 5 minutes.
        self.start_time = 0
        def timeout():
            duration = time.time() - self.start_time
            if duration >= 300:
                if self.active_test is not None:
                    self.active_test.errback(Exception("Timed out"))
                    self.active_test = None
                    self.test_node_unl = None

                self.start_time = 0

        # Schedule timeout.
        LoopingCall(timeout).start(60, now=True)

    def handle_requests_builder(self):
        # Handle bandwidth requests.
        def handle_requests(node, src_node_id, msg):
            try:
                _log.debug("In handle requests")

                # Check message type.
                msg = json.loads(msg, object_pairs_hook=OrderedDict)
                if msg[u"type"] != u"test_bandwidth_request":
                    _log.debug("req: Invalid request")
                    return

                # Drop request if test already active.
                if self.test_node_unl is not None:
                    _log.debug("req: test already active")
                    return

                # Check sig.
                src_node_id = parse_node_id_from_unl(msg[u"requester"])
                if not verify_signature(msg, self.wif, src_node_id):
                    _log.debug("req: Invalid sig")
                    return

                # Build response.
                our_unl = self.transfer.net.unl.value
                res = OrderedDict([
                    (u"type", u"test_bandwidth_response"),
                    (u"timestamp", int(time.time())),
                    (u"requestee", our_unl),
                    (u"request", msg)
                ])

                # Check they got our node ID right.
                if our_unl != msg[u"test_node_unl"]:
                    _log.debug("req: they got our node id wrong")
                    return

                # Sign response
                res = sign(res, self.wif)

                # Save their node ID!
                self.test_node_unl = msg[u"requester"]

                # Accept transfers.
                def accept_handler(contract_id, src_unl, data_id, file_size):
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
                        return 0

                    # Invalid node making this connection.
                    if self.test_node_unl != src_unl:
                        _log.debug("unl not = in bob accept\a")
                        return 0

                    # Invalid file_size request size for test.
                    test_data_size = (self.test_size * ONE_MB)
                    if msg[u"file_size"] > (test_data_size + 1024):
                        _log.debug("file size not = in bob accept\a")
                        return 0

                    # Update download test results.
                    def completion_handler(client, found_contract_id, con):
                        contract = self.transfer.contracts[found_contract_id]
                        if contract[u"data_id"] != msg[u"data_id"]:
                            return

                        if self.transfer.get_direction(found_contract_id) == u"send":
                            test = "upload"
                            if contract[u"dest_unl"] != self.test_node_unl:
                                _log.debug("Bob upload: invalid src unl")
                                _log.debug("\a")
                                return 0

                            self.test_node_unl = None
                            self.transfer.remove_handler("accept", accept_handler)
                        else:
                            test = "download"
                            if contract[u"src_unl"] != self.test_node_unl:
                                _log.debug("Alice dl: src unl incorrect.")
                                return 0

                            # Send download request to remote host!
                            self.transfer.data_request(
                                "download",
                                msg[u"data_id"],
                                msg[u"file_size"],
                                self.test_node_unl
                            )

                        self.results[test]["end_time"] = int(time.time())
                        self.results[test]["transferred"] = test_data_size

                        _log.debug("\a")
                        _log.debug("Bob transfer complete!")
                        _log.debug(self.results)

                        if test == "upload":
                            return -1
                        else:
                            return 1

                    # Register complete handler.
                    self.transfer.add_handler("complete", completion_handler)

                    return 1

                # Add accept handler for bandwidth tests.
                self.transfer.add_handler("accept", accept_handler)

                # Update start time for download test.
                def start_handler(client, con, start_contract_id):
                    _log.debug("IN BOB START HANDLER")
                    contract = self.transfer.contracts[start_contract_id]
                    if contract[u"data_id"] != msg[u"data_id"]:
                        _log.debug("Bob data id not equal!")
                        _log.debug("\a")
                        return 0

                    # Determine test.
                    if self.transfer.get_direction(start_contract_id) == u"send":
                        test = "upload"
                    else:
                        test = "download"

                    # Set start time.
                    self.results[test]["start_time"] = int(time.time())

                    # Delete handler.
                    if test == "upload":
                        return -1

                    _log.debug(test)
                    _log.debug("Downlaod start handler")
                    _log.debug("nl")

                    return 1

                # Add start handler.
                self.transfer.add_handler("start", start_handler)

                # Set start time.
                self.start_time = time.time()

                # Send request back to source.
                res = json.dumps(res, ensure_ascii=True)
                self.api.relay_message(src_node_id, res)
                _log.debug("req: got request")
            except (ValueError, KeyError) as e:
                _log.debug(e)
                _log.debug("Error in req")

        return handle_requests

    def handle_responses_builder(self):
        def handle_responses(node, src_node_id, msg):
            try:
                # Check message type.
                msg = json.loads(msg, object_pairs_hook=OrderedDict)
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

                if not verify_signature(msg[u"request"], self.wif, self.api.get_id()):
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

                # Handle accept transfer (for download requests.)
                def accept_handler(contract_id, src_unl, data_id, file_size):
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

                # Register accept handler.
                self.transfer.add_handler("accept", accept_handler)

                # Handle start transfer.
                def start_handler(client, con, contract_id):
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
                    self.results[test]["start_time"] = int(time.time())

                    if test == "download":
                        return -1
                    else:
                        return 1

                    _log.debug(self.results)

                # Register start handler.
                self.transfer.add_handler("start", start_handler)

                # Send upload request to remote host!
                file_size = req[u"file_size"]
                contract_id = self.transfer.data_request(
                    "download",
                    req[u"data_id"],
                    file_size,
                    req[u"test_node_unl"]
                )

                # Fire error.
                def errback(ret):
                    self.active_test.errback(ret)

                # Register error handler for transfer.
                self.transfer.defers[contract_id].addErrback(errback)

                def completion_handler(client, found_contract_id, con):
                    # What test is this for?
                    _log.debug("IN ALICE completion handler")
                    contract = self.transfer.contracts[found_contract_id]
                    if contract[u"data_id"] != req[u"data_id"]:
                        return

                    if self.transfer.get_direction(found_contract_id) == u"send":
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

                    self.results[test]["end_time"] = int(time.time())
                    self.results[test]["transferred"] = file_size
                    _log.debug(self.results)

                    if test == "download":
                        # Check results.
                        if self.is_bad_results():
                            return -1


                        # Schedule next call if it returned too fast.
                        if self.is_bad_test():
                            _log.debug("SCHEDUALING NEW TRANSFER!")
                            node_unl = copy.deepcopy(self.test_node_unl)
                            self.test_node_unl = None
                            self.start(
                                node_unl,
                                size=self.test_size * 10
                            )
                        else:
                            # Cleanup.
                            self.test_node_unl = None
                            _log.debug("TRANSFER ALL DONE!")
                            _log.debug(self.results)

                            # Convert results to bytes per second.
                            speeds = self.interpret_results()

                            # Return results.
                            self.active_test.callback(speeds)
                            self.active_test = None


                        return -1
                    else:
                        return 1

                # Register completion handler.
                self.transfer.add_handler("complete", completion_handler)

                _log.debug("res: got response")
            except (ValueError, KeyError) as e:
                _log.debug("Error in res")
                _log.debug(e)
                return

        return handle_responses

    def interpret_results(self):
        speeds = {}
        for test in list(self.results):
            # Seconds.
            start_time = self.results[test]["start_time"]
            end_time = self.results[test]["end_time"]
            seconds = Decimal(end_time - start_time)
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

    def is_bad_test(self):
        threshold = 2
        for test in list(self.results):
            start_time = self.results[test]["start_time"]
            end_time = self.results[test]["end_time"]
            assert(start_time)
            assert(end_time)

            duration = end_time - start_time
            if duration < threshold:
                return 1

        return 0

    def start(self, node_unl, size=1):
        """
        :param node_unl: UNL of target
        :param size: MB to send in transfer
        :return: deferred with test results
        """

        # Any tests currently in progress?
        if self.test_node_unl is not None:
            return 0

        # Reset test size.
        self.test_size = size

        # Reset deferred.
        self.active_test = defer.Deferred()

        # Generate random file to upload.
        file_size = size * ONE_MB
        shard = generate_random_file(file_size)

        # Hash partial content.
        data_id = get_hash(shard)
        _log.debug("FINGER_log.debug HASH")
        _log.debug(data_id)

        # File meta data.
        meta = OrderedDict([
            (u"file_size", file_size),
            (u"algorithm", u"sha256"),
            (u"hash", data_id.decode("utf-8"))
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
        storjnode.storage.manager.add(self.transfer.store_config, shard)

        # Build bandwidth test request.
        req = OrderedDict([
            (u"type", u"test_bandwidth_request"),
            (u"timestamp", int(time.time())),
            (u"requester", self.transfer.net.unl.value),
            (u"test_node_unl", node_unl),
            (u"data_id", data_id.decode("utf-8")),
            (u"file_size", file_size)
        ])

        # Sign request.
        req = sign(req, self.wif)

        # Send request.
        node_id = parse_node_id_from_unl(node_unl)
        req = json.dumps(req, ensure_ascii=True)
        self.api.relay_message(node_id, req)

        # Set start time.
        self.start_time = time.time()

        # Return deferred.
        return self.active_test


if __name__ == "__main__":
    # Alice sample node.
    alice_wallet = BtcTxStore(testnet=False, dryrun=True)
    alice_wif = alice_wallet.create_key()
    alice_node_id = address_to_node_id(alice_wallet.get_address(alice_wif))
    alice_dht = pyp2p.dht_msg.DHT(node_id=alice_node_id)
    alice_transfer = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=63600,
            dht_node=alice_dht,
        ),
        wif=alice_wif,
        store_config={tempfile.mkdtemp(): None}
    )

    _log.debug("Alice UNL")
    _log.debug(alice_transfer.net.unl.value)

    # Bob sample node.
    bob_wallet = BtcTxStore(testnet=False, dryrun=True)
    bob_wif = bob_wallet.create_key()
    bob_node_id = address_to_node_id(bob_wallet.get_address(bob_wif))
    bob_dht = pyp2p.dht_msg.DHT(node_id=bob_node_id)
    bob_transfer = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=63601,
            dht_node=bob_dht,
        ),
        wif=bob_wif,
        store_config={tempfile.mkdtemp(): None}
    )

    _log.debug("Bob UNL")
    _log.debug(bob_transfer.net.unl.value)

    # Show bandwidth.
    def show_bandwidth(results):
        _log.debug(results)

    # Test bandwidth between Alice and Bob.
    bob_test = BandwidthTest(bob_wif, bob_transfer, bob_dht)
    alice_test = BandwidthTest(alice_wif, alice_transfer, alice_dht)
    d = alice_test.start(bob_transfer.net.unl.value)
    d.addCallback(show_bandwidth)

    # Main event loop.
    while alice_test.active_test is not None:
        for client in [alice_transfer, bob_transfer]:
            if client == alice_transfer:
                _log.debug("Alice")
            else:
                _log.debug("Bob")
            process_transfers(client)

        time.sleep(0.002)
