import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("localhost:6667")]


class TestTransferNetwork(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.alice_wif = self.btctxstore.create_key()
        self.alice_address = self.btctxstore.get_address(self.alice_wif)
        self.bob_wif = self.btctxstore.create_key()
        self.bob_address = self.btctxstore.get_address(self.bob_wif)
        self.charlie_wif = self.btctxstore.create_key()
        self.charlie_address = self.btctxstore.get_address(self.charlie_wif)

        self.alice = network.Service(INITIAL_RELAYNODES, self.alice_wif)
        self.alice.connect()
        self.bob = network.Service(INITIAL_RELAYNODES, self.bob_wif)
        self.bob.connect()
        self.charlie = network.Service(INITIAL_RELAYNODES, self.charlie_wif)
        self.charlie.connect()
        time.sleep(15)  # allow time to connect

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()
        self.charlie.disconnect()

    def test_connects(self):
        self.alice.send(self.bob_address, b"alice_to_bob")
        self.alice.send(self.charlie_address, b"alice_to_charlie")
        time.sleep(15)  # other test is responsable for simultainous connect
        self.bob.send(self.alice_address, b"bob_to_alice")
        self.charlie.send(self.alice_address, b"charlie_to_alice")

        time.sleep(15)  # allow time to connect and send

        self.assertEqual(len(self.alice.get_received()), 2)
        self.assertEqual(len(self.bob.get_received()), 1)
        self.assertEqual(len(self.charlie.get_received()), 1)

        alice_connections = set([self.bob_address, self.charlie_address])
        self.assertEqual(alice_connections, set(self.alice.nodes_connected()))
        self.assertEqual([self.alice_address], self.bob.nodes_connected())
        self.assertEqual([self.alice_address], self.charlie.nodes_connected())


if __name__ == "__main__":
    unittest.main()
