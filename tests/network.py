# start twisted
from crochet import setup
setup()

# make twisted use standard library logging module
from twisted.python import log
observer = log.PythonLoggingObserver()
observer.start()

# setup standard logging module
import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)


import os
import time
import binascii
import random
import unittest
import btctxstore
import storjnode


TEST_MESSAGE_TIMEOUT = 5
TEST_SWARM_SIZE = 20
TEST_MAX_MESSAGES = 2


class TestBlockingNode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
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

        # wait until network overlay stable
        time.sleep(20)

    @classmethod
    def tearDownClass(cls):
        for node in cls.swarm:
            node.stop()

    # FIXME expose and test is public rpc call

    #######################
    # test util functions #
    #######################

    def test_has_public_ip(self):
        random_peer = random.choice(self.swarm)
        result = random_peer.has_public_ip()
        self.assertTrue(isinstance(result, bool))

    ########################
    # test relay messaging #
    ########################

    def _test_relay_message(self, sender, receiver, success_expected):
        testmessage = binascii.hexlify(os.urandom(32))
        receiver_id = receiver.get_id()
        sender.send_relay_message(receiver_id, testmessage)
        time.sleep(2)  # wait for it to be relayed

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
            self._test_relay_message(sender, receiver, sender is not receiver)

    def test_relay_message_to_void(self):  # for coverage
        random_peer = random.choice(self.swarm)
        void_id = b"void" * 5
        random_peer.send_relay_message(void_id, "into the void")
        time.sleep(2)  # wait for it to be relayed

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

        time.sleep(2)  # wait for it to be relayed

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

    @unittest.skip("causes tests to not finish")  # FIXME make it work!
    def test_direct_message_to_void(self):  # for coverage
        isolated_peer = storjnode.network.BlockingNode(
            self.__class__.btctxstore.create_wallet(),
            bootstrap_nodes=[("240.0.0.0", 1337)],
        )
        void_id = b"void" * 5
        result = isolated_peer.send_direct_message(void_id, "into the void")
        self.assertTrue(result is None)

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
