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
import unittest
from storjnode.network.bandwidth_test import BandwidthTest
from twisted.internet.task import LoopingCall
from crochet import setup
setup()

_log = logging.getLogger(__name__)
_log.setLevel("DEBUG")

test_success = 0
class TestBandwidthTest(unittest.TestCase):
    def test_bandwidth_test(self):
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
            global test_success
            test_success = 1
            _log.debug(results)

        # Test bandwidth between Alice and Bob.
        bob_test = BandwidthTest(bob_wif, bob_transfer, bob_dht)
        alice_test = BandwidthTest(alice_wif, alice_transfer, alice_dht)
        d = alice_test.start(bob_transfer.net.unl.value)
        d.addCallback(show_bandwidth)

        # Main event loop.
        while alice_test.active_test is not None:
            for client in [alice_transfer, bob_transfer]:
                process_transfers(client)

            time.sleep(0.002)

        self.assertTrue(test_success == 1)


if __name__ == "__main__":
    unittest.main()