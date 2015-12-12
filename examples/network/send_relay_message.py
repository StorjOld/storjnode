#!/usr/bin/env python
# coding: utf-8

import time
import btctxstore
import storjnode
import argparse
import signal
import sys
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def parse_args(args):
    description = "Start a storjnode that only runs the DHT."
    parser = argparse.ArgumentParser(description=description)

    # --debug
    msg = "Show debug information."
    parser.add_argument('--debug', action='store_true', help=msg)

    # --quiet
    msg = "Only show warning and error information."
    parser.add_argument('--quiet', action='store_true', help=msg)

    # nodeid
    msg = "The node to receive the message, as a bitcoin address."
    parser.add_argument("nodeid", default=None, help=msg)

    # message
    msg = "The message to send to the node."
    parser.add_argument("message", help=msg)

    return vars(parser.parse_args(args=args))


def main(args):
    arguments = parse_args(args)
    node = None
    key = btctxstore.BtcTxStore().create_wallet()  # random key
    try:
        # start node
        node = storjnode.network.Node(key, disable_data_transfer=True)

        print("Giving nodes some time to find peers.")
        time.sleep(storjnode.network.WALK_TIMEOUT)

        # send relay message
        receiverid = arguments["nodeid"]
        message = arguments["message"]
        node.relay_message(storjnode.util.address_to_node_id(receiverid),
                           message)

    except KeyboardInterrupt:
        pass

    finally:
        if node is not None:
            node.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
