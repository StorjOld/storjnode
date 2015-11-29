"""
Not complete, don't add to __init__
"""

from decimal import Decimal
from collections import OrderedDict
import time
import tempfile
import pyp2p
from storjnode.network.process_transfers import process_transfers
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.message import sign, verify_signature
from storjnode.util import address_to_node_id, parse_node_id_from_unl
from twisted.internet import defer
from btctxstore import BtcTxStore


class BandwidthTest():
    def __init__(self, wif, transfer, api):
        self.wif = wif
        self.api = api
        self.transfer = transfer
        self.test_node_unl = None
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
        def handle_responses(node, src_node_id, msg):
            # Check message type.
            msg = OrderedDict(msg)
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

            if not verify_signature(msg[u"request"], self.wif,
                                    self.api.get_id()):
                print("res: our request sig was invalid")
                return

            # Check node IDs match.
            if req[u"test_node_unl"] != msg[u"requestee"]:
                print("res: node ids don't match")
                return

            # Check their sig.
            src_node_id = parse_node_id_from_unl(msg[u"requestee"])
            if not verify_signature(msg, self.wif, src_node_id):
                print("res: their sig did not match")
                return

            # Set active node ID.
            self.test_node_unl = msg[u"requestee"]
            print("res: got response")

            try:
                pass
            except (ValueError, KeyError) as e:
                print("Error in res: %s" % repr(e))
                return

        return handle_responses

    def handle_requests_builder(self):
        # Handle bandwidth requests.
        def handle_requests(node, src_node_id, msg):
            print("In handle requests")

            # Check message type.
            msg = OrderedDict(msg)
            if msg[u"type"] != u"test_bandwidth_request":
                print("req: Invalid request")
                return

            # Drop request if test already active.
            if self.test_node_unl is not None:
                print("req: test already active")
                return

            # Check sig.
            src_node_id = parse_node_id_from_unl(msg[u"requester"])
            if not verify_signature(msg, self.wif, src_node_id):
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
            res = sign(res, self.wif)

            # Send request back to source.
            self.api.relay_message(src_node_id, res.itmes())
            print("req: got request")

            try:
                pass
            except (ValueError, KeyError) as e:
                print(e)
                print("Error in req")

        return handle_requests

    def start(self, node_unl, test_unit="kbps", size=1):
        """
        :param node_unl: UNL of target
        :param size: MB to send in transfer
        :return: deferred with test results
        """

        # Any tests currently in progress?
        if self.test_node_unl is not None:
            return 0

        # Build bandwidth test request.
        req = OrderedDict({
            u"type": u"test_bandwidth_request",
            u"timestamp": int(time.time()),
            u"requester": self.transfer.net.unl.value,
            u"test_node_unl": node_unl
        })

        # Sign request.
        req = sign(req, self.wif)

        # Send request.
        node_id = parse_node_id_from_unl(node_unl)
        self.api.relay_message(node_id, req.items())

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
