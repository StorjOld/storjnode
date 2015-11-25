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
from storjnode.network.process_transfers import process_transfers
from storjnode.network.file_transfer import FileTransfer
from storjnode.util import sign_msg, check_sig, address_to_node_id
from twisted.internet import defer
from btctxstore import BtcTxStore

class BandwidthTest():
    def __init__(self, wif, transfer, api):
        self.wif = wif
        self.api = api
        self.transfer = transfer
        self.test_node_id = None
        self.active_test = defer.Deferred()

        # Stored in BYTES per second.
        self.speed = {
            "download": Decimal(0),
            "upload": Decimal(0)
        }

        # Listen for bandwidth requests + responses.
        handle_requests = self.handle_requests_builder()
        handle_responses = self.handle_responses_builder()
        self.api.add_message_handler(handle_requests)
        self.api.add_message_handler(handle_responses)

    def handle_responses_builder(self):
        def handle_responses(src_node_id, msg):
            try:
                # Check message type.
                msg = json.loads(msg, object_pairs_hook=OrderedDict)
                if msg[u"type"] != u"test_bandwidth_response":
                    print("res: Invalid response")
                    return

                # Transfer already active.
                if self.test_node_id is not None:
                    print("res: transfer already active")
                    return

                # Check we sent the request.
                req = msg[u"request"]
                if not check_sig(msg, self.wif):
                    print("res: our request sig was invalid")
                    return

                # Check node IDs match.
                if req[u"test_node_id"] != msg[u"requestee"]:
                    print("res: node ids don't match")
                    return

                # Check their sig.
                src_node_id = binascii.unhexlify(msg[u"requestee"])
                if not check_sig(msg, self.wif, src_node_id):
                    print("res: their sig did not match")
                    return

                # Set active node ID.
                self.test_node_id = src_node_id
                print("res: got response")

            except (ValueError, KeyError) as e:
                return

        return handle_responses

    def handle_requests_builder(self):
        # Handle bandwidth requests.
        def handle_requests(src_node_id, msg):
            try:
                # Check message type.
                msg = json.loads(msg, object_pairs_hook=OrderedDict)
                if msg[u"type"] != u"test_bandwidth_request":
                    print("req: Invalid request")
                    return

                # Drop request if test already active.
                if self.test_node_id is not None:
                    print("req: test already active")
                    return

                # Check sig.
                src_node_id = binascii.unhexlify(msg[u"requester"])
                if not check_sig(msg, self.wif):
                    print("req: Invalid sig")
                    return

                # Build response.
                our_node_id = binascii.unhexlify(self.api.get_id())
                res = OrderedDict({
                    u"type": u"test_bandwidth_response",
                    u"timestamp": int(time.time()),
                    u"requestee": our_node_id.decode("utf-8"),
                    u"request": msg
                })

                # Check they got our node ID right.
                if our_node_id != msg[u"test_node_id"]:
                    print("req: they got our node id wrong")
                    return

                # Sign response
                res = sign_msg(res, self.wif)

                # Send request back to source.
                self.api.relay_message(src_node_id, res)
                print("req: got request")

            except (ValueError, KeyError) as e:
                print(e)

        return handle_requests

    def start(self, node_id, test_unit="kbps"):
        """
        :param node_id: bytes node_id
        :return: deferred with test results
        """

        # Any tests currently in progress?
        if self.test_node_id is not None:
            return 0

        # Build bandwidth test request.
        requester = binascii.hexlify(self.api.get_id())
        test_node_id = binascii.hexlify(node_id)
        req = OrderedDict({
            u"type": u"test_bandwidth_request",
            u"timestamp": int(time.time()),
            u"requester": requester.decode("utf-8"),
            u"test_node_id": test_node_id.decode("utf-8")
        })

        # Sign request.
        req = sign_msg(req, self.wif)

        # Send request.
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

    # Test bandwidth between Alice and Bob.
    bob_test = BandwidthTest(bob_wif, bob_transfer, bob_dht)
    alice_test = BandwidthTest(alice_wif, alice_transfer, alice_dht)
    d = alice_test.start(bob_node_id)

    # Main event loop.
    while 1:
        for client in [alice_transfer, bob_transfer]:
            if client == alice_transfer:
                print("Alice")
            else:
                print("Bob")
            process_transfers(client)

        time.sleep(1)

