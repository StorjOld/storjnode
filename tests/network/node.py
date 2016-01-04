import os
import json
import cProfile
from pstats import Stats
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
from kademlia.node import Node as KademliaNode
from storjnode.network.server import QUERY_TIMEOUT, WALK_TIMEOUT
from storjnode.network.file_transfer import enable_unl_requests
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


_log = storjnode.log.getLogger(__name__)


PROFILE = False
SWARM_SIZE = 16
KSIZE = SWARM_SIZE / 2 if SWARM_SIZE / 2 < 20 else 20
PORT = 3000
STORAGE_DIR = tempfile.mkdtemp()
LAN_IP = storjnode.util.get_inet_facing_ip()


class TestNode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        # start profiler
        if PROFILE:
            cls.profile = cProfile.Profile()
            cls.profile.enable()

        # create swarm
        print("TEST: creating swarm")
        cls.btctxstore = btctxstore.BtcTxStore(testnet=False)
        cls.swarm = []
        for i in range(SWARM_SIZE):

            # isolate swarm
            bootstrap_nodes = [(LAN_IP, PORT + x) for x in range(i)][-20:]

            # create node
            node = storjnode.network.Node(
                cls.btctxstore.create_wallet(), port=(PORT + i), ksize=KSIZE,
                bootstrap_nodes=bootstrap_nodes,
                refresh_neighbours_interval=0.0,
                store_config={STORAGE_DIR: None},
                nat_type="preserving",
                node_type="passive",
                disable_data_transfer=False
            )
            storjnode.network.messages.info.enable(node, {})
            storjnode.network.messages.peers.enable(node)
            enable_unl_requests(node)
            node.bandwidth_test.enable()
            cls.swarm.append(node)

            msg = "TEST: created node {0} @ 127.0.0.1:{1}"
            print(msg.format(node.get_address(), node.port))

        # Peer used for get unl requests.
        unl_peer_bootstrap_nodes = [
            (LAN_IP, PORT + x)
            for x in range(SWARM_SIZE)
        ][-20:]
        cls.test_get_unl_peer = storjnode.network.Node(
            cls.btctxstore.create_wallet(),
            bootstrap_nodes=unl_peer_bootstrap_nodes,
            refresh_neighbours_interval=0.0,
            store_config={STORAGE_DIR: None},
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=False
        )
        enable_unl_requests(cls.test_get_unl_peer)

        # stabalize network overlay
        print("TEST: stabalize network overlay")
        time.sleep(WALK_TIMEOUT)
        for node in cls.swarm:
            node.refresh_neighbours()
        cls.test_get_unl_peer.refresh_neighbours()
        time.sleep(WALK_TIMEOUT)
        for node in cls.swarm:
            node.refresh_neighbours()
        cls.test_get_unl_peer.refresh_neighbours()
        time.sleep(WALK_TIMEOUT)

        print("TEST: created swarm")

    @classmethod
    def tearDownClass(cls):

        # stop swarm
        print("TEST: stopping swarm")
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

        def callback(unl):
            got_unl.set()
        self.swarm[1].get_unl_by_node_id(node_id).addCallback(callback)
        got_unl.wait(timeout=WALK_TIMEOUT * 4)
        self.assertTrue(got_unl.isSet())

    #################################
    # test util and debug functions #
    #################################

    def test_refresh_neighbours_thread(self):
        interval = QUERY_TIMEOUT * 2
        alice_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[("240.0.0.0", 1337)],
            store_config={STORAGE_DIR: None},
            refresh_neighbours_interval=interval,
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        alice_received = threading.Event()
        alice_node.add_message_handler(lambda n, m: alice_received.set())

        bob_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[(LAN_IP, alice_node.port)],
            store_config={STORAGE_DIR: None},
            refresh_neighbours_interval=interval,
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
        sender.relay_message(receiver_id, testmessage)

        received_event = threading.Event()

        def handler(node, message):
            received.append(message)
            received_event.set()
        received = []
        receiver.add_message_handler(handler)

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
            print(msg.format(sender.get_address(), receiver.get_address()))
            self._test_relay_message(sender, receiver, True)

    def test_relay_message_to_void(self):  # for coverage
        random_peer = random.choice(self.swarm)
        void_id = b"void" * 5
        random_peer.relay_message(void_id, "into the void")
        time.sleep(QUERY_TIMEOUT)  # wait until relayed

    def test_relay_message_full_duplex(self):
        alice_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[("240.0.0.0", 1337)],
            refresh_neighbours_interval=0.0,
            store_config={STORAGE_DIR: None},
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        alice_received = threading.Event()
        alice_node.add_message_handler(lambda n, m: alice_received.set())

        bob_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[(LAN_IP, alice_node.port)],
            refresh_neighbours_interval=0.0,
            store_config={STORAGE_DIR: None},
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        bob_received = threading.Event()
        bob_node.add_message_handler(lambda n, m: bob_received.set())

        time.sleep(QUERY_TIMEOUT)
        # wait until network overlay stable, 2 peers

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

    @unittest.skip("not implemented")
    def test_receive_invavid_hop_limit(self):
        pass  # FIXME test drop message if max hops exceeded or less than 0

    @unittest.skip("not implemented")
    def test_receive_invalid_distance(self):
        pass  # FIXME test do not relay away from dest

    def test_max_received_messages(self):
        alice_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[("240.0.0.0", 1337)],
            refresh_neighbours_interval=0.0,
            max_messages=2,
            store_config={STORAGE_DIR: None},
            nat_type="preserving",
            node_type="passive",
            disable_data_transfer=True
        )
        bob_node = storjnode.network.Node(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[(LAN_IP, alice_node.port)],
            refresh_neighbours_interval=0.0,
            max_messages=2,
            store_config={STORAGE_DIR: None},
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
        limit = KSIZE
        interval = WALK_TIMEOUT * 100

        crawled_event = threading.Event()
        results = {}

        def handler(key, shard):
            # storjnode.storage.shard.copy(shard, sys.stdout)
            results.update(dict(key=key, shard=shard))
            crawled_event.set()
        random_peer = random.choice(self.swarm)
        monitor = storjnode.network.monitor.Monitor(
            random_peer,
            {},  # FIXME use tmp dir
            limit=limit,
            interval=interval,
            on_crawl_complete=handler
        )

        crawled_event.wait(timeout=(interval + 5))
        monitor.stop()

        # check that `limit` nodes were scanned
        self.assertTrue(len(results) > 0)
        shard = results["shard"]
        shard.seek(0)
        crawl_data = json.loads(shard.read())
        print("CRAWLED DATA", crawl_data)
        self.assertEqual(len(crawl_data["processed"]), limit)


if __name__ == "__main__":
    unittest.main()
