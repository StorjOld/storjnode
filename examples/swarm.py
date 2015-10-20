#!/usr/bin/python
# coding: utf-8

import logging

# set logging before anything is imported
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)

import storjnode
from btctxstore import BtcTxStore
from twisted.internet import reactor

# TODO get this from args
STARTING_PORT = 3000
SWARM_SIZE = 10

btctxstore = BtcTxStore(testnet=False)
swarm = []

for i in range(SWARM_SIZE):
    port = STARTING_PORT + i
    key = btctxstore.create_key()
    peer = storjnode.network.BlockingNode(key, port=port, start_reactor=False)
    swarm.append(peer)

# serve forever
print("Starting with {0} peers ...".format(len(swarm)))
reactor.run()
