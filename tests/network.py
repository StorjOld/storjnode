import random
import unittest
import btctxstore
import storjnode


TEST_SWARM_SIZE = 20


class TestNode(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False)
        self.swarm = []
        for i in range(TEST_SWARM_SIZE):
            print("creating peer {0}".format(i))
            bootstrap_nodes = [("127.0.0.1", 3000 + x) for x in range(i)][-5:]
            node = storjnode.network.kadpynode.KadPyNode({
                "nodekey": self.btctxstore.create_wallet(),
                "node_address": ("127.0.0.1", 3000 + i),
                "bootstrap_nodes": bootstrap_nodes,
            })
            node.start()
            self.swarm.append(node)

    def test_store_and_retreive(self):

        inserted = dict([
            ("key_{0}".format(i), "value_{0}".format(i)) for i in range(5)
        ])

        # insert mappping randomly into the swarm
        for key, value in inserted.items():
            print("inserting {0} -> {1}".format(key, value))
            random_peer = random.choice(self.swarm)
            random_peer.put(key, value)

        # retrieve values randomly
        for key, inserted_value in inserted.items():
            random_peer = random.choice(self.swarm)
            found_value = random_peer.get(key)
            print("found {0} -> {1}".format(key, found_value))
            self.assertEqual(found_value, inserted_value)


if __name__ == "__main__":
    unittest.main()
