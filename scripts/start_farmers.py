#!/usr/bin/env python
# coding: utf-8


# always use faster native code
import os
os.environ["PYCOIN_NATIVE"] = "openssl"


import shutil  # NOQA
import tempfile  # NOQA
import argparse  # NOQA
import signal  # NOQA
import storjnode  # NOQA
import btctxstore  # NOQA
from crochet import setup  # NOQA


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


NUM_FARMERS = 10
START_PORT = 5000
STORE_SIZE = "1G"


def make_config(port):
    config = storjnode.config.create()
    config["network"]["port"] = port  # unique port
    config["storage"][tempfile.mkdtemp()] = {  # unique store folder
        "use_folder_tree": False, "limit": STORE_SIZE
    }
    storjnode.config.validate(config)
    return config


def main():
    farmers = []
    try:
        for i in range(NUM_FARMERS):
            config = make_config(START_PORT + i)  # unique config
            wallet = btctxstore.BtcTxStore().create_wallet()
            node = storjnode.api.StorjNode(wallet=wallet, config=config)
            node.farm()
    except KeyboardInterrupt:
        pass
    finally:
        for node in farmers:
            node.stop()
            for path in node.cfg_get_current()["storage"].keys():
                shutil.rmtree(path)  # delete store folder


if __name__ == "__main__":
    main()
