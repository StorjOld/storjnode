#!/usr/bin/env python
# from examples/usage.py

import time
import storjnode
import btctxstore

# node key must be a btc wif or hwif
node_key = btctxstore.BtcTxStore().create_key()

# start node on default port 4653
node = storjnode.network.BlockingNode(node_key)

time.sleep(12)  # Giving node some time to find peers

# The blocking node interface is very simple and behaves like a dict.
node["examplekey"] = "examplevalue"  # put key value pair into DHT
retrieved = node["examplekey"]  # retrieve value by key from DHT
print("{key} => {value}".format(key="examplekey", value=retrieved))

# A node does not know of its size or all entries.
try:
    node.items()
except NotImplementedError as e:
    print(e)

# A node can only write to the DHT.
try:
    del node["examplekey"]
except NotImplementedError as e:
    print(e)

# stop twisted reactor to disconnect from network
node.stop_reactor()
