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


if os.environ.get("STORJNODE_USE_RELAYNODE"):
    INITIAL_RELAYNODES = [os.environ.get("STORJNODE_USE_RELAYNODE")]
else:
    INITIAL_RELAYNODES = ["niners.ctrl-c.se:6667"]
    # INITIAL_RELAYNODES = ["storj.sdo-srv.com:6667"]
    # INITIAL_RELAYNODES = ["irc.dal.net", "irc.eu.dal.net"]


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
    service = network.Service(INITIAL_RELAYNODES, key)
    try:
        service.connect()
        with open(arguments["filepath"], "rb") as f:
            data = f.read()
            service.send(arguments["receiver"], data)

        while service.has_queued_output():
            time.sleep(0.1)
    finally:
        service.disconnect()
