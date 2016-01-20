#!/usr/bin/env python

# This example requires pygraphviz >= 1.3.1

# always use faster native code
import os
os.environ["PYCOIN_NATIVE"] = "openssl"


import json  # NOQA
import sys  # NOQA
import signal  # NOQA
import argparse  # NOQA
import time  # NOQA
import storjnode  # NOQA
import datetime  # NOQA
import btctxstore  # NOQA
from crochet import setup  # NOQA


TESTGROUPB_BOOTSTRAP_NODES = [
    ["104.236.1.59", 4653], ["159.203.64.230", 4653],
    ["78.46.188.55", 4653], ["158.69.201.105", 6770],
    ["162.218.239.6", 35839], ["192.187.97.131", 10322],
    ["185.86.149.128", 20560], ["185.61.148.22", 18825]
]


log = storjnode.log.getLogger(__name__)


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def _parse_args(args):
    txt = """Crawl the network and optionally generate a graph of all nodes.

    This is a simple crawler that can only reach nodes with a public ip,
    so nodes behind a NAT can only be infered from public node routing tables.
    """
    parser = argparse.ArgumentParser(description=txt)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--testgroupb', action='store_true',
                        help="Map the testgroupb network")
    parser.add_argument('--render', action='store_true',
                        help="Render graph (requires pygraphviz).")
    parser.add_argument("--path", default=None,
                        help="Path to save the generated graph.")
    return vars(parser.parse_args(args=args))


def print_stats(netmap):
    private_nodes = 0
    public_nodes = 0
    data = {}

    for nodeid, results in netmap.items():
        node_address = storjnode.util.node_id_to_address(nodeid)
        ip, port = results["addr"]
        has_peers = len(results["peers"]) > 0
        if has_peers:
            public_nodes += 1
        else:
            private_nodes += 1
        data[node_address] = {
            "transport": [ip, port], "is_public": has_peers
        }

    print(json.dumps(data, indent=2))
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

    import pygraphviz
    now = datetime.datetime.now()
    name = "network_map_%s" % now.strftime('%Y-%m-%d_%H:%M:%S')
    path = path or os.path.join(storjnode.common.STORJ_HOME,
                                "graphs", "%s.png" % name)
    path = storjnode.util.full_path(path)
    storjnode.util.ensure_path_exists(os.path.dirname(path))

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


def make_config(testgroupb):
    config = storjnode.config.create()
    if testgroupb:
        config["network"]["bootstrap_nodes"] = TESTGROUPB_BOOTSTRAP_NODES
    config["network"]["disable_data_transfer"] = True
    config["network"]["monitor"]["enable_crawler"] = False
    config["network"]["monitor"]["enable_responses"] = False
    storjnode.config.validate(config)
    return config


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])

    node = None
    try:
        # setup node
        key = btctxstore.BtcTxStore().create_key()
        config = make_config(arguments["testgroupb"])
        node = storjnode.network.Node(key, config=config)

        # shitty wait for network stabilization
        log.info("Shitty wait for network stabilization.")
        time.sleep(storjnode.network.WALK_TIMEOUT)
        node.refresh_neighbours()
        time.sleep(storjnode.network.WALK_TIMEOUT)
        node.refresh_neighbours()
        time.sleep(storjnode.network.WALK_TIMEOUT)

        # generate network map
        netmap = storjnode.network.map.generate(node)
        print_stats(netmap)
        if arguments["render"]:
            print(render(netmap, arguments["path"]))

    except KeyboardInterrupt:
        pass

    finally:
        log.info("Stopping node")
        if node is not None:
            node.stop()
