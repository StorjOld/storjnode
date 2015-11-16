#!/usr/bin/env python
# from examples/map_network.py
import time
import storjnode
import datetime
from crochet import setup
from storjnode.common import STORJ_HOME
setup()  # start twisted via crochet


key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
node = storjnode.network.Node(key)


print("Giving nodes some time to find peers.")
time.sleep(storjnode.network.WALK_TIMEOUT)


try:
    netmap = storjnode.network.map.generate(node)
    now = datetime.datetime.now()
    storjnode.util.ensure_path_exists(STORJ_HOME)
    storjnode.network.map.render(netmap, STORJ_HOME, "netmap %s" % str(now))
finally:
    node.stop()
