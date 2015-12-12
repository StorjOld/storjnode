#!/usr/bin/env python
import sys
import signal
import argparse
import time
import storjnode
from crochet import setup


log = storjnode.log.getLogger(__name__)


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def _parse_args(args):
    txt = """Crawl the network and generate a graph of all nodes.

    This is a simple crawlr that can only reach nodes with a public ip,
    so nodes behind a NAT can only be infered from public node routing tables.
    """
    parser = argparse.ArgumentParser(description=txt)

    # debug
    parser.add_argument('--debug', action='store_true',
                        help="Show debug information.")

    # quiet
    parser.add_argument('--quiet', action='store_true',
                        help="Don't show logging information.")

    # path
    parser.add_argument("--path", default=None,
                        help="Path to save the generate graph.")

    return vars(parser.parse_args(args=args))


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])

    node = None
    try:
        # setup node
        key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
        node = storjnode.network.Node(key)

        log.info("Giving nodes some time to find peers.")
        time.sleep(storjnode.network.WALK_TIMEOUT)

        netmap = storjnode.network.map.generate(node)
        print(storjnode.network.map.render(netmap, arguments["path"]))

    except KeyboardInterrupt:
        pass

    finally:
        log.info("Stopping node")
        if node is not None:
            node.stop()
