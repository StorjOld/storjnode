import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"                                                  
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)   

import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestNodeMessageMultaple(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.alice_wif = self.btctxstore.create_key()
        self.alice_address = self.btctxstore.get_address(self.alice_wif)
        self.bob_wif = self.btctxstore.create_key()
        self.bob_address = self.btctxstore.get_address(self.bob_wif)
        self.charlie_wif = self.btctxstore.create_key()
        self.charlie_address = self.btctxstore.get_address(self.charlie_wif)

        self.alice = network.Network(INITIAL_RELAYNODES, self.alice_wif)
        self.alice.connect()
        self.bob = network.Network(INITIAL_RELAYNODES, self.bob_wif)
        self.bob.connect()
        self.charlie = network.Network(INITIAL_RELAYNODES, self.charlie_wif)
        self.charlie.connect()
        time.sleep(15)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()
        self.charlie.disconnect()

    def test_connects(self):

        # connect nodes to each other
        self.alice.node_connect(self.bob_address)
        self.alice.node_connect(self.charlie_address)

        time.sleep(15)  # allow time to connect

        self.alice.send(self.bob_address, b"alice_to_bob")
        self.alice.send(self.charlie_address, b"alice_to_charlie")
        self.bob.send(self.alice_address, b"bob_to_alice")
        self.charlie.send(self.alice_address, b"charlie_to_alice")
        
        time.sleep(15)  # allow time to send

        self.assertEqual(len(self.alice.received()), 2)
        self.assertEqual(len(self.bob.received()), 1)
        self.assertEqual(len(self.charlie.received()), 1)


if __name__ == "__main__":
    unittest.main()
