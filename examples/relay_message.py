#!/usr/bin/env python
# from examples/relay_message.py
import time
import binascii
import storjnode
from crochet import setup, TimeoutError
setup()  # start twisted via crochet


# create alice node (with bitcoin wif as node key)
alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
alice_node = storjnode.network.Node(
    alice_key, bootstrap_nodes=[("240.0.0.0", 1337)]  # isolate
)


# create bob node (with bitcoin hwif as node key)
bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
           "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
bob_node = storjnode.network.Node(
    bob_key, bootstrap_nodes=[("127.0.0.1", alice_node.port)]  # isolate
)


# add message handler to bob node
def message_handler(source, message):
    src = binascii.hexlify(source) if source is not None else "unknown"
    print("%s from %s" % (message, src))
alice_node.add_message_handler(message_handler)


print("Giving nodes some time to find peers.")
time.sleep(storjnode.network.WALK_TIMEOUT)


try:
    # send relayed message (non blocking call)
    bob_node.relay_message(alice_node.get_id(), "hi alice")
    time.sleep(storjnode.network.WALK_TIMEOUT)  # wait for it to be relayed

except TimeoutError:
    print("Got timeout error")

finally:  # stop nodes
    alice_node.stop()
    bob_node.stop()
