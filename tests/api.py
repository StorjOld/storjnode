import signal
import random
import shutil
import unittest
import tempfile
import storjnode
from btctxstore import BtcTxStore
from crochet import setup


SWARM_SIZE = 8
STORAGE_DIR = tempfile.mkdtemp()
PORT = 4000


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def _test_config(storage_path, port):
    config = storjnode.config.create()
    bootstrap_nodes = [["127.0.0.1", PORT + i] for i in range(SWARM_SIZE)]
    config["network"]["bootstrap_nodes"] = bootstrap_nodes
    config["network"]["port"] = port
    config["network"]["disable_data_transfer"] = True
    config["network"]["monitor"]["enable_crawler"] = False
    config["network"]["monitor"]["enable_responses"] = False
    config["storage"] = {
        storage_path: { "limit": "10G", "use_folder_tree": False }
    }
    storjnode.config.validate(config)
    return config


class TestApi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        btctxstore = BtcTxStore()
        cls.swarm = []
        for i in range(SWARM_SIZE):
            storage_path = "{0}/peer_{1}".format(STORAGE_DIR, i)
            config = _test_config(storage_path, PORT + i)
            cls.swarm.append(storjnode.api.StorjNode(
                wallet=btctxstore.create_wallet(), config=config
            ))

    @classmethod
    def tearDownClass(cls):
        for peer in cls.swarm:
            peer.on_shutdown()
        shutil.rmtree(STORAGE_DIR)

    def test_info(self):
        peer = random.choice(self.swarm)
        info = peer.info()
        # FIXME use schema to check format
        self.assertEqual(len(info["network"]["peers"]), SWARM_SIZE)

    ##########
    # CONFIG #
    ##########

    def test_cfg_current(self):
        peer = random.choice(self.swarm)
        current = peer.cfg_current()
        storjnode.config.validate(current)

    def test_cfg_default(self):
        peer = random.choice(self.swarm)
        default = peer.cfg_default()
        self.assertEqual(default, storjnode.config.create())

    def test_cfg_schema(self):
        peer = random.choice(self.swarm)
        schema = peer.cfg_schema()
        self.assertEqual(schema, storjnode.config.SCHEMA)

    #######
    # DHT #
    #######

    def test_dht(self):
        inserted = dict([
            ("key_{0}".format(i), "value_{0}".format(i)) for i in range(5)
        ])

        # insert mappping randomly into the swarm
        for key, value in inserted.items():
            peer = random.choice(self.swarm)
            self.assertTrue(peer.dht_put(key, value))

        # retrieve values randomly
        for key, inserted_value in inserted.items():
            peer = random.choice(self.swarm)
            found_value = peer.dht_get(key)
            self.assertEqual(found_value, inserted_value)

    ##########
    # EVENTS #
    ##########

    def test_msg_notify(self):
        pass

    def test_msg_list(self):
        pass

    def test_msg_publish(self):
        pass

    def test_msg_subscribe(self):
        pass

    def test_msg_unsubscribe(self):
        pass


if __name__ == "__main__":
    unittest.main()
