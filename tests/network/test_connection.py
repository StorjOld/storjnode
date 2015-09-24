import unittest
from storjnode.network import Network


# get initial setup
SERVER = "irc.quakenet.org"  # FIXME get from config
PORT = 6667  # FIXME get from config


class TestConnection(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_connects(self):
        initial_relaynodes = [("irc.quakenet.org", 6667)]
        network = Network(initial_relaynodes)
        network.start()
        self.assertTrue(network.connected())


if __name__ == "__main__":
    unittest.main()
