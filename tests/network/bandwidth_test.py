import storjnode
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
from storjnode.util import address_to_node_id
from storjnode.util import parse_node_id_from_unl, generate_random_file
from twisted.internet import defer
from btctxstore import BtcTxStore
import unittest
from storjnode.network.bandwidth.test import BandwidthTest
from twisted.internet.task import LoopingCall
from crochet import setup
setup()

_log = logging.getLogger(__name__)
test_success = 0


class TestBandwidthTest(unittest.TestCase):
    def test_bandwidth_test(self):
        # Alice sample node.
        alice_wallet = BtcTxStore(testnet=False, dryrun=True)
        alice_wif = alice_wallet.create_key()
        alice_node_id = address_to_node_id(alice_wallet.get_address(alice_wif))
        alice_dht = pyp2p.dht_msg.DHT(
            node_id=alice_node_id,
            networking=0
        )
        alice_transfer = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=63600,
                debug=1,
                wan_ip="8.8.8.8",
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
        bob_dht = pyp2p.dht_msg.DHT(
            node_id=bob_node_id,
            networking=0
        )
        bob_transfer = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=63601,
                debug=1,
                wan_ip="8.8.8.8",
                dht_node=bob_dht
            ),
            wif=bob_wif,
            store_config={tempfile.mkdtemp(): None}
        )

        # Link DHT nodes.
        alice_dht.add_relay_link(bob_dht)
        bob_dht.add_relay_link(alice_dht)

        _log.debug("Bob UNL")
        _log.debug(bob_transfer.net.unl.value)

        # Show bandwidth.
        def show_bandwidth(results):
            global test_success
            test_success = 1
            _log.debug(results)

        # Test bandwidth between Alice and Bob.
        bob_test = BandwidthTest(bob_wif, bob_transfer, bob_dht, 0)
        alice_test = BandwidthTest(alice_wif, alice_transfer, alice_dht, 0)
        d = alice_test.start(bob_transfer.net.unl.value)
        d.addCallback(show_bandwidth)

        # Main event loop.
        # and not test_success
        end_time = time.time() + 60
        while alice_test.active_test is not None and time.time() < end_time:
            for client in [alice_transfer, bob_transfer]:
                process_transfers(client)

            time.sleep(0.002)

        # End net.
        for client in [alice_transfer, bob_transfer]:
            client.net.stop()

        self.assertTrue(test_success == 1)


if __name__ == "__main__":
    unittest.main()
