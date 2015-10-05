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


class TestConcatsSmallData(unittest.TestCase):

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

    def test_concats_small_data(self):
        self.alice.send(self.bob_address, b"foo")
        self.alice.send(self.bob_address, b"bar")
        self.alice.send(self.bob_address, b"baz")

        while self.alice.has_queued_output():  # wait until sent
            time.sleep(0.2)
        time.sleep(10)  # allow time to receive

        expected_bob = {self.alice_address: b"foobarbaz"}
        self.assertEqual(expected_bob, self.bob.get_received())


if __name__ == "__main__":
    unittest.main()
