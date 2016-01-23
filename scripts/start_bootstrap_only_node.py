#!/usr/bin/env python
# coding: utf-8


# always use faster native code
import os
os.environ["PYCOIN_NATIVE"] = "openssl"


import argparse  # NOQA
import signal  # NOQA
import storjnode  # NOQA
import btctxstore  # NOQA
from crochet import setup  # NOQA


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def parse_args():
    description = "Start a storjnode bootstrap only node."
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--noisy', action='store_true')
    parser.add_argument("--port", type=int, help="UDP port to listen on.")
    return vars(parser.parse_args())


def make_config(port):
    config = storjnode.config.create()
    config["network"]["port"] = port
    config["network"]["disable_data_transfer"] = True
    config["network"]["monitor"]["enable_crawler"] = False
    config["network"]["monitor"]["enable_responses"] = False
    storjnode.config.validate(config)
    return config


def main():
    args = parse_args()
    config = make_config(args["port"])
    wallet = btctxstore.BtcTxStore().create_wallet()
    node = None
    try:
        node = storjnode.api.StorjNode(wallet=wallet, config=config)
        node.farm(norpc=True)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.on_shutdown()


if __name__ == "__main__":
    main()
