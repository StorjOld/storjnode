import unittest
from storjnode.communication import Communication


# get initial setup
SERVER = "irc.quakenet.org"  # FIXME get from config
PORT = 6667  # FIXME get from config


class TestConnection(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_connects(self):
        communication = Communication([("irc.quakenet.org", 6667)])
        communication.start()
        self.assertTrue(communication.connected())


if __name__ == "__main__":
    unittest.main()
