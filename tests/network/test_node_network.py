import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"                                                  
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)   

import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestNodeNetwork(unittest.TestCase):

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

        # connect all nodes to each other
        self.alice.node_connect(self.bob_address)
        self.bob.node_connect(self.charlie_address)
        self.charlie.node_connect(self.alice_address)

        time.sleep(15)

        # check that nodes are connected to each other
        self.assertTrue(self.alice.node_connected(self.bob_address))
        self.assertTrue(self.bob.node_connected(self.alice_address))
        self.assertTrue(self.bob.node_connected(self.charlie_address))
        self.assertTrue(self.charlie.node_connected(self.bob_address))
        self.assertTrue(self.charlie.node_connected(self.alice_address))
        self.assertTrue(self.alice.node_connected(self.charlie_address))


if __name__ == "__main__":
    unittest.main()
