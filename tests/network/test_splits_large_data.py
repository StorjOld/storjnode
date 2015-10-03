import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestSplitsLargeData(unittest.TestCase):

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
        time.sleep(10)  # allow time to connect

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        largedata = b"X" * (network.package.MAX_DATA_SIZE * 2)
        self.alice.node_send(self.bob_address, largedata)

        time.sleep(10)  # allow time to connect and send

        expected_bob = {self.alice_address: largedata}
        self.assertEqual(expected_bob, self.bob.node_received())


if __name__ == "__main__":
    unittest.main()
