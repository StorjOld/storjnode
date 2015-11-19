#!/usr/bin/env python
import time
import signal
import storjnode
from crochet import setup, TimeoutError

# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)

# start node (use bitcoin wif or hwif as node key)
node_key = "KzygUeD8qXaKBFdJWMk9c6AVib89keoZFBNdFBsj73kYZfAc4n1j"
node = storjnode.network.Node(node_key)

try:
    print("Giving nodes some time to find peers.")
    time.sleep(storjnode.network.WALK_TIMEOUT)

    # The blocking node interface is very simple and behaves like a dict.
    node["examplekey"] = "examplevalue"  # put key value pair into DHT
    retrieved = node["examplekey"]  # retrieve value by key from DHT
    print("{key} => {value}".format(key="examplekey", value=retrieved))

except TimeoutError:
    print("Got timeout error")

except KeyboardInterrupt:
    pass

finally:
    print("Stopping node")
    node.stop()
