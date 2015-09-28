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


class TestNodeNetwork(unittest.TestCase):

    def setUp(self):
        self.alice = network.Network(INITIAL_RELAYNODES, ALICE_ADDRESS)
        self.alice.connect()
        self.bob = network.Network(INITIAL_RELAYNODES, BOB_ADDRESS)
        self.bob.connect()
        self.charlie = network.Network(INITIAL_RELAYNODES, CHARLIE_ADDRESS)
        self.charlie.connect()
        time.sleep(15)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()
        self.charlie.disconnect()

    def test_connects(self):

        # connect all nodes to each other
        self.alice.connect_to_node(BOB_ADDRESS)
        self.bob.connect_to_node(CHARLIE_ADDRESS)
        self.charlie.connect_to_node(ALICE_ADDRESS)

        time.sleep(30)

        # check that nodes are connected to each other
        self.assertTrue(self.alice.node_connected(BOB_ADDRESS))
        self.assertTrue(self.bob.node_connected(ALICE_ADDRESS))
        self.assertTrue(self.bob.node_connected(CHARLIE_ADDRESS))
        self.assertTrue(self.charlie.node_connected(BOB_ADDRESS))
        self.assertTrue(self.charlie.node_connected(ALICE_ADDRESS))
        self.assertTrue(self.alice.node_connected(CHARLIE_ADDRESS))


if __name__ == "__main__":
    unittest.main()
