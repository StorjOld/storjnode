import unittest
import btctxstore
from storjnode.network import Network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestNetworkConnection(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)

    def test_connects(self):
        # connect
        self.network = Network(INITIAL_RELAYNODES, self.wif)
        self.network.connect()

        # is connected
        self.assertTrue(self.network.connected())

        # disconnect
        self.network.disconnect()
        self.assertFalse(self.network.connected())

    def test_restart(self):
        # connect
        self.network = Network(INITIAL_RELAYNODES, self.wif)
        self.network.connect()

        # test reconnect
        self.assertTrue(self.network.connected()) # is connected
        self.network.reconnect()
        self.assertTrue(self.network.connected()) # is connected again

        # disconnect
        self.network.disconnect()
        self.assertFalse(self.network.connected())


if __name__ == "__main__":
    unittest.main()
