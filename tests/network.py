import time
import random
import threading
import unittest
import btctxstore
import storjnode
from twisted.internet import reactor


TEST_SWARM_SIZE = 10


class TestNode(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False)
        self.swarm = []
        for i in range(TEST_SWARM_SIZE):
            bootstrap_nodes = [
                ("127.0.0.1", 3000 + x) for x in range(i)
            ][-5:]  # only the last 5 nodes
            node = storjnode.network.BlockingNode(
                self.btctxstore.create_wallet(), port=(3000 + i),
                bootstrap_nodes=bootstrap_nodes, start_reactor=False
            )
            self.swarm.append(node)

        # start reactor
        self.reactor_thread = threading.Thread(
            target=reactor.run, kwargs={"installSignalHandlers": False}
        )
        self.reactor_thread.start()

        # wait
        time.sleep(12)

    def tearDown(self):
        for peer in self.swarm:
            del peer

        # stop reactor
        reactor.stop()
        self.reactor_thread.join()

    def test_swarm(self):
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
