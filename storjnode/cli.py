import time

# File transfer.
from .network.file_transfer import FileTransfer, process_transfers
from pyp2p.unl import UNL, is_valid_unl
from pyp2p.net import Net
from pyp2p.dht_msg import DHT

import binascii
import argparse
import storjnode
import btctxstore
import sys
import random
from crochet import setup, TimeoutError
setup()  # start twisted via crochet


def _add_programm_args(parser):

    # port
    default = None
    parser.add_argument("--dht_port", default=default, type=int,
                        help="Node DHT port, random user port by default.")

    parser.add_argument("--passive_port", default=default, type=int,
                        help=("Port to receive inbound TCP connections on"
                              " when nodes direct connect to us."))

    parser.add_argument("--passive_bind", default=default,
                        help=("LAN IP to receive inbound TCP connections on"
                              " when nodes direct connect to us."))

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
        "host_file", help=("Copy a local file to the storage folder and"
                           " return its data ID and file size.")
    )
    parser.add_argument(
        "path", help="Local path of file to host on the network."
    )


def _add_upload(command_parser):
    parser = command_parser.add_parser(
        "upload", help="Upload a hosted file to another node on the network."
    )
    parser.add_argument(
        "data_id", help="Data ID of hosted file to upload."
    )
    parser.add_argument(
        "file_size", help="File size in bytes of hosted file to upload."
    )
    parser.add_argument("node_unl", help=("UNL of the node to direct connect"
                                          " to for the transfer."))


def _add_download(command_parser):
    parser = command_parser.add_parser(
        "download",
        help="Download a hosted file from another node on the network."
    )
    parser.add_argument(
        "data_id", help="Data ID of the hosted file to download."
    )
    parser.add_argument(
        "file_size", help="File size in bytes of hosted file to download."
    )
    parser.add_argument(
        "node_unl",
        help="UNL of the node to direct connect to for the transfer."
    )


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


def command_run(node, client, args):
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


def command_put(node, args):
    try:
        node[args["key"]] = args["value"]
        print("Put '{key}' => '{value}'!".format(**args))
    except TimeoutError:
        print("Timeout error!")


def command_get(node, args):
    try:
        value = node[args["key"]]
        print("Got '{key}' => '{value}'!".format(key=args["key"],
                                                 value=value))
    except TimeoutError:
        print("Timeout error!")


def command_direct_message(node, args):
    try:
        peerid = binascii.unhexlify(args["id"])
        result = node.send_direct_message(peerid, args["message"])
        if result is None:
            print("Unsuccessfully sent!")
        else:
            print("Successfully sent!")
    except TimeoutError:
        print("Timeout error!")


def command_relay_message(node, args):
    peerid = binascii.unhexlify(args["id"])
    node.send_relay_message(peerid, args["message"])
    print("Queued relay message.")
    time.sleep(5)  # give time for queue to be processed


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


def command_showtype(node):
    try:
        print("Public node!" if node.dbg_has_public_ip() else "Private node!")
    except TimeoutError:
        print("Timeout error!")


def command_upload(client, args):
    client.data_request(
        "upload",
        args["data_id"],
        int(args["file_size"]),
        args["node_unl"]
    )

    while 1:
        time.sleep(0.5)
        process_transfers(client)


def command_download(client, args):
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


def setup_node(args):
    node_key = _get_node_key(args)
    dht_port = args["dht_port"]
    bootstrap_nodes = _get_bootstrap_nodes(args)
    return storjnode.network.BlockingNode(node_key, port=dht_port,
                                          bootstrap_nodes=bootstrap_nodes)


def setup_file_transfer_client(args):

    #Setup direct connect.
    wallet = btctxstore.BtcTxStore(testnet=True, dryrun=True)
    if args["passive_port"] is None:
        #passive_port = random.randport(4000, 68000)
        passive_port = random.choice(range(1024, 49151))  # randomish user port
    else:
        passive_port = args["passive_port"]

    if args["passive_bind"] is not None:
        passive_bind = args["passive_bind"]
    else:
        passive_bind = "0.0.0.0"

    direct_net = Net(
        net_type="direct",
        dht_node=DHT(),
        debug=1,
        passive_port=passive_port,
        passive_bind=passive_bind
    )

    #File transfer client.
    return FileTransfer(
        net=direct_net,
        wallet=wallet,
        storage_path=args["storage_path"]
    )


def main(args):
    command, args = _parse_args(args)

    # show version
    if command == "version":
        print("v{0}".format(storjnode.__version__))
        return

    node = setup_node(args)
    client = setup_file_transfer_client(args)

    print("Giving node 120sec to find peers ...")
    time.sleep(120)

    if command == "run":
        command_run(node, client, args)
    elif command == "put":
        command_put(node, args)
    elif command == "get":
        command_get(node, args)
    elif command == "direct_message":
        command_direct_message(node, args)
    elif command == "relay_message":
        command_relay_message(node, args)
    elif command == "showid":
        print("Node id: {0}".format(binascii.hexlify(node.get_id())))
    elif command == "showtype":
        command_showtype(node)

    # TCP networking / file transfer commands.
    elif command == "host_file":
        print(client.move_file_to_storage(args["path"]))
    elif command == "showunl":
        print("UNL = " + client.net.unl.value)
    elif command == "upload":
        command_upload(client, args)
    elif command == "download":
        command_download(client, args)

    print("Stopping node")
    client.net.stop()
    node.stop()
