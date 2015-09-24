import unittest
from storjnode.network import Network


INITIAL_RELAYNODES = [("irc.quakenet.org", 6667)]  # FIXME use own network


class TestConnection(unittest.TestCase):

    def test_connects(self):
        # connect
        self.network = Network(INITIAL_RELAYNODES)
        self.network.connect()

        # is connected
        self.assertTrue(self.network.connected())

        # disconnect
        self.network.disconnect()
        self.assertFalse(self.network.connected())

    def test_restart(self):
        # connect
        self.network = Network(INITIAL_RELAYNODES)
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
