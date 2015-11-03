#!/usr/bin/env python

import time
import storjnode
from crochet import setup
setup()  # start twisted via crochet

# create alice node (with bitcoin wif as node key)
alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
alice_node = storjnode.network.BlockingNode(alice_key, port=4653)
alice_id = alice_node.get_id()

# create bob node (with bitcoin hwif as node key)
bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
           "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
bob_node = storjnode.network.BlockingNode(bob_key, port=4654)
bob_id = alice_node.get_id()

time.sleep(12)  # Giving nodes some time to find peers

# send direct message
alice_node.send_direct_message(bob_id, "hi bob")  # blocking call
if(bob_node.has_messages()):
    print(bob_node.get_messages())

# send relayed message
bob_node.send_relay_message(alice_id, "hi alice")  # non blocking call
time.sleep(10)  # wait for it to be relayed
if(alice_node.has_messages()):
    print(alice_node.get_messages())

# stop nodes
alice_node.stop()
bob_node.stop()
