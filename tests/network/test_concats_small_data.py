import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestConcatsSmallData(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.alice_wif = self.btctxstore.create_key()
        self.alice_address = self.btctxstore.get_address(self.alice_wif)
        self.bob_wif = self.btctxstore.create_key()
        self.bob_address = self.btctxstore.get_address(self.bob_wif)
        self.alice = network.Service(INITIAL_RELAYNODES, self.alice_wif)
        self.alice.connect()
        self.bob = network.Service(INITIAL_RELAYNODES, self.bob_wif)
        self.bob.connect()
        time.sleep(15)

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        self.alice.send(self.bob_address, b"foo")
        self.alice.send(self.bob_address, b"bar")
        self.alice.send(self.bob_address, b"baz")

        time.sleep(20)  # allow time to connect and send

        expected_bob = {self.alice_address: b"foobarbaz"}
        self.assertEqual(expected_bob, self.bob.received())


if __name__ == "__main__":
    unittest.main()
