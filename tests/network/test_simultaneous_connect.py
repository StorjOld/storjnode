import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("localhost:6667")]


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
        time.sleep(15)  # allow time to connect

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        self.alice.send(self.bob_address, b"something")
        self.bob.send(self.alice_address, b"something")

        time.sleep(15)  # allow time to connect and send

        self.assertEqual(self.alice.nodes_connected(), [self.bob_address])
        self.assertEqual(self.bob.nodes_connected(), [self.alice_address])


if __name__ == "__main__":
    unittest.main()
