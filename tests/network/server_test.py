import unittest
from storjnode.network.server import Server


class TestServer(unittest.TestCase):

    ##################################
    # test server's port closing     #
    ##################################

    def test_server_port_closing(self):
        # create server and start listen on port 12345
        test_result = True
        key = "5KaasrJx9KQymQ4zMffEPrsHxSn1bCnM9c3tbicp4Uunf1nrzyM"
        port = 12345
        server1 = Server(key, port)
        port_handler = server1.listen(port)
        server1.set_port_handler(port_handler)
        server1.stop()
        try:
            # once again with the same port to test if it was closed properly
            server2 = Server(key, port)
            port_handler = server2.listen(port)
            server2.set_port_handler(port_handler)
            server2.stop()
        except:
            test_result = False
        finally:
            self.assertTrue(test_result)


if __name__ == "__main__":
    unittest.main()
