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
PORT = 3000
STORAGE_DIR = tempfile.mkdtemp()
storjnode.network.process_transfers.CON_TIMEOUT = 10000000000
storjnode.network.process_transfers.HANDSHAKE_TIMEOUT = 100000000000

print("Storage dir: " + str(STORAGE_DIR))

LAN_IP = storjnode.util.get_inet_facing_ip()
swarm = []

# isolate swarm
btctxstore = btctxstore.BtcTxStore(testnet=False)
for i in range(0, 2):
    bootstrap_nodes = [(LAN_IP, PORT + x) for x in range(i)][-20:]
    node = storjnode.network.Node(
        btctxstore.create_wallet(), port=(PORT + i), ksize=KSIZE,
        bootstrap_nodes=bootstrap_nodes,
        refresh_neighbours_interval=0.0,
        store_config={"{0}/peer_{1}".format(STORAGE_DIR, i): None},
        nat_type="preserving",
        node_type="passive",
        disable_data_transfer=False
    )
    print(node._data_transfer.net.passive_port)
    print(node._data_transfer.net.unl.value)
    node.bandwidth_test.test_timeout = 100000000000
    print()

    assert(node._data_transfer is not None)
    node.repeat_relay.thread_running = False
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
    print("IN SUCCESS CALLBACK!?@#!@#?!@?#")
    test_success = 1
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
