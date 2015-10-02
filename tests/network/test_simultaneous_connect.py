import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


@unittest.skip("broken")
class TestSimultaneousConnect(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.alice_wif = self.btctxstore.create_key()
        self.bob_wif = self.btctxstore.create_key()
        self.alice_address = self.btctxstore.get_address(self.alice_wif)
        self.bob_address = self.btctxstore.get_address(self.bob_wif)
        self.alice = network.Service(INITIAL_RELAYNODES, self.alice_wif)
        self.bob = network.Service(INITIAL_RELAYNODES, self.bob_wif)
        self.alice.connect()
        self.bob.connect()
        time.sleep(15)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        for i in range(3):  # try several time in case it works by chance
            self.alice.node_send(self.bob_address, b"something")
            self.bob.node_send(self.alice_address, b"something")

            time.sleep(15)  # allow time to connect and send

            self.assertEqual(self.alice.nodes_connected(), [self.bob_address])
            self.assertEqual(self.bob.nodes_connected(), [self.alice_address])

            self.alice.reconnect()
            self.bob.reconnect()

            time.sleep(15)


if __name__ == "__main__":
    unittest.main()
