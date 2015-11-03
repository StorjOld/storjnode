#!/usr/bin/env python
# from examples/direct_message.py

import time
import storjnode
from crochet import setup, TimeoutError
setup()  # start twisted via crochet

# create alice node (with bitcoin wif as node key)
alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
alice_node = storjnode.network.BlockingNode(
    alice_key,
    bootstrap_nodes=[("240.0.0.0", 1337)]  # XXX isolate for now
)
alice_id = alice_node.get_id()

# create bob node (with bitcoin hwif as node key)
bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
           "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
bob_node = storjnode.network.BlockingNode(
    bob_key,
    bootstrap_nodes=[("127.0.0.1", alice_node.port)]  # XXX isolate for now
)
bob_id = alice_node.get_id()

print("Giving nodes some time to find peers.")
time.sleep(30)

try:
    # send direct message
    bob_node.send_direct_message(alice_id, "hi alice")  # blocking call
    if alice_node.has_messages():
        print("alice received:", alice_node.get_messages())
    else:
        print("direct message failed")

except TimeoutError:
    print("Got timeout error")

finally:  # stop nodes
    alice_node.stop()
    bob_node.stop()
