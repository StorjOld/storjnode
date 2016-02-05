import os
# import sys
import json
import cProfile
from pstats import Stats
import hashlib
import signal
import threading
import tempfile
import time
import shutil
import binascii
import random
import unittest
import btctxstore
import storjnode
from storjkademlia.node import Node as KademliaNode
from storjnode.network.server import QUERY_TIMEOUT, WALK_TIMEOUT
from storjnode.network.file_transfer import enable_unl_requests
import storjnode.network.process_transfers
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


_log = storjnode.log.getLogger(__name__)


PROFILE = False
SWARM_SIZE = 8
PORT = storjnode.util.get_unused_port()
STORAGE_DIR = tempfile.mkdtemp()


def _test_config(storage_path, bootstrap_nodes):
    config = storjnode.config.create()
    config["network"]["refresh_neighbours_interval"] = 0
    config["network"]["bootstrap_nodes"] = bootstrap_nodes
    config["storage"] = {
        storage_path: {"limit": "5G", "use_folder_tree": False}
    }
    storjnode.config.validate(config)
    return config


class TestNode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        # start profiler
        if PROFILE:
            cls.profile = cProfile.Profile()
            cls.profile.enable()

        # isolate swarm
        bootstrap_nodes = [["127.0.0.1", PORT + i] for i in range(SWARM_SIZE)]

        # create swarm
        _log.info("TEST: creating swarm")
        cls.btctxstore = btctxstore.BtcTxStore(testnet=False)
        cls.swarm = []
        cls.network_id = hashlib.sha256(
            str(time.time()).encode("ascii")
        ).hexdigest()[0:16]
        for i in range(SWARM_SIZE):

            # create node
            storage_path = "{0}/peer_{1}".format(STORAGE_DIR, i)
            config = _test_config(storage_path, bootstrap_nodes)
            node = storjnode.network.Node(
                cls.btctxstore.create_wallet(), port=(PORT + i),
                config=config,
                nat_type="preserving",
                node_type="passive",
                disable_data_transfer=False,
                max_messages=10000000000000,
                network_id=cls.network_id
            )
            storjnode.network.messages.info.enable(node, config)
            storjnode.network.messages.peers.enable(node)
            enable_unl_requests(node)
            node.bandwidth_test.__init__(
                node.get_key(),
                node._data_transfer,
                node,
                0,
                1
            )
            node.bandwidth_test.enable()
            node.latency_tests.enable()
            node.bandwidth_test.test_timeout = 20000
            node.bandwidth_test.increasing_tests = 0
            cls.swarm.append(node)

            msg = "TEST: created node {0} @ 127.0.0.1:{1}"
            _log.info(msg.format(node.get_address(), node.port))

        # Make a list of all routing entries.
        cls.kademlia_nodes = None

        # Peer used for get unl requests.
        # FIXME remove unl_peer and node from swarm
        storage_path = "{0}/unl_peer".format(STORAGE_DIR)
        config = _test_config(storage_path, bootstrap_nodes)
        cls.test_get_unl_peer = storjnode.network.Node(
            cls.btctxstore.create_wallet(),
            config=config,
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=False
        )
        enable_unl_requests(cls.test_get_unl_peer)
        _log.info("TEST: created swarm")

    @classmethod
    def tearDownClass(cls):

        # stop swarm
        _log.info("TEST: stopping swarm")
        for node in cls.swarm:
            node.stop()
        cls.test_get_unl_peer.stop()
        shutil.rmtree(STORAGE_DIR)

        # get profiler stats
        if PROFILE:
            stats = Stats(cls.profile)
            stats.strip_dirs()
            stats.sort_stats('cumtime')
            stats.print_stats()

    def test_get_unl(self):
        node_id = self.test_get_unl_peer.get_id()
        got_unl = threading.Event()

        def on_error(err):
            _log.error(repr(err))
            return err

        def on_success(unl):
            got_unl.set()
        deferred = self.swarm[1].get_unl_by_node_id(node_id)
        deferred.addCallback(on_success).addErrback(on_error)
        got_unl.wait(timeout=WALK_TIMEOUT * 4)
        self.assertTrue(got_unl.isSet())

    #################################
    # test util and debug functions #
    #################################

    def test_refresh_neighbours_thread(self):
        interval = QUERY_TIMEOUT * 2
        config = _test_config(STORAGE_DIR, [["240.0.0.0", 1337]])
        config["network"]["refresh_neighbours_interval"] = interval
        alice_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            config=config,
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        alice_received = threading.Event()
        alice_node.add_message_handler(lambda n, m: alice_received.set())

        config = _test_config(STORAGE_DIR, [["127.0.0.1", alice_node.port]])
        config["network"]["refresh_neighbours_interval"] = interval
        bob_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            config=config,
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        bob_received = threading.Event()
        bob_node.add_message_handler(lambda n, m: bob_received.set())

        time.sleep(interval * 2)  # wait until network overlay stable, 2 peers

        try:
            alice_node.relay_message(bob_node.get_id(), "hi bob")
            bob_node.relay_message(alice_node.get_id(), "hi alice")
            bob_received.wait(timeout=QUERY_TIMEOUT)
            alice_received.wait(timeout=QUERY_TIMEOUT)
            self.assertTrue(bob_received.isSet())
            self.assertTrue(alice_received.isSet())
        finally:
            alice_node.stop()
            bob_node.stop()

    def test_has_public_ip(self):  # for coverage
        random_peer = random.choice(self.swarm)
        result = random_peer.sync_has_public_ip()
        self.assertTrue(isinstance(result, bool))

    def test_get_known_peers(self):  # for coverage
        random_peer = random.choice(self.swarm)
        peers = random_peer.get_known_peers()
        for peer in peers:
            self.assertTrue(isinstance(peer, KademliaNode))

    ########################
    # test relay messaging #
    ########################

    def _test_relay_message(self, sender, receiver, success_expected):
        testmessage = binascii.hexlify(os.urandom(32))
        receiver_id = receiver.get_id()

        received = []
        received_event = threading.Event()

        def handler(node, message):
            if message == testmessage:
                received.append(message)
                received_event.set()
        receiver.add_message_handler(handler)
        sender.relay_message(receiver_id, testmessage)

        try:
            if not success_expected:
                time.sleep(WALK_TIMEOUT)  # wait until relayed
                self.assertEqual(len(received), 0)

            else:  # success expected
                received_event.wait(timeout=WALK_TIMEOUT)

                # check one message received
                self.assertEqual(len(received), 1)

                # check if correct message received
                message = received[0]
                self.assertEqual(testmessage, message)
        finally:
            receiver.remove_message_handler(handler)

    def test_relay_messaging_success(self):
        sender = self.swarm[0]
        receiver = self.swarm[SWARM_SIZE - 1]
        self._test_relay_message(sender, receiver, True)

    def test_relay_message_self(self):
        sender = self.swarm[0]
        receiver = self.swarm[0]
        self._test_relay_message(sender, receiver, True)

    def test_relay_messaging(self):
        senders, receivers = storjnode.util.baskets(self.swarm, 2)
        random.shuffle(senders)
        random.shuffle(receivers)
        for sender, receiver in zip(senders, receivers):
            msg = "TEST: sending relay message from {0} to {1}"
            _log.info(msg.format(sender.get_address(), receiver.get_address()))
            self._test_relay_message(sender, receiver, True)

    def test_relay_message_to_void(self):  # for coverage
        random_peer = random.choice(self.swarm)
        void_id = b"void" * 5
        random_peer.relay_message(void_id, "into the void")
        time.sleep(QUERY_TIMEOUT)  # wait until relayed

    def test_relay_message_full_duplex(self):
        alice_node = self.swarm[0]
        bob_node = self.swarm[SWARM_SIZE - 1]
        alice_received = threading.Event()
        bob_received = threading.Event()

        def alice_handler(node, message):
            alice_received.set()

        def bob_handler(node, message):
            bob_received.set()

        alice_node.add_message_handler(alice_handler)
        bob_node.add_message_handler(bob_handler)
        alice_node.relay_message(bob_node.get_id(), "hi bob")
        bob_node.relay_message(alice_node.get_id(), "hi alice")
        bob_received.wait(timeout=QUERY_TIMEOUT)
        alice_received.wait(timeout=QUERY_TIMEOUT)

        try:
            self.assertTrue(bob_received.isSet())
            self.assertTrue(alice_received.isSet())
        finally:
            alice_node.remove_message_handler(alice_handler)
            bob_node.remove_message_handler(bob_handler)

    @unittest.skip("not implemented")
    def test_receive_invavid_hop_limit(self):
        pass  # FIXME test drop message if max hops exceeded or less than 0

    @unittest.skip("not implemented")
    def test_receive_invalid_distance(self):
        pass  # FIXME test do not relay away from dest

    def test_max_received_messages(self):
        alice_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            max_messages=2,
            config=_test_config(STORAGE_DIR, [["240.0.0.0", 1337]]),
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        bob_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            max_messages=2,
            config=_test_config(STORAGE_DIR, [["127.0.0.1", alice_node.port]]),
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        time.sleep(QUERY_TIMEOUT)  # wait until network overlay stable, 2 peers
        try:
            # XXX stop dispatcher
            bob_node._message_dispatcher_thread_stop = True
            bob_node._message_dispatcher_thread.join()

            a = binascii.hexlify(os.urandom(32))
            b = binascii.hexlify(os.urandom(32))
            c = binascii.hexlify(os.urandom(32))
            alice_node.relay_message(bob_node.get_id(), a)
            alice_node.relay_message(bob_node.get_id(), b)
            alice_node.relay_message(bob_node.get_id(), c)

            time.sleep(QUERY_TIMEOUT)  # wait until messages relayed

            # XXX check messages
            messages = bob_node.server.get_messages()
            self.assertEqual(len(messages), 2)

        finally:
            alice_node.stop()
            bob_node.stop()

    ###############################
    # test distributed hash table #
    ###############################

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

    ########################
    # test network mapping #
    ########################

    def test_mapnetwork(self):
        random_peer = random.choice(self.swarm)
        netmap = storjnode.network.map.generate(random_peer)
        self.assertTrue(isinstance(netmap, dict))

    #########################
    # test message handlers #
    #########################

    def test_message_handler_error(self):  # for coverage
        sender = self.swarm[0]
        receiver = self.swarm[SWARM_SIZE - 1]
        received_event = threading.Event()

        def handler(node, message):
            received_event.set()
            raise Exception("Test error")
        receiver.add_message_handler(handler)

        # handlers should not interfere with each other
        self._test_relay_message(sender, receiver, True)

        received_event.wait(timeout=QUERY_TIMEOUT)
        receiver.remove_message_handler(handler)

    ########################
    # test network monitor #
    ########################

    def test_network_monitor_service(self):
        limit = 1
        interval = 60 * 15
        crawled_event = threading.Event()
        results = {}

        def handler(key, shard):
            # storjnode.storage.shard.copy(shard, sys.stdout)
            results.update(dict(key=key, shard=shard))
            crawled_event.set()

        self.swarm.reverse()
        node = self.swarm[-1]
        for n in self.swarm:
            if n.sim_dht.has_mutex:
                if n.sim_dht.has_testable_neighbours():
                    node = n
                    break

        # Todo: figure out how to choose node that has mutex
        # and how to make it so it has more neighbours than other
        # mutex nodes
        monitor = storjnode.network.monitor.Monitor(
            node, limit=limit, interval=interval, on_crawl_complete=handler
        )

        crawled_event.wait(timeout=(interval + 5))
        monitor.stop()

        # check that limit nodes were scanned
        self.assertTrue(crawled_event.is_set())
        self.assertTrue(len(results), limit)
        shard = results["shard"]
        shard.seek(0)
        shard_data = json.loads(shard.read())
        monitor_data = json.loads(shard_data["data"])
        _log.info("CRAWLED DATA: {0}".format(shard_data["data"]))
        self.assertTrue(self.btctxstore.verify_signature_unicode(
            shard_data["address"], shard_data["signature"], shard_data["data"]
        ))
        self.assertEqual(len(monitor_data["processed"]), limit)

    def test_find_next_free_dataset_num(self):
        peer = random.choice(self.swarm)
        for i in range(10):
            key = storjnode.network.monitor.predictable_key(peer, i)
            peer[key] = "taken"
            num = storjnode.network.monitor.find_next_free_dataset_num(peer)
            self.assertEqual(num, i + 1)


if __name__ == "__main__":
    unittest.main()
