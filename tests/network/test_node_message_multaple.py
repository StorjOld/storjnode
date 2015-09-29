import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"                                                  
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)   

import time
import unittest
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]
ALICE_ADDRESS = "1F3SedVWR2em2hpSbCfM8WsgjTSCkGWE8i"
BOB_ADDRESS = "13i3511DwugmktybXJhkMj4nhaFvXJ7uhX"
CHARLIE_ADDRESS = "1A3JkxMoZDqJ4nLvMWc3L7EXokEyKGzfEA"


class TestNodeMessageMultaple(unittest.TestCase):

    def setUp(self):
        self.alice = network.Network(INITIAL_RELAYNODES, ALICE_ADDRESS)
        self.alice.connect()
        self.bob = network.Network(INITIAL_RELAYNODES, BOB_ADDRESS)
        self.bob.connect()
        self.charlie = network.Network(INITIAL_RELAYNODES, CHARLIE_ADDRESS)
        self.charlie.connect()
        time.sleep(2)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()
        self.charlie.disconnect()

    def test_connects(self):

        # connect nodes to each other
        self.alice.connect_to_node(BOB_ADDRESS)
        self.alice.connect_to_node(CHARLIE_ADDRESS)

        time.sleep(2)  # allow time to connect

        self.alice.send_message(BOB_ADDRESS, "test", "alice_to_bob")
        self.alice.send_message(CHARLIE_ADDRESS, "test", "alice_to_charlie")
        self.bob.send_message(ALICE_ADDRESS, "test", "bob_to_alice")
        self.charlie.send_message(ALICE_ADDRESS, "test", "charlie_to_alice")
        
        time.sleep(2)  # allow time to send

        self.assertEqual(len(self.alice.get_messages_received()), 2)
        self.assertEqual(len(self.bob.get_messages_received()), 1)
        self.assertEqual(len(self.charlie.get_messages_received()), 1)


if __name__ == "__main__":
    unittest.main()
