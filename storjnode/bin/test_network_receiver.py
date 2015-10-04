#!/usr/bin/python3

import logging

LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

import time
import os
import sys
import argparse
from storjnode import network


RELAYNODES = [("irc.quakenet.org", 6667)]
USERHOME = os.path.expanduser("~")
STOREPATH = os.path.join(USERHOME, ".storjnode", "test_network_receiver")


def get_args():
    class ArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)
    description = "Dataserve client command-line interface."
    parser = ArgumentParser(description=description)
    parser.add_argument("wallet", help="Bitcoin WIF is this nodes identity"
                                       " and for signing.")
    parser.add_argument("--storepath" , default=STOREPATH,
                        help="Path to store data. default=%s" % STOREPATH)
    return vars(parser.parse_args())


if __name__ == "__main__":
    arguments = get_args()
    service = network.Service(RELAYNODES, arguments["wallet"])
    service.connect()
    while True:
        received = service.get_received()
        for node, data in received.items():
            # FIXME make storepath dirs
            path = os.path.realpath(os.path.join(arguments["storepath"], node))
            with open(path, "ab") as f:
                f.write(data)
        time.sleep(0.1)
