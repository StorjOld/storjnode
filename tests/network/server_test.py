import unittest
import storjnode
import signal
from storjnode.network.server import Server
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


class TestServer(unittest.TestCase):

    ##################################
    # test server's port closing     #
    ##################################

    def test_server_port_closing(self):
        # create server and start listen on some random port
        key = "5KaasrJx9KQymQ4zMffEPrsHxSn1bCnM9c3tbicp4Uunf1nrzyM"
        port = storjnode.util.get_unused_port()
        server1 = Server(key, port)
        port_handler = server1.listen(port)
        server1.set_port_handler(port_handler)
        server1.stop()

        # once again with the same port to test if it was closed properly
        server2 = Server(key, port)
        port_handler = server2.listen(port)
        server2.set_port_handler(port_handler)
        server2.stop()


if __name__ == "__main__":
    unittest.main()
