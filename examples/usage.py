#!/usr/bin/env python
# from examples/usage.py

import time
import storjnode
from crochet import setup, TimeoutError
setup()  # start twisted via crochet

# start node (use bitcoin wif or hwif as node key)
node_key = "KzygUeD8qXaKBFdJWMk9c6AVib89keoZFBNdFBsj73kYZfAc4n1j"
node = storjnode.network.Node(node_key)

print("Giving nodes some time to find peers.")
time.sleep(30)

try:
    # The blocking node interface is very simple and behaves like a dict.
    node["examplekey"] = "examplevalue"  # put key value pair into DHT
    retrieved = node["examplekey"]  # retrieve value by key from DHT
    print("{key} => {value}".format(key="examplekey", value=retrieved))

    # A node cannot know of the DHT size or all entries.
    try:
        node.items()
    except NotImplementedError as e:
        print(repr(e))

    # A node can only write to the DHT.
    try:
        del node["examplekey"]
    except NotImplementedError as e:
        print(repr(e))

except TimeoutError:
    print("Got timeout error")

finally:
    node.stop()
