import unittest
from storjnode.network import Network


INITIAL_RELAYNODES = [("irc.quakenet.org", 6667)]  # FIXME use own network


class TestConnection(unittest.TestCase):

    def test_connects(self):
        # connect
        self.network = Network(INITIAL_RELAYNODES)
        self.network.start()

        # is connected
        self.assertTrue(self.network.connected())

        # disconnect
        self.network.stop()
        self.assertFalse(self.network.connected())

    def test_restart(self):
        # connect
        self.network = Network(INITIAL_RELAYNODES)
        self.network.start()

        # is connected
        self.assertTrue(self.network.connected())

        self.network.restart()

        # is connected again
        self.assertTrue(self.network.connected())

        # disconnect
        self.network.stop()
        self.assertFalse(self.network.connected())

if __name__ == "__main__":
    unittest.main()
