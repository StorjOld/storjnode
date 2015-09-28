import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"                                                  
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)   

import time
import unittest
from storjnode import network


INITIAL_RELAYNODES = [("irc.quakenet.org", 6667)]  # FIXME use own network
ALICE_ADDRESS = "1F3SedVWR2em2hpSbCfM8WsgjTSCkGWE8i"
BOB_ADDRESS = "13i3511DwugmktybXJhkMj4nhaFvXJ7uhX"


@unittest.skip("")
class TestNodeMessage(unittest.TestCase):

    def setUp(self):
        self.alice = network.Network(INITIAL_RELAYNODES, ALICE_ADDRESS)
        self.alice.connect()
        self.bob = network.Network(INITIAL_RELAYNODES, BOB_ADDRESS)
        self.bob.connect()
        time.sleep(5)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        self.alice.connect_to_node(BOB_ADDRESS)
        time.sleep(15)  # allow time to connect

        alice_got_message = False
        def alice_handler(message):
            alice_got_message = True
            self.assertEqual(message["type"], "test")
            self.assertEqual(message["node"], BOB_ADDRESS)
            self.assertEqual(message["data"], "bobs_test_data")

        bob_got_message = False
        def bob_handler(message):
            bob_got_message = True
            self.assertEqual(message["type"], "test")
            self.assertEqual(message["node"], ALICE_ADDRESS)
            self.assertEqual(message["data"], "alices_test_data")

        self.alice.add_message_handler(alice_handler)
        self.bob.add_message_handler(bob_handler)

        self.alice.send_message(BOB_ADDRESS, "test", "alices_test_data")
        self.bob.send_message(ALICE_ADDRESS, "test", "bobs_test_data")
        
        time.sleep(15)  # allow time to send

        self.assertTrue(alice_got_message)
        self.assertTrue(bob_got_message)


if __name__ == "__main__":
    unittest.main()
