import time
import shutil
import tempfile
import random
import unittest
import btctxstore
import storjnode
from crochet import setup
from storjnode.network.server import QUERY_TIMEOUT, WALK_TIMEOUT
setup()  # start twisted via crochet


QUERY_TIMEOUT = QUERY_TIMEOUT / 4
WALK_TIMEOUT = WALK_TIMEOUT / 4
SWARM_SIZE = 32
PORT = 4000


class TestMapNetwork(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.btctxstore = btctxstore.BtcTxStore(testnet=False)
        cls.swarm = []
        for i in range(SWARM_SIZE):

            # isolate swarm
            bootstrap_nodes = [("127.0.0.1", PORT + x) for x in range(i)][-20:]

            # create node
            node = storjnode.network.Node(
                cls.btctxstore.create_wallet(), port=(PORT + i), ksize=16,
                bootstrap_nodes=bootstrap_nodes, disable_data_transfer=True,
                refresh_neighbours_interval=0.0
            )
            cls.swarm.append(node)

        # stabalize network overlay
        time.sleep(WALK_TIMEOUT)
        for node in cls.swarm:
            node.refresh_neighbours()
        time.sleep(WALK_TIMEOUT)
        for node in cls.swarm:
            node.refresh_neighbours()
        time.sleep(WALK_TIMEOUT)

    @classmethod
    def tearDownClass(cls):
        for node in cls.swarm:
            node.stop()

    def test_mapnetwork(self):
        tempdir = tempfile.mkdtemp()
        try:
            random_peer = random.choice(self.swarm)
            netmap = storjnode.network.map.generate(random_peer)
            self.assertTrue(isinstance(netmap, dict))
            storjnode.network.map.render(netmap, tempdir, "test_map",
                                         view=False)
        finally:
            shutil.rmtree(tempdir)


if __name__ == "__main__":
    unittest.main()
