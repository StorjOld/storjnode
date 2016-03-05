#!/usr/bin/env python
# coding: utf-8


# always use faster native code
import os
os.environ["PYCOIN_NATIVE"] = "openssl"


import time # NOQA
import shutil  # NOQA
import tempfile  # NOQA
import argparse  # NOQA
import signal  # NOQA
import storjnode  # NOQA
import btctxstore  # NOQA
import threading  # NOQA
from crochet import setup  # NOQA


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


NUM_FARMERS = 10
START_PORT = 5000
STORE_SIZE = "1G"
STORE_PREFIX = "farmer_"  # you may have to delete them yourself?


def make_config(port):
    prefix = STORE_PREFIX + str(port)
    path = tempfile.mkdtemp(prefix=prefix)  # unique store folder
    config = storjnode.config.create()
    config["network"]["port"] = port  # unique port
    config["storage"]= {
        path: {"use_folder_tree": False, "limit": STORE_SIZE}
    }

    storjnode.config.validate(config)
    return config


def main():
    farmers = []
    threads = []
    try:
        for i in range(NUM_FARMERS):
            print("Starting farmer")
            config = make_config(START_PORT + i)  # unique config
            wallet = btctxstore.BtcTxStore().create_wallet()
            node = storjnode.api.StorjNode(wallet=wallet, config=config)
            thread = threading.Thread(target=node.farm)
            thread.start()
            threads.append(thread)
            time.sleep(2)
        while True:
            time.sleep(1)  # run forever

    except KeyboardInterrupt:
        pass
    finally:
        for node in farmers:
            for path in node.cfg_get_current()["storage"].keys():
                shutil.rmtree(path)  # delete store folder


if __name__ == "__main__":
    main()
