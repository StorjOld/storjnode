import os
import datetime
import time
import binascii
import random
import unittest
import btctxstore
import storjnode
from storjnode.network.server import QUERY_TIMEOUT, WALK_TIMEOUT
from crochet import setup
setup()  # start twisted via crochet

# change timeouts because everything is local
QUERY_TIMEOUT = QUERY_TIMEOUT / 5.0
WALK_TIMEOUT = WALK_TIMEOUT / 5.0

TEST_MESSAGE_TIMEOUT = 5
TEST_SWARM_SIZE = 64  # tested up to 256
TEST_MAX_MESSAGES = 2


class TestBlockingNode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        print("TEST: creating swarm")
        cls.btctxstore = btctxstore.BtcTxStore(testnet=False)
        cls.swarm = []
        for i in range(TEST_SWARM_SIZE):

            # isolate swarm
            bootstrap_nodes = [("127.0.0.1", 3000 + x) for x in range(i)][-1:]

            # create node
            node = storjnode.network.BlockingNode(
                cls.btctxstore.create_wallet(), port=(3000 + i),
                bootstrap_nodes=bootstrap_nodes,
                message_timeout=TEST_MESSAGE_TIMEOUT,
                max_messages=TEST_MAX_MESSAGES
            )
            cls.swarm.append(node)

            msg = "TEST: created node {0} @ 127.0.0.1:{1}"
            print(msg.format(node.get_hex_id(), node.port))

        # stabalize network overlay
        print("TEST: stabalize network overlay")
        time.sleep(WALK_TIMEOUT)
        for node in cls.swarm:
            node._server.bootstrap(node._server.bootstrappableNeighbors())
        time.sleep(WALK_TIMEOUT)
        for node in cls.swarm:
            node._server.bootstrap(node._server.bootstrappableNeighbors())
        time.sleep(WALK_TIMEOUT)

        #print("TEST: generating swarm graph")
        #name = "unittest_network_" + str(datetime.datetime.now())
        #storjnode.network.generate_graph(cls.swarm, name)

        print("TEST: created swarm")

    @classmethod
    def tearDownClass(cls):
        print("TEST: stopping swarm")
        for node in cls.swarm:
            node.stop()

    # FIXME expose and test is public rpc call

    #######################
    # test util functions #
    #######################

    def test_dbg_has_public_ip(self):  # for coverage
        random_peer = random.choice(self.swarm)
        result = random_peer.dbg_has_public_ip()
        self.assertTrue(isinstance(result, bool))

    def test_get_known_peers(self): # for coverage
        random_peer = random.choice(self.swarm)
        peers = random_peer.get_known_peers()
        self.assertTrue(isinstance(peers, list))
        for peerid in peers:
            self.assertTrue(isinstance(peerid, str))

    ########################
    # test relay messaging #
    ########################

    def _test_relay_message(self, sender, receiver, success_expected):
        testmessage = binascii.hexlify(os.urandom(32))
        receiver_id = receiver.get_id()
        sender.send_relay_message(receiver_id, testmessage)
        time.sleep(QUERY_TIMEOUT)  # wait until relayed

        if not success_expected:
            self.assertFalse(receiver.has_messages())

        else:  # success expected

            # check one message received
            self.assertTrue(receiver.has_messages())
            received = receiver.get_messages()
            self.assertEqual(len(received), 1)

            # check if correct message received
            source, message = received[0]["source"], received[0]["message"]
            self.assertEqual(testmessage, message)
            self.assertEqual(source, None)

    def test_relay_messaging_success(self):
        sender = self.swarm[0]
        receiver = self.swarm[TEST_SWARM_SIZE - 1]
        self._test_relay_message(sender, receiver, True)

    def test_relay_message_self(self):
        sender = self.swarm[0]
        receiver = self.swarm[0]
        self._test_relay_message(sender, receiver, False)

    def test_relay_messaging(self):
        senders = self.swarm[:]
        random.shuffle(senders)
        receivers = self.swarm[:]
        random.shuffle(receivers)
        for sender, receiver in zip(senders, receivers):
            msg = "TEST: sending relay message from {0} to {1}"
            print(msg.format(sender.get_hex_id(), receiver.get_hex_id()))
            self._test_relay_message(sender, receiver, sender is not receiver)

    def test_relay_message_to_void(self):  # for coverage
        random_peer = random.choice(self.swarm)
        void_id = b"void" * 5
        random_peer.send_relay_message(void_id, "into the void")
        time.sleep(QUERY_TIMEOUT)  # wait until relayed

    def test_max_relay_messages(self):  # for coverage
        random_peer = random.choice(self.swarm)
        void_id = b"void" * 5

        queued = random_peer.send_relay_message(void_id, "into the void")
        self.assertTrue(queued)
        queued = random_peer.send_relay_message(void_id, "into the void")
        self.assertTrue(queued)

        # XXX chance of failure if queue is processed during test
        queued = random_peer.send_relay_message(void_id, "into the void")
        self.assertFalse(queued)  # relay queue full

        time.sleep(QUERY_TIMEOUT)  # wait until relayed

    def test_relay_message_full_duplex(self):
        alice_node = storjnode.network.BlockingNode(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[("240.0.0.0", 1337)]
        )
        bob_node = storjnode.network.BlockingNode(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[("127.0.0.1", alice_node.port)]
        )
        time.sleep(QUERY_TIMEOUT)  # wait until network overlay stable, 2 peers
        try:
            alice_node.send_relay_message(bob_node.get_id(), "hi bob")
            time.sleep(QUERY_TIMEOUT)  # wait until relayed
            self.assertTrue(bob_node.has_messages())
            bob_node.send_relay_message(alice_node.get_id(), "hi alice")
            time.sleep(QUERY_TIMEOUT)  # wait until relayed
            self.assertTrue(alice_node.has_messages())
        finally:
            alice_node.stop()
            bob_node.stop()

    #########################
    # test direct messaging #
    #########################

    def _test_direct_message(self, sender, receiver, success_expected):
        testmessage = binascii.hexlify(os.urandom(32))
        receiver_id = receiver.get_id()
        sender_address = sender.send_direct_message(receiver_id, testmessage)

        if not success_expected:
            self.assertTrue(sender_address is None)  # was not received
            self.assertFalse(receiver.has_messages())

        else:  # success expected

            # check if got message
            self.assertTrue(sender_address is not None)  # was received

            # check returned transport address is valid
            ip, port = sender_address
            self.assertTrue(storjnode.util.valid_ip(ip))
            self.assertTrue(isinstance(port, int))
            self.assertTrue(port >= 0 and port <= 2**16)

            # check one message received
            self.assertTrue(receiver.has_messages())
            received = receiver.get_messages()
            self.assertEqual(len(received), 1)

            # check if correct message received
            source, message = received[0]["source"], received[0]["message"]
            self.assertEqual(testmessage, message)

            # check if message and sender ip/port match
            self.assertEqual(ip, source.ip)
            self.assertEqual(port, source.port)

    def test_direct_messaging_success(self):
        sender = self.swarm[0]
        receiver = self.swarm[TEST_SWARM_SIZE - 1]
        self._test_direct_message(sender, receiver, True)

    def test_direct_messaging_failure(self):
        testmessage = binascii.hexlify(os.urandom(32))
        sender = self.swarm[0]
        result = sender.send_direct_message(b"f483", testmessage)
        self.assertTrue(result is None)

    def test_direct_message_self(self):
        sender = self.swarm[0]
        receiver = self.swarm[0]
        self._test_direct_message(sender, receiver, False)

    def test_direct_messaging(self):
        senders = self.swarm[:]
        random.shuffle(senders)
        receivers = self.swarm[:]
        random.shuffle(receivers)
        for sender, receiver in zip(senders, receivers):
            msg = "TEST: sending direct message from {0} to {1}"
            print(msg.format(sender.get_hex_id(), receiver.get_hex_id()))
            self._test_direct_message(sender, receiver, sender is not receiver)

    def test_stale_messages_dropped(self):
        testmessage = binascii.hexlify(os.urandom(32))
        sender = self.swarm[0]
        receiver = self.swarm[TEST_SWARM_SIZE - 1]
        receiver_id = receiver.get_id()
        sender_address = sender.send_direct_message(receiver_id, testmessage)

        self.assertTrue(sender_address is not None)  # was received
        self.assertTrue(receiver.has_messages())  # check one message received
        time.sleep(TEST_MESSAGE_TIMEOUT + 1)  # wait until stale
        self.assertFalse(receiver.has_messages())  # check message was dropped

    def test_direct_message_to_void(self):  # for coverage
        peer = storjnode.network.BlockingNode(
            self.__class__.btctxstore.create_wallet(),
            bootstrap_nodes=[("240.0.0.0", 1337)],  # isolated peer
        )
        try:
            void_id = b"void" * 5
            result = peer.send_direct_message(void_id, "into the void")
            self.assertTrue(result is None)
        finally:
            peer.stop()

    def test_direct_message_full_duplex(self):
        alice_node = storjnode.network.BlockingNode(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[("240.0.0.0", 1337)]
        )
        bob_node = storjnode.network.BlockingNode(
            self.__class__.btctxstore.create_key(),
            bootstrap_nodes=[("127.0.0.1", alice_node.port)]
        )
        time.sleep(QUERY_TIMEOUT)  # wait until network overlay stable, 2 peers
        try:
            alice_node.send_direct_message(bob_node.get_id(), "hi bob")
            self.assertTrue(bob_node.has_messages())
            bob_node.send_direct_message(alice_node.get_id(), "hi alice")
            self.assertTrue(alice_node.has_messages())
        finally:
            alice_node.stop()
            bob_node.stop()

    def test_max_received_messages(self):
        sender = self.swarm[0]

        receiver = self.swarm[TEST_SWARM_SIZE - 1]
        receiver_id = receiver.get_id()

        message_a = binascii.hexlify(os.urandom(32))
        message_b = binascii.hexlify(os.urandom(32))
        message_c = binascii.hexlify(os.urandom(32))

        result = sender.send_direct_message(receiver_id, message_a)
        self.assertTrue(result is not None)
        result = sender.send_direct_message(receiver_id, message_b)
        self.assertTrue(result is not None)
        result = sender.send_direct_message(receiver_id, message_c)
        self.assertTrue(result is None)

        received = receiver.get_messages()
        self.assertEqual(len(received), 2)
        self.assertTrue(received[0]["message"] in [message_a, message_b])
        self.assertTrue(received[1]["message"] in [message_a, message_b])

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


if __name__ == "__main__":
    unittest.main()
