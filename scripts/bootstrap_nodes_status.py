#!/usr/bin/env python
# coding: utf-8


# always use faster native code
import os
os.environ["PYCOIN_NATIVE"] = "openssl"


import json  # NOQA
import argparse  # NOQA
import signal  # NOQA
import storjnode  # NOQA
import btctxstore  # NOQA
from twisted.internet import defer  # NOQA
from crochet import setup  # NOQA
from storjnode.common import DEFAULT_BOOTSTRAP_NODES  # NOQA
from kademlia.node import Node  # NOQA
from crochet import wait_for  # NOQA


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def parse_args():
    description = "Start a storjnode bootstrap only node."
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    return vars(parser.parse_args())


def make_config():
    config = storjnode.config.create()
    config["network"]["disable_data_transfer"] = True
    config["network"]["monitor"]["enable_crawler"] = False
    config["network"]["monitor"]["enable_responses"] = False
    storjnode.config.validate(config)
    return config


@wait_for(timeout=60)
def get_bootstrap_nodes_status(node, bootstrap_nodes):

    def on_success(results):
        assert(len(results) == len(bootstrap_nodes))
        for index in range(len(results)):
            success, ourid = results[index]
            ip, port = bootstrap_nodes[index]
            status = "ONLINE" if success else "DOWN"
            print("{ip}:{port} {status}".format(
                ip=ip, port=port, status=status
            ))

    ds = []
    for ip, port in bootstrap_nodes:
        knode = Node(b"X"*20, ip=ip, port=port)
        ds.append(node.server.protocol.callPing(knode))
    return defer.gatherResults(ds).addCallback(on_success)


def main():
    parse_args()
    config = make_config()
    wallet = btctxstore.BtcTxStore().create_wallet()
    node = None
    try:
        node = storjnode.network.Node(wallet, config=config)
        get_bootstrap_nodes_status(node, DEFAULT_BOOTSTRAP_NODES)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.stop()


if __name__ == "__main__":
    main()
