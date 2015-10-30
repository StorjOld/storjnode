#!/usr/bin/env python
# from examples/multinode.py

import time
import storjnode
from crochet import setup

setup()  # start twisted via crochet

# create alice node (with bitcoin wif as node key)
alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
alice_node = storjnode.network.BlockingNode(alice_key, port=4653)

# create bob node (with bitcoin hwif as node key)
bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
           "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
bob_node = storjnode.network.BlockingNode(bob_key, port=4654)

time.sleep(12)  # Giving nodes some time to find peers

# use nodes
alice_node["examplekey"] = "examplevalue"  # alice inserts value
stored_value = bob_node["examplekey"]  # bob retrievs value
print("{key} => {value}".format(key="examplekey", value=stored_value))

# stop nodes
alice_node.stop()
bob_node.stop()
