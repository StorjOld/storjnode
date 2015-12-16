#!/usr/bin/env python

# This example requires pygraphviz >= 1.3.1

import sys
import signal
import argparse
import time
import storjnode
import pygraphviz
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


def print_stats(netmap):
    private_nodes = 0
    public_nodes = 0
    for nodeid, results in netmap.items():
        if len(results["peers"]) > 0:
            public_nodes += 1
        else:
            private_nodes += 1
    print("Private nodes:", private_nodes)
    print("Public nodes:", public_nodes)
    print("Total nodes:", private_nodes + public_nodes)


def render(network_map, path=None):
    """ Render a network map.

    Args:
        network_map: The generated network map to render.
        path: The path to save the rendered output at.
              Saves to '~/.storj/graphs/network map TIMESTAMP.png' by default.
    """

    now = datetime.datetime.now()
    name = "network_map_%s" % now.strftime('%Y-%m-%d_%H:%M:%S')
    path = path or os.path.join(storjnode.common.STORJ_HOME,
                                "graphs", "%s.png" % name)
    path = util.full_path(path)
    util.ensure_path_exists(os.path.dirname(path))

    graph = pygraphviz.AGraph()  # (strict=False,directed=True)

    # add nodes
    for nodeid, results in network_map.items():
        node_address = storjnode.util.node_id_to_address(nodeid)
        ip, port = results["addr"]
        has_peers = len(results["peers"]) > 0
        graph.add_node(node_address, color='green' if has_peers else "blue")

    # add connections
    for nodeid, results in network_map.items():
        node_address = storjnode.util.node_id_to_address(nodeid)
        for peerid, ip, port in results["peers"]:
            peer_address = storjnode.util.node_id_to_address(peerid)
            graph.add_edge(node_address, peer_address)

    # render graph
    graph.layout(prog='dot')
    graph.draw(path, prog='circo')
    return path


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])

    node = None
    try:
        # setup node
        # FIXME generate key
        key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
        node = storjnode.network.Node(key)

        log.info("Giving nodes some time to find peers.")
        time.sleep(storjnode.network.WALK_TIMEOUT)

        netmap = storjnode.network.map.generate(node)
        print_stats(netmap)
        print(render(netmap, arguments["path"]))

    except KeyboardInterrupt:
        pass

    finally:
        log.info("Stopping node")
        if node is not None:
            node.stop()
