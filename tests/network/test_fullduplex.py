import logging

LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

import os
import time
import unittest
import btctxstore
from storjnode import network


if os.environ.get("STORJNODE_USE_RELAYNODE"):
    INITIAL_RELAYNODES = [os.environ.get("STORJNODE_USE_RELAYNODE")]
else:
    INITIAL_RELAYNODES = ["localhost:6667"]


class TestFullDuplex(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.alice_wif = self.btctxstore.create_key()
        self.alice_address = self.btctxstore.get_address(self.alice_wif)
        self.bob_wif = self.btctxstore.create_key()
        self.bob_address = self.btctxstore.get_address(self.bob_wif)
        self.alice = network.Service(INITIAL_RELAYNODES, self.alice_wif)
        self.alice.connect()
        self.bob = network.Service(INITIAL_RELAYNODES, self.bob_wif)
        self.bob.connect()

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_fullduplex(self):
        self.alice.send(self.bob_address, b"alice")
        self.bob.send(self.alice_address, b"bob")

        while (self.alice.has_queued_output() or  # wait until sent
               self.bob.has_queued_output()):
            time.sleep(0.2)
        time.sleep(5)  # allow time to receive

        expected_alice = {self.bob_address: b"bob"}
        self.assertEqual(expected_alice, self.alice.get_received())

        expected_bob = {self.alice_address: b"alice"}
        self.assertEqual(expected_bob, self.bob.get_received())

        self.assertEqual([self.bob_address], self.alice.nodes_connected())
        self.assertEqual([self.alice_address], self.bob.nodes_connected())


if __name__ == "__main__":
    unittest.main()
