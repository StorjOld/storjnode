import os
os.environ["PYCOIN_NATIVE"] = "openssl"

import psutil  # NOQA
import time  # NOQA
import threading  # NOQA
import binascii  # NOQA
import signal  # NOQA
import storjnode  # NOQA
import btctxstore  # NOQA
from crochet import setup  # NOQA
from storjnode.network.server import WALK_TIMEOUT  # NOQA


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


SIMULATE = False
PORT = 6000
SWARM_SIZE = 128
BOOTSTRAP_NODES = [["127.0.0.1", PORT + i] for i in range(SWARM_SIZE)]


def _make_config(port):
    config = storjnode.config.create()
    config["network"]["port"] = port
    if SIMULATE:
        config["network"]["bootstrap_nodes"] = BOOTSTRAP_NODES
    config["network"]["refresh_neighbours_interval"] = 0
    config["network"]["disable_data_transfer"] = True
    config["network"]["monitor"]["enable_crawler"] = False
    config["network"]["monitor"]["enable_responses"] = True
    storjnode.config.validate(config)
    return config


def _create_swarm(swarm, size):
    for i in range(size):
        wallet = btctxstore.BtcTxStore().create_wallet()
        node = storjnode.network.Node(
            wallet, port=(PORT + i),
            config=_make_config(PORT + 1),
        )
        swarm.append(node)
    return swarm


def _test_relay(sender, receiver):
    received = []
    received_event = threading.Event()

    def handler(node, message):
        received.append(message)
        received_event.set()
    receiver.add_message_handler(handler)

    testmessage = binascii.hexlify(os.urandom(32))
    receiver_id = receiver.get_id()
    sender.relay_message(receiver_id, testmessage)

    # check if correct message received
    received_event.wait(timeout=storjnode.network.server.WALK_TIMEOUT)
    assert(len(received) == 1)
    message = received[0]
    assert(testmessage == message)

    receiver.remove_message_handler(handler)


def _organize_overlay(swarm):
    time.sleep(WALK_TIMEOUT)
    print("refreshing peers")
    for node in swarm:
        node.refresh_neighbours()
    time.sleep(WALK_TIMEOUT)
    print("refreshing peers")
    for node in swarm:
        node.refresh_neighbours()
    time.sleep(WALK_TIMEOUT)
    print("refreshing peers")
    for node in swarm:
        node.refresh_neighbours()
    time.sleep(WALK_TIMEOUT)


if __name__ == "__main__":
    swarm = []
    successes = 0
    successes_duration = 0.0
    failures = 0
    try:
        swarm = _create_swarm(swarm, SWARM_SIZE)
        if not SIMULATE:
            _organize_overlay(swarm)
        numtests = len(swarm) ** 2
        for sender in swarm:
            for receiver in swarm:
                try:
                    print("{0} of {1} {2} -> {3}".format(
                        successes + failures, numtests,
                        sender.get_address(), receiver.get_address()
                    ))

                    start = time.time()
                    _test_relay(sender, receiver)
                    successes_duration += (time.time() - start)
                    successes += 1
                except AssertionError:
                    failures += 1
    finally:
        for node in swarm:
            node.stop()
        total = successes + failures
        print("SUCCESSFULL: {0}".format(successes))
        if successes > 0:
            avg_success = successes_duration / successes
            print("AVG SUCCESS TIME: {0}".format(avg_success))
        print("FAILURES: {0}".format(failures))
        if total > 0:
            print("RESULT: {0}%".format(
                float(successes) / float(total) * 100.0
            ))
