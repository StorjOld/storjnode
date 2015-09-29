import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"                                                  
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)   

import time
import unittest
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]
ALICE_ADDRESS = "1F3SedVWR2em2hpSbCfM8WsgjTSCkGWE8i"
BOB_ADDRESS = "13i3511DwugmktybXJhkMj4nhaFvXJ7uhX"


class TestNodeMessageFullDuplex(unittest.TestCase):

    def setUp(self):
        self.alice = network.Network(INITIAL_RELAYNODES, ALICE_ADDRESS)
        self.alice.connect()
        self.bob = network.Network(INITIAL_RELAYNODES, BOB_ADDRESS)
        self.bob.connect()
        time.sleep(2)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        self.alice.connect_to_node(BOB_ADDRESS)
        time.sleep(2)  # allow time to connect

        self.alice.send_message(BOB_ADDRESS, "test", "alices_test_data")
        self.bob.send_message(ALICE_ADDRESS, "test", "bobs_test_data")
        
        time.sleep(2)  # allow time to send

        self.assertTrue(len(self.alice.get_messages_received()) == 1)
        self.assertTrue(len(self.bob.get_messages_received()) == 1


if __name__ == "__main__":
    unittest.main()
