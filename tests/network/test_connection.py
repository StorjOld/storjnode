import unittest
import btctxstore
from storjnode.network import Service


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestConnection(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)

    def test_connects(self):
        # connect
        self.service = Service(INITIAL_RELAYNODES, self.wif)
        self.service.connect()

        # is connected
        self.assertTrue(self.service.connected())

        # disconnect
        self.service.disconnect()
        self.assertFalse(self.service.connected())

    def test_restart(self):
        # connect
        self.service = Service(INITIAL_RELAYNODES, self.wif)
        self.service.connect()

        # test reconnect
        self.assertTrue(self.service.connected())  # is connected
        self.service.reconnect()
        self.assertTrue(self.service.connected())  # is connected again

        # disconnect
        self.service.disconnect()
        self.assertFalse(self.service.connected())


if __name__ == "__main__":
    unittest.main()
