import time
import random
import threading
import unittest
import btctxstore
import storjnode
from twisted.internet import reactor


TEST_SWARM_SIZE = 50


class TestBlockingNode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.btctxstore = btctxstore.BtcTxStore(testnet=False)
        cls.swarm = []
        for i in range(TEST_SWARM_SIZE):

            # isolate swarm
            bootstrap_nodes = [
                ("127.0.0.1", 3000 + x) for x in range(i)
            ][-3:]  # only knows the last 3 nodes

            # create node
            node = storjnode.network.BlockingNode(
                cls.btctxstore.create_wallet(), port=(3000 + i),
                bootstrap_nodes=bootstrap_nodes, start_reactor=False
            )
            cls.swarm.append(node)

        # start reactor
        cls.reactor_thread = threading.Thread(
            target=reactor.run, kwargs={"installSignalHandlers": False}
        )
        cls.reactor_thread.start()

        # wait
        time.sleep(12)

    @classmethod
    def tearDownClass(cls):
        reactor.stop()
        cls.reactor_thread.join()

    def test_messaging_success(self):
        sending_peer = self.swarm[0]
        receiving_peer = self.swarm[TEST_SWARM_SIZE - 1]
        receiver_id = receiving_peer.get_id()
        sender_address = sending_peer.send_message(receiver_id, "testmessage")

        # check if got message
        self.assertTrue(sender_address is not None)  # was received

        # check returned transport address is valid
        ip, port = sender_address
        self.assertTrue(storjnode.util.valid_ip(ip))
        self.assertTrue(isinstance(port, int))
        self.assertTrue(port >= 0 and port <= 2**16)

        # check one message received
        self.assertTrue(receiving_peer.has_messages())
        received = receiving_peer.get_messages()
        self.assertEqual(len(received), 1)

        # check if message and sender ip/port match
        source, message = received[0]["source"], received[0]["message"]
        self.assertEqual("testmessage", message)
        self.assertEqual(ip, source.ip)
        self.assertEqual(port, source.port)

    def test_set_get_item(self):
        inserted = dict([
            ("key_{0}".format(i), "value_{0}".format(i)) for i in range(5)
        ])

        # insert mappping randomly into the swarm
        for key, value in inserted.items():
            random_peer = random.choice(self.swarm)
            random_peer[key] = value

        # retrieve values randomly
        for key, inserted_value in inserted.items():
            random_peer = random.choice(self.swarm)
            found_value = random_peer[key]
            self.assertEqual(found_value, inserted_value)


if __name__ == "__main__":
    unittest.main()
