#!/usr/bin/env python
# from examples/multinode_usage.py

import time
import storjnode
import btctxstore
from twisted.internet import reactor

peers = [("159.203.64.230", 4653)]  # known bootstrap peers

# create alice node
alice_wallet = btctxstore.BtcTxStore().create_wallet()  # hwif
alice_node = storjnode.network.BlockingNode(
    alice_wallet, port=4653, start_reactor=False, bootstrap_nodes=peers
)

# create bob node
bob_key = btctxstore.BtcTxStore().create_wallet()  # wif
bob_node = storjnode.network.BlockingNode(
    bob_key, port=4654, start_reactor=False, bootstrap_nodes=peers
)

# start twisted reactor yourself
reactor_thread = threading.Thread(target=reactor.run,
                                  kwargs={"installSignalHandlers": False})
reactor_thread.start()
time.sleep(12)  # Giving node some time to find peers

# use nodes
alice_node["examplekey"] = "examplevalue"  # alice inserts value
stored_value = bob_node["examplekey"]  # bob retrievs value
print("{key} => {value}".format(key="examplekey", value=stored_value)

# stop twisted reactor
reactor.stop()
reactor_thread.join()
