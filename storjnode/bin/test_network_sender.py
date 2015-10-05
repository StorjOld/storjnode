#!/usr/bin/python3

import logging

LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

import time
import os
import sys
import argparse
from btctxstore import BtcTxStore
from storjnode import network


RELAYNODES = ["irc.quakenet.org:6667"]


def get_args():
    class ArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)
    description = "Dataserve client command-line interface."
    parser = ArgumentParser(description=description)
    parser.add_argument("receiver" , help="Address of the receiving node.")
    parser.add_argument("filepath" , help="File to send to receiving node.")
    return vars(parser.parse_args())


if __name__ == "__main__":
    arguments = get_args()
    btctxstore = BtcTxStore()
    key = btctxstore.create_key()
    address = btctxstore.get_address(key)
    logging.info("USING ON TIME ADDRESS %s", address)
    service = network.Service(RELAYNODES, key)
    try:
        service.connect()
        with open(arguments["filepath"], "rb") as f:
            data = f.read()
            service.send(arguments["receiver"], data)

        while service.has_queued_output():
            time.sleep(0.1)
    finally:
        service.disconnect()
