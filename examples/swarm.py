#!/usr/bin/python
# coding: utf-8

# start twisted
from crochet import setup
setup()

# make twisted use standard library logging module
from twisted.python import log
observer = log.PythonLoggingObserver()
observer.start()

# setup standard logging module
import sys
import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
if "--debug" in sys.argv:  # debug shows everything
    logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)
elif "--quiet" in sys.argv:  # quiet disables logging
    logging.basicConfig(format=LOG_FORMAT, level=60)
else:  # default level INFO
    logging.basicConfig(format=LOG_FORMAT, level=logging.WARNING)

import time
import argparse
import storjnode
from btctxstore import BtcTxStore


def _parse_args(args):
    parser = argparse.ArgumentParser(description="Start storjnode swarm.")

    # debug
    parser.add_argument('--debug', action='store_true',
                        help="Show debug information.")

    # quiet
    parser.add_argument('--quiet', action='store_true',
                        help="Don't show logging information.")

    # isolate
    parser.add_argument('--isolate', action='store_true',
                        help="Isolate swarm form main network.")

    # ports
    default = 5000
    msg = "Where swarm ports start from. Default: {0}"
    parser.add_argument("--ports", default=default, type=int,
                        help=msg.format(default))

    # size
    default = 20
    msg = "Number of nodes in the swarm. Default: {0}"
    parser.add_argument("--size", default=default, type=int,
                        help=msg.format(default))


    return vars(parser.parse_args(args=args))


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])

    # isolate swarm if requested
    bootstrap_nodes = None
    if arguments["isolate"]:
        bootstrap_nodes = [("127.0.0.1", arguments["ports"])]

    swarm = []
    btctxstore = BtcTxStore(testnet=False)
    for i in range(arguments["size"]):
        port = arguments["ports"] + i
        node_key = btctxstore.create_key()
        peer = storjnode.network.BlockingNode(node_key, port=port,
                                              bootstrap_nodes=bootstrap_nodes)
        swarm.append(peer)
        print("Started peer {0} on port {1}.".format(i, port))
        time.sleep(0.2)

    # serve forever
    print("Running swarm with {0} ...".format(len(swarm)))
    while True:
        time.sleep(1)
