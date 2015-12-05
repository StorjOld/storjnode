#!/usr/bin/env python
import signal
import time
import storjnode
from crochet import setup

# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)

# setup node
key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
node = storjnode.network.Node(key)

try:
    print("Giving nodes some time to find peers.")
    time.sleep(storjnode.network.WALK_TIMEOUT)
    results = storjnode.network.monitor.run(node)
    print("Monitor results: {0} {1} {2}".format(*results))

except KeyboardInterrupt:
    pass

finally:
    print("Stopping node")
    node.stop()
