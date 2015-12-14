#!/usr/bin/env python
import sys
import argparse
import signal
import time
import storjnode
from crochet import setup

# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def _parse_args(args):
    txt = """TODO description"""
    parser = argparse.ArgumentParser(description=txt)

    # debug
    parser.add_argument('--debug', action='store_true',
                        help="Show debug information.")

    # quiet
    parser.add_argument('--quiet', action='store_true',
                        help="Don't show logging information.")

    # interval
    txt = "How often data is collected in seconds. Default: 3600"
    parser.add_argument("--interval", default=3600, type=int, help=txt)

    # limit
    txt = "Max nodes to scan, 0 entire network. Default: 20"
    parser.add_argument("--limit", default=20, type=int, help=txt)

    return vars(parser.parse_args(args=args))


# TODO add store args

if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])

    store_config = {}
    node = None
    monitor = None

    try:
        # FIXME generate key
        key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"

        # create a dht node
        node = storjnode.network.Node(key)

        # enable responses to info requests
        storjnode.network.messages.info.enable(node, store_config)

        # enable responses to peer requests
        storjnode.network.messages.peers.enable(node)

        print("Giving nodes some time to find peers.")
        time.sleep(storjnode.network.WALK_TIMEOUT)

        # start monitor
        print("Starting monitor")
        monitor = storjnode.network.monitor.Monitor(
            node, store_config,
            interval=arguments["interval"],
            limit=arguments["limit"]
        )

        # monitor forever
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    finally:
        print("Stopping monitor and node")
        if monitor is not None:
            monitor.stop()
        if node is not None:
            node.stop()
