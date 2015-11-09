#!/usr/bin/env python
# from examples/multinode.py

import time
import storjnode
from crochet import setup, TimeoutError
setup()  # start twisted via crochet

# create alice node (with bitcoin wif as node key)
alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
alice_node = storjnode.network.Node(alice_key)

# create bob node (with bitcoin hwif as node key)
bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
           "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
bob_node = storjnode.network.Node(bob_key)

print("Giving nodes some time to find peers.")
time.sleep(30)

try:
    # use nodes
    alice_node["examplekey"] = "examplevalue"  # alice inserts value
    stored_value = bob_node["examplekey"]  # bob retrievs value
    print("{key} => {value}".format(key="examplekey", value=stored_value))

except TimeoutError:
    print("Got timeout error")

finally:  # stop nodes
    alice_node.stop()
    bob_node.stop()
