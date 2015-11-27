"""
Not complete, don't add to __init__
"""



from decimal import Decimal
from collections import OrderedDict
import time
import binascii
import json
import tempfile
import pyp2p
import os
import storjnode.storage.manager
from storjnode.storage.shard import get_hash
from storjnode.network.process_transfers import process_transfers
from storjnode.network.file_transfer import FileTransfer
from storjnode.util import sign_msg, check_sig, address_to_node_id, parse_node_id_from_unl, generate_random_file
from twisted.internet import defer
from btctxstore import BtcTxStore


#ONE_MB = 1048576
ONE_MB = 1 # Easier for testing.

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
                "transferred": Decimal(0),
                "start_time": int(0),
                "end_time": int(0)
            },
            "download": {
                "transferred": Decimal(0),
                "start_time": int(0),
                "end_time": int(0)
            }
        }

        # Listen for bandwidth requests + responses.
        handle_requests = self.handle_requests_builder()
        handle_responses = self.handle_responses_builder()
        self.api.add_message_handler(handle_requests)
        self.api.add_message_handler(handle_responses)

    def handle_requests_builder(self):
        # Handle bandwidth requests.
        def handle_requests(src_node_id, msg):
            try:
                print("In handle requests")

                # Check message type.
                msg = json.loads(msg, object_pairs_hook=OrderedDict)
                if msg[u"type"] != u"test_bandwidth_request":
                    print("req: Invalid request")
                    return

                # Drop request if test already active.
                if self.test_node_unl is not None:
                    print("req: test already active")
                    return

                # Check sig.
                src_node_id = parse_node_id_from_unl(msg[u"requester"])
                if not check_sig(msg, self.wif, src_node_id):
                    print("req: Invalid sig")
                    return

                # Build response.
                our_unl = self.transfer.net.unl.value
                res = OrderedDict({
                    u"type": u"test_bandwidth_response",
                    u"timestamp": int(time.time()),
                    u"requestee": our_unl,
                    u"request": msg
                })

                # Check they got our node ID right.
                if our_unl != msg[u"test_node_unl"]:
                    print("req: they got our node id wrong")
                    return

                # Sign response
                res = sign_msg(res, self.wif)

                # Save their node ID!
                self.test_node_unl = msg[u"requester"]

                # Accept transfers.
                def accept_handler(contract_id, src_unl, data_id, file_size):
                    print("In download accept handler!")
                    print(data_id)
                    print(msg[u"data_id"])
                    print()
                    print(self.test_node_unl)
                    print(src_unl)
                    print()
                    print(msg[u"file_size"])


                    if data_id != msg[u"data_id"]:
                        return 0

                    # Invalid node making this connection.
                    if self.test_node_unl != src_unl:
                        return 0

                    # Invalid file_size request size for test.
                    test_data_size = (self.test_size * ONE_MB)
                    if msg[u"file_size"] > (test_data_size + 1024):
                        return 0

                    # Update download test results.
                    def completion_handler(client, found_contract_id, con):
                        # This is completion for another transfer!
                        if found_contract_id != contract_id:
                            return

                        # Check test data.
                        if not self.check_test_file(data_id, src_unl):
                            print("Test data was incorrect in download!")
                            return

                        transferred = client.con_info[con]
                        transferred = transferred[contract_id]["file_size"]
                        self.results["download"]["end_time"] = int(time.time())
                        self.results["download"]["transferred"] = transferred

                        print("\a")
                        print("download transfer complete!")
                        print(self.results)

                        # Send download request to remote host!
                        self.transfer.data_request(
                            "download",
                            msg[u"data_id"],
                            msg[u"file_size"],
                            self.test_node_unl
                        )

                    # Register complete handler.
                    self.transfer.add_handler("complete", completion_handler)

                    return -1

                # Add accept handler for bandwidth tests.
                self.transfer.add_handler("accept", accept_handler)

                # Update start time for download test.
                def start_handler(client, con, contract_id):
                    contract = self.transfer.contracts[contract_id]
                    if contract[u"data_id"] != msg[u"data_id"]:
                        return

                    # Update start time.
                    self.results["download"]["start_time"] = int(time.time())

                    print("Downlaod start handler")
                    print()

                # Add start handler.
                self.transfer.add_handler("start", start_handler)

                # Send request back to source.
                res = json.dumps(res, ensure_ascii=True)
                self.api.relay_message(src_node_id, res)
                print("req: got request")
            except (ValueError, KeyError) as e:
                print(e)
                print("Error in req")

        return handle_requests

    def handle_responses_builder(self):
        def handle_responses(src_node_id, msg):
            try:
                # Check message type.
                msg = json.loads(msg, object_pairs_hook=OrderedDict)
                if msg[u"type"] != u"test_bandwidth_response":
                    print("res: Invalid response")
                    return

                # Transfer already active.
                if self.test_node_unl is not None:
                    print("res: transfer already active")
                    return

                # Check we sent the request.
                req = msg[u"request"]
                print(req)

                if not check_sig(msg[u"request"], self.wif, self.api.get_id()):
                    print("res: our request sig was invalid")
                    return

                # Check node IDs match.
                if req[u"test_node_unl"] != msg[u"requestee"]:
                    print("res: node ids don't match")
                    return

                # Check their sig.
                src_node_id = parse_node_id_from_unl(msg[u"requestee"])
                if not check_sig(msg, self.wif, src_node_id):
                    print("res: their sig did not match")
                    return

                # Set active node ID.
                self.test_node_unl = msg[u"requestee"]

                # Handle accept transfer (for download requests.)
                def accept_handler(contract_id, src_unl, data_id, file_size):
                    if src_unl != self.test_node_unl:
                        print("SRC UNL != \a")
                        return 0

                    if data_id != req[u"data_id"]:
                        print("Data id != \a")
                        return 0

                    # Invalid file_size request size for test.
                    test_data_size = (self.test_size * ONE_MB)
                    if req[u"file_size"] > (test_data_size + 1024):
                        print("file size != \a")
                        return 0

                    return 1

                # Register accept handler.
                self.transfer.add_handler("accept", accept_handler)

                # Handle start transfer.
                def start_handler(client, con, contract_id):
                    print("In upload start handler!")
                    print("IN ALICE start handler")


                    contract = self.transfer.contracts[contract_id]
                    print(contract)
                    print(req[u"data_id"])

                    # Check this corrosponds to something.
                    if contract[u"data_id"] != req[u"data_id"]:
                        print("Alice start: invalid data id")
                        return 0

                    # Determine test.
                    if self.transfer.get_direction(contract_id) == u"send":
                        test = "upload"
                        if contract[u"src_unl"] != self.test_node_unl:
                            print("Alice upload: invalid src unl")
                            return 0
                    else:
                        test = "download"


                    # Set start time.
                    self.results[test]["start_time"] = int(time.time())

                    print(self.results)

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

                def completion_handler(client, found_contract_id, con):
                    # What test is this for?
                    print("IN ALICE completion handler")
                    contract = self.transfer.contracts[found_contract_id]
                    if contract[u"data_id"] != req[u"data_id"]:
                        return

                    if self.transfer.get_direction(found_contract_id) == u"send":
                        print("\a")
                        print("Upload transfer complete!")
                        test = "upload"

                        # Delete our copy of the file.
                        storjnode.storage.manager.remove(
                            self.transfer.store_config,
                            req[u"data_id"]
                        )
                    else:
                        # Check the source of the request.
                        print(contract[u"src_unl"])
                        print(self.test_node_unl)
                        test = "download"
                        if contract[u"src_unl"] != self.test_node_unl:
                            print("Alice dl: src unl incorrect.")
                            return

                        # Check test data.
                        if not self.check_test_file(
                                req[u"data_id"],
                                self.test_node_unl
                        ):
                            print("Test data was incorrect in download!")
                            return

                        print("Alice download")

                    self.results[test]["end_time"] = int(time.time())
                    self.results[test]["transferred"] = file_size
                    print(self.results)

                # Register completion handler.
                self.transfer.add_handler("complete", completion_handler)

                print("res: got response")
            except (ValueError, KeyError) as e:
                print("Error in res")
                print(e)
                return

        return handle_responses

    def check_test_file(self, data_id, node_unl):
        # Size of the test data (without appended sig.)
        test_data_size = self.test_size * ONE_MB

        # Hash partial content.
        path = storjnode.storage.manager.find(
            self.transfer.store_config,
            data_id
        )
        shard = open(path, "rb")
        fingerprint = get_hash(shard, limit=test_data_size)
        print("FINGERPRINT HASH")
        print(fingerprint)

        # File meta data.
        meta = OrderedDict({
            u"file_size": test_data_size,
            u"algorithm": u"sha256",
            u"hash": fingerprint.decode("utf-8")
        })

        # Check signature.
        node_id = parse_node_id_from_unl(node_unl)
        sig_size = os.path.getsize(path) - test_data_size
        shard.seek(1, test_data_size)
        sig = shard.read(sig_size)
        meta[u"signature"] = sig
        print("SIG")
        print(sig)

        print("UNL")
        print(node_unl)

        print("META")
        print(meta)

        return check_sig(meta, self.wif, node_id)


    def start(self, node_unl, test_unit="kbps", size=1):
        """
        :param node_unl: UNL of target
        :param size: MB to send in transfer
        :return: deferred with test results
        """

        # Any tests currently in progress?
        if self.test_node_unl is not None:
            return 0

        # Generate random file to upload.
        file_size = self.test_size * ONE_MB
        shard = generate_random_file(file_size)

        # Hash partial content.
        fingerprint = get_hash(shard)
        print("FINGERPRINT HASH")
        print(fingerprint)

        # File meta data.
        meta = OrderedDict({
            u"file_size": file_size,
            u"algorithm": u"sha256",
            u"hash": fingerprint.decode("utf-8")
        })



        print("UNL")
        print(self.transfer.net.unl.value)

        print("META")
        print(meta)

        # Sign meta data.
        sig = sign_msg(meta, self.wif)[u"signature"]

        print("SIG")
        print(sig)


        # Write signature to file.
        shard.seek(0, 2) # EOF
        shard.write(sig)
        shard.seek(0) # Beginning.

        # Update file size.
        file_size += len(sig)

        # Get data_id of resulting file content (rand data + sig)
        data_id = get_hash(shard)

        # Add file to storage.
        storjnode.storage.manager.add(self.transfer.store_config, shard)

        # Build bandwidth test request.
        req = OrderedDict({
            u"type": u"test_bandwidth_request",
            u"timestamp": int(time.time()),
            u"requester": self.transfer.net.unl.value,
            u"test_node_unl": node_unl,
            u"data_id": data_id.decode("utf-8"),
            u"file_size": file_size
        })

        # Sign request.
        req = sign_msg(req, self.wif)

        # Send request.
        node_id = parse_node_id_from_unl(node_unl)
        req = json.dumps(req, ensure_ascii=True)
        self.api.relay_message(node_id, req)

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

    print("Alice UNL")
    print(alice_transfer.net.unl.value)

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

    print("Bob UNL")
    print(bob_transfer.net.unl.value)

    # Test bandwidth between Alice and Bob.
    bob_test = BandwidthTest(bob_wif, bob_transfer, bob_dht)
    alice_test = BandwidthTest(alice_wif, alice_transfer, alice_dht)
    d = alice_test.start(bob_transfer.net.unl.value)

    # Main event loop.
    while 1:
        for client in [alice_transfer, bob_transfer]:
            if client == alice_transfer:
                print("Alice")
            else:
                print("Bob")
            process_transfers(client)

        time.sleep(1)

