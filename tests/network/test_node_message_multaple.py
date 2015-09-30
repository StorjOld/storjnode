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
        time.sleep(10)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()
        self.charlie.disconnect()

    def test_connects(self):

        # connect nodes to each other
        self.alice.connect_to_node(self.bob_address)
        self.alice.connect_to_node(self.charlie_address)

        time.sleep(10)  # allow time to connect

        self.alice.send_message(self.bob_address, "test", b"alice_to_bob")
        self.alice.send_message(self.charlie_address, "test", b"alice_to_charlie")
        self.bob.send_message(self.alice_address, "test", b"bob_to_alice")
        self.charlie.send_message(self.alice_address, "test", b"charlie_to_alice")
        
        time.sleep(10)  # allow time to send

        self.assertEqual(len(self.alice.get_messages_received()), 2)
        self.assertEqual(len(self.bob.get_messages_received()), 1)
        self.assertEqual(len(self.charlie.get_messages_received()), 1)


if __name__ == "__main__":
    unittest.main()
