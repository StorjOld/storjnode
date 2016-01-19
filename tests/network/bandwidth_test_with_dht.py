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
from pyp2p.lib import parse_exception
from kademlia.node import Node as KademliaNode
from storjnode.network.server import QUERY_TIMEOUT, WALK_TIMEOUT
from storjnode.network.file_transfer import enable_unl_requests
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


_log = storjnode.log.getLogger(__name__)


PROFILE = False
SWARM_SIZE = 4
KSIZE = SWARM_SIZE / 2 if SWARM_SIZE / 2 < 20 else 20
PORT = 4000
STORAGE_DIR = tempfile.mkdtemp()

print("Storage dir: " + str(STORAGE_DIR))

LAN_IP = storjnode.util.get_inet_facing_ip()
swarm = []


def _test_config(storage_path):
    config = storjnode.config.create()
    fs_format = storjnode.util.get_fs_type(storage_path)
    config["storage"] = {
        storage_path: {
            "limit": storjnode.storage.manager.DEFAULT_STORE_LIMIT,
            "use_folder_tree": fs_format == "vfat",
        }
    }
    storjnode.config.validate(config)
    return config

# isolate swarm
btctxstore = btctxstore.BtcTxStore(testnet=False)
for i in range(0, 2):
    bootstrap_nodes = [(LAN_IP, PORT + x) for x in range(i)][-20:]
    storage_path = "{0}/peer_{1}".format(STORAGE_DIR, i)
    config = _test_config(storage_path)
    node = storjnode.network.Node(
        btctxstore.create_wallet(), port=(PORT + i), ksize=KSIZE,
        bootstrap_nodes=bootstrap_nodes,
        refresh_neighbours_interval=0.0,
        config=config,
        nat_type="preserving",
        node_type="passive",
        disable_data_transfer=False,
        max_messages=1024
    )
    print(node._data_transfer.net.passive_port)
    print(node._data_transfer.net.unl.value)
    node.bandwidth_test.test_timeout = 1000000
    node.bandwidth_test.increasing_tests = 1
    node.bandwidth_test.increases = {
        1: 4,
        4: 10,
        10: 20,
        20: 40
    }
    print()

    assert(node._data_transfer is not None)
    # node.repeat_relay.thread_running = False
    storjnode.network.messages.info.enable(node, {})
    storjnode.network.messages.peers.enable(node)
    enable_unl_requests(node)
    node.bandwidth_test.enable()
    swarm.append(node)

# stabalize network overlay
print("TEST: stabalize network overlay")
time.sleep(WALK_TIMEOUT)

for node in swarm:
    node.refresh_neighbours()

time.sleep(WALK_TIMEOUT)

for node in swarm:
    node.refresh_neighbours()

time.sleep(WALK_TIMEOUT)

# Show bandwidth.
still_running = 1


def show_bandwidth(results):
    print(results)
    global test_success
    global still_running
    print("IN SUCCESS CALLBACK!?@#!@#?!@?#")
    test_success = 1
    still_running = 0
    return
    try:
        _log.debug(results)
        print(swarm[0].bandwidth_test.test_size)
        print(swarm[0].bandwidth_test.active_test)
        print(swarm[0].bandwidth_test.results)
        print(swarm[0].bandwidth_test.test_node_unl)
        print(swarm[0].bandwidth_test.start_time)
        print(swarm[0].bandwidth_test.data_id)
        print(swarm[0].bandwidth_test.handlers)

        print("starting next bandwiwdth test!")

        def success_callback_2(results):
            global still_running
            still_running = 0
            print("IN FINAL SYUCCESS CALLBACK!?!")
            print(results)

        d = swarm[0].test_bandwidth(swarm[1].get_id())
        d.addCallback(success_callback_2)
    except Exception as e:
        print(parse_exception(e))
        exit()

print(swarm)
d = swarm[0].test_bandwidth(swarm[1].get_id())
d.addCallback(show_bandwidth)
print("Stablised")

while still_running:
    time.sleep(0.1)


for node in swarm:
    node.stop()
