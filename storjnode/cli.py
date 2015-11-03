# File transfer.
from .network.file_transfer import FileTransfer, process_transfers
from .network.pyp2p.unl import UNL, is_valid_unl
from .network.pyp2p.net import Net
from .network.pyp2p.dht_msg import DHT

# start twisted
from crochet import setup
setup()

# make twisted use standard library logging module
from twisted.python import log
observer = log.PythonLoggingObserver()
observer.start()

# setup standard logging module
import sys
import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
if "--debug" in sys.argv:  # debug shows everything
    logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)
elif "--quiet" in sys.argv:  # quiet disables logging
    logging.basicConfig(format=LOG_FORMAT, level=60)
else:  # default level INFO
    logging.basicConfig(format=LOG_FORMAT, level=logging.WARNING)

from collections import OrderedDict
import binascii
import argparse
import time
import storjnode
import btctxstore
import json
import hashlib
import sys
import os
import shutil
import random

def _add_programm_args(parser):

    # port
    default = None
    parser.add_argument("--dht_port", default=default, type=int,
                        help="Node DHT port, random user port by default.")

    parser.add_argument("--passive_port", default=default, type=int,
                        help="Port to receive inbound TCP connections on when nodes direct connect to us.")

    parser.add_argument("--storage_path", default=default,
                        help="Where to store files hosted.")

    # bootstrap
    default = None
    msg = "Optional bootstrap node. Example: 127.0.0.1:1234"
    parser.add_argument("--bootstrap", default=default,
                        help=msg.format(default))

    # node_key
    default = None
    msg = ("Bitcoin wif/hwif for node id, auth and signing. "
           "If not given a one will be generated.")
    parser.add_argument("--node_key", default=default,
                        help=msg)

    # debug
    parser.add_argument('--debug', action='store_true',
                        help="Show debug information.")

    # quiet
    parser.add_argument('--quiet', action='store_true',
                        help="Only show warning and error information.")


def _add_put(command_parser):
    parser = command_parser.add_parser(
        "put", help="Put key, value pair into DHT."
    )
    parser.add_argument("key", help="Key to retrieve value.")
    parser.add_argument("value", help="Value to insert into the DHT")


def _add_get(command_parser):
    parser = command_parser.add_parser(
        "get", help="Get value from DHT."
    )
    parser.add_argument("key", help="Key to retrieve value by.")


def _add_run(command_parser):
    command_parser.add_parser(
        "run", help="Run node and extend DHT network."
    )


def _add_version(command_parser):
    command_parser.add_parser(
        "version", help="Show version number and exit."
    )


def _add_relay_message(command_parser):
    parser = command_parser.add_parser(
        "relay_message", help="Send relay message to a peer."
    )
    parser.add_argument("id", help="ID of the peer to receive the message.")
    parser.add_argument("message", help="The message to sent the peer.")


def _add_direct_message(command_parser):
    parser = command_parser.add_parser(
        "direct_message", help="Send direct message to a peer."
    )
    parser.add_argument("id", help="ID of the peer to receive the message.")
    parser.add_argument("message", help="The message to sent the peer.")

def _add_host_file(command_parser):
    parser = command_parser.add_parser(
        "host_file", help="Copy a local file to the storage folder and return its data ID and file size."
    )
    parser.add_argument("path", help="Local path of file to host on the network.")

def _add_upload(command_parser):
    parser = command_parser.add_parser(
        "upload", help="Upload a hosted file to another node on the network."
    )
    parser.add_argument("data_id", help="Data ID of hosted file to upload.")
    parser.add_argument("file_size", help="File size in bytes of hosted file to upload.")
    parser.add_argument("node_unl", help="UNL of the node to direct connect to for the transfer.")

def _add_download(command_parser):
    parser = command_parser.add_parser(
        "download", help="Download a hosted file from another node on the network."
    )
    parser.add_argument("data_id", help="Data ID of the hosted file to download.")
    parser.add_argument("file_size", help="File size in bytes of hosted file to download.")
    parser.add_argument("node_unl", help="UNL of the node to direct connect to for the transfer.")


def _add_showid(command_parser):
    command_parser.add_parser(
        "showid", help="Show node id."
    )

def _add_showunl(command_parser):
    command_parser.add_parser(
        "showunl", help="Generate a Universal Node Locator."
    )


def _add_showtype(command_parser):
    msg = "Show if public node with internet visible IP or private node."
    command_parser.add_parser("showtype", help=msg)


