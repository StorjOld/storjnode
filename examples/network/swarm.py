#!/usr/bin/python
import sys
import time
import argparse
import signal
import storjnode
from btctxstore import BtcTxStore
from crochet import setup

# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


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
    try:
        btctxstore = BtcTxStore(testnet=False)
        for i in range(arguments["size"]):
            port = arguments["ports"] + i
            node_key = btctxstore.create_key()
            peer = storjnode.network.Node(node_key, port=port,
                                          bootstrap_nodes=bootstrap_nodes)
            swarm.append(peer)
            print("Started peer {0} on port {1}.".format(i, port))
            time.sleep(0.1)

        # serve forever
        print("Running swarm with {0} ...".format(len(swarm)))
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        pass

    finally:
        print("Stopping nodes")
        for node in swarm:
            node.stop()
