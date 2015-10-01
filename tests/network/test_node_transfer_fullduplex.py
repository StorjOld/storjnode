import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

import time
import btctxstore
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestNodeTransferFullDuplex(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.alice_wif = self.btctxstore.create_key()
        self.alice_address = self.btctxstore.get_address(self.alice_wif)
        self.bob_wif = self.btctxstore.create_key()
        self.bob_address = self.btctxstore.get_address(self.bob_wif)
        self.alice = network.Network(INITIAL_RELAYNODES, self.alice_wif)
        self.alice.connect()
        self.bob = network.Network(INITIAL_RELAYNODES, self.bob_wif)
        self.bob.connect()
        time.sleep(15)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        self.alice.send(self.bob_address, b"alice")

        time.sleep(15)  # other test is responsable for simultainous connect

        self.bob.send(self.alice_address, b"bob")

        time.sleep(15)  # allow time to connect and send

        expected_alice = {self.bob_address: b"bob"}
        self.assertEqual(expected_alice, self.alice.received())

        expected_bob = {self.alice_address: b"alice"}
        self.assertEqual(expected_bob, self.bob.received())


if __name__ == "__main__":
    unittest.main()