def _parse_args(args):
    class ArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)

    # setup parser
    description = "Low level reference node command-line interface."
    parser = ArgumentParser(description=description)
    _add_programm_args(parser)
    command_parser = parser.add_subparsers(
        title='commands', dest='command', metavar="<command>"
    )

    _add_version(command_parser)
    _add_put(command_parser)
    _add_get(command_parser)
    _add_run(command_parser)
    _add_showid(command_parser)
    _add_showtype(command_parser)
    _add_direct_message(command_parser)
    _add_relay_message(command_parser)
    _add_showunl(command_parser)
    _add_host_file(command_parser)
    _add_upload(command_parser)
    _add_download(command_parser)

    # get values
    arguments = vars(parser.parse_args(args=args))
    command = arguments.pop("command")
    if not command:
        parser.error("No command given!")
    return command, arguments


def run(node, client, args):
    args["id"] = binascii.hexlify(node.get_id())
    args["dht_port"] = node.port
    print("Running node on port {dht_port} with id {id}".format(**args))
    print("Direct connect UNL = " + client.net.unl.value)
    while True:
        time.sleep(0.5)
        for received in node.get_messages():
            message = received["message"]
            if received["source"] is not None:
                peerid = binascii.hexlify(received["source"].id)
                msg = "Received direct message from {0}: {1}"
                print(msg.format(peerid, message))
            else:
                print("Received relayed message: {0}".format(message))

        process_transfers(client)

def direct_message(node, args):
    peerid = binascii.unhexlify(args["id"])
    result = node.send_direct_message(peerid, args["message"])
    print("RESULT:", result)
    print("Unsuccessfully sent!" if result is None else "Successfully sent!")


def relay_message(node, args):
    peerid = binascii.unhexlify(args["id"])
    node.send_relay_message(peerid, args["message"])
    print("Queued relay message.")


def _get_bootstrap_nodes(args):
    # FIXME doesn't work with ipv6 addresses
    if args["bootstrap"] is not None:
        bootstrap = args["bootstrap"].split(":")
        return [(bootstrap[0], int(bootstrap[1]))]
    return None


def _get_node_key(args):
    if args["node_key"] is not None:
        return args["node_key"]
    return btctxstore.BtcTxStore().create_wallet()


def main(args):
    command, args = _parse_args(args)

    # show version
    if command == "version":
        print("v{0}".format(storjnode.__version__))
        return

    # setup node
    node_key = _get_node_key(args)
    dht_port = args["dht_port"]
    bootstrap_nodes = _get_bootstrap_nodes(args)
    node = storjnode.network.BlockingNode(node_key, port=dht_port,
                                          bootstrap_nodes=bootstrap_nodes)

    #Setup direct connect.
    wallet = btctxstore.BtcTxStore(testnet=True, dryrun=True)
    if args["passive_port"] == None:
        passive_port = random.randport(4000, 68000)
    else:
        passive_port = args["passive_port"]
    direct_net = Net(
        net_type="direct",
        dht_node=DHT(),
        debug=1,
        passive_port=passive_port
    )

    #File transfer client.
    client = FileTransfer(
        net=direct_net,
        wallet=wallet,
        storage_path=args["storage_path"]
    )

    print("Giving node 12sec to find peers ...")
    time.sleep(12)

    if command == "run":
        run(node, client, args)

    elif command == "put":
        node[args["key"]] = args["value"]
        print("Put '{key}' => '{value}'!".format(**args))

    elif command == "get":
        value = node[args["key"]]
        print("Got '{key}' => '{value}'!".format(key=args["key"], value=value))

    elif command == "direct_message":
        direct_message(node, args)

    elif command == "relay_message":
        relay_message(node, args)
        time.sleep(5)  # give time for queue to be processed

    elif command == "showid":
        print("Node id: {0}".format(binascii.hexlify(node.get_id())))

    elif command == "showtype":
        print("Public node!" if node.has_public_ip() else "Private node!")


    # TCP networking / file transfer commands.
    if command == "host_file":
        print(client.move_file_to_storage(args["path"]))

    if command == "showunl":
        print("UNL = " + direct_net.unl.value)

    elif command == "upload":
        client.data_request(
            "upload",
            args["data_id"],
            int(args["file_size"]),
            args["node_unl"]
        )

        while 1:
            time.sleep(0.5)
            process_transfers(client)

    elif command == "download":
        print(args["data_id"])
        print(args["file_size"])
        print(args["node_unl"])

        client.data_request(
            "download",
            args["data_id"],
            int(args["file_size"]),
            args["node_unl"]
        )

        while 1:
            time.sleep(0.5)
            process_transfers(client)

    print("Stopping node")
    client.net.stop()
    node.stop()
