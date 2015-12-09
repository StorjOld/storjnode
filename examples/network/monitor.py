#!/usr/bin/env python
import signal
import time
import storjnode
from crochet import setup

# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)

storj_config = {}
node = None
monitor = None

try:
    # setup node
    key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
    node = storjnode.network.Node(key)  # create a dht node
    storjnode.network.messages.info.enable(node, storj_config)
    storjnode.network.messages.peers.enable(node)

    print("Giving nodes some time to find peers.")
    time.sleep(storjnode.network.WALK_TIMEOUT)

    # start monitor
    monitor = storjnode.network.monitor.Monitor(node, storj_config, interval=3600)

    # monitor forever
    while True:
        time.sleep(0.1)

except KeyboardInterrupt:
    pass

finally:
    print("Stopping monitor and node")
    if monitor is not None:
        monitor.stop()
    if node is not None:
        node.stop()
