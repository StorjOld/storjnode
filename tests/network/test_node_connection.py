import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"                                                  
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)   

import time
import unittest
from storjnode import network


INITIAL_RELAYNODES = [("irc.quakenet.org", 6667)]  # FIXME use own network
ALICE_ADDRESS = "1F3SedVWR2em2hpSbCfM8WsgjTSCkGWE8i"
BOB_ADDRESS = "13i3511DwugmktybXJhkMj4nhaFvXJ7uhX"


class TestNodeConnection(unittest.TestCase):

    def setUp(self):
        self.alice = network.Network(INITIAL_RELAYNODES, ALICE_ADDRESS)
        self.alice.connect()
        self.bob = network.Network(INITIAL_RELAYNODES, BOB_ADDRESS)
        self.bob.connect()

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        self.alice.connect_to_node(BOB_ADDRESS)
        time.sleep(15)
        alice_connected = self.alice.node_connection_state(BOB_ADDRESS)
        self.assertEqual(alice_connected, network.CONNECTED)
        bob_connected = self.bob.node_connection_state(ALICE_ADDRESS)
        self.assertEqual(bob_connected, network.CONNECTED)


if __name__ == "__main__":
    unittest.main()
