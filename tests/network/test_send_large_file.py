import hashlib
import time
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestSendLargeFile(unittest.TestCase):

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
        time.sleep(15)  # allow time to connect

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def test_connects(self):
        large_file = b"X" * (1024 * 1024)  # 1M

        self.alice.node_send(self.bob_address, large_file)

        time.sleep(60 * 3)  # allow time to connect and send

        # check size
        received = self.bob.node_received()[self.alice_address]
        self.assertEqual(len(received), len(large_file))

        # check hash
        received_hash = hashlib.sha256(received).digest()
        large_file_hash = hashlib.sha256(large_file).digest()
        self.assertEqual(received_hash, large_file_hash)


if __name__ == "__main__":
    unittest.main()
