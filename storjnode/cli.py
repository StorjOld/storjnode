import time
import binascii
import argparse
import storjnode
import btctxstore
import sys
import pprint
from storjnode.network import WALK_TIMEOUT
from storjnode.storage.manager import DEFAULT_STORE_PATH
from pyp2p.unl import UNL
from crochet import setup, TimeoutError
setup()  # start twisted via crochet


def _add_programm_args(parser):

    # port
    default = None
    parser.add_argument("--udp_port", default=default, type=int,
                        help="Node DHT port, random user port by default.")

    parser.add_argument("--passive_port", default=default, type=int,
                        help=("Port to receive inbound TCP connections on"
                              " when nodes direct connect."))

    parser.add_argument("--passive_bind", default=default,
                        help=("LAN IP to receive inbound TCP connections on"
                              " when nodes direct connect."))

    parser.add_argument("--node_type", default=default,
                        help=("Direct conncet node details. Passive = port is forwarded, simultaneous = predictable type NAT, active = everything else."))

    parser.add_argument("--nat_type", default=default,
                        help=("Defines the node's NAT type. reuse, preserving, random, or delta"))

    default = DEFAULT_STORE_PATH
    msg = "Where to store files hosted, default: {0}."
    parser.add_argument("--storage_path", default=default,
                        help=msg.format(default))

    default = None
    msg = "Optional skip DHT bootstrap."
    parser.add_argument("--bootstrap", default=default,
                        help=msg.format(default))

    # bootstrap
    parser.add_argument('--skip_dht_bootstrap', action='store_true',
                        help="Skip DHT bootstrapping for faster testing.")

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


def _add_deconstruct_unl(command_parser):
    parser = command_parser.add_parser(
        "deconstruct_unl", help="Deconstructs a Universal Node Locator."
    )

    parser.add_argument("unl", help="Base64 encoded UNL to deconstruct.")


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
    _add_deconstruct_unl(command_parser)
    _add_host_file(command_parser)
    _add_upload(command_parser)
    _add_download(command_parser)

    # get values
    arguments = vars(parser.parse_args(args=args))
    command = arguments.pop("command")
    if not command:
        parser.error("No command given!")
    return command, arguments


def on_message(source, message):
    if source is not None:
        peerid = binascii.hexlify(source)
        msg = "Received direct message from {0}: {1}"
        print(msg.format(peerid, message))
    else:
        print("Received relayed message: {0}".format(message))


def command_run(node, args):
    args["id"] = binascii.hexlify(node.get_id())
    args["udp_port"] = node.port
    print("Running node on port {udp_port} with id {id}".format(**args))
    print("Direct connect UNL = " + node.get_unl())
    node.add_message_handler(on_message)

    while 1:
        time.sleep(1)


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
        result = node.direct_message(peerid, args["message"])
        if result is None:
            print("Unsuccessfully sent!")
        else:
            print("Successfully sent!")
    except TimeoutError:
        print("Timeout error!")


def command_relay_message(node, args):
    peerid = binascii.unhexlify(args["id"])
    node.relay_message(peerid, args["message"])
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
        print("Public node!" if node.sync_has_public_ip() else "Private node!")
    except TimeoutError:
        print("Timeout error!")


def command_showid(node, args):
    print("Node id: {0}".format(binascii.hexlify(node.get_id())))


def command_host_file(node, args):
    print(node.move_file_to_storage(args["path"]))


def command_showunl(node, args):
    print("UNL = " + node.get_unl())


def command_upload(node, args):
    print(args["data_id"])
    print(args["node_unl"])

    print(node.sync_request_data_transfer(
        args["data_id"],
        args["node_unl"],
        "send"
    ))


def command_download(node, args):
    print(args["data_id"])
    print(args["node_unl"])

    print(node.sync_request_data_transfer(
        args["data_id"],
        args["node_unl"],
        "receive"
    ))


def setup_node(args):
    node_key = _get_node_key(args)
    udp_port = args["udp_port"]
    bootstrap_nodes = _get_bootstrap_nodes(args)
    if args["storage_path"] is not None:
        store_config = {
            args["storage_path"]: {"limit": 0, "use_folder_tree": False}
        }
    else:
        from storjnode.storage.manager import DEFAULT_PATHS
        store_config = DEFAULT_PATHS

    passive_port = args["passive_port"] or 50200
    passive_bind = args["passive_bind"] or "0.0.0.0"
    node_type = args["node_type"] or "unknown"
    nat_type = args["nat_type"] or "unknown"

    return storjnode.network.Node(
        node_key, port=udp_port, bootstrap_nodes=bootstrap_nodes,
        refresh_neighbours_interval=WALK_TIMEOUT,
        passive_port=passive_port,
        passive_bind=passive_bind,
        node_type=node_type,
        nat_type=nat_type,
        store_config=store_config
    )


def main(args):
    command, args = _parse_args(args)

    # show version
    if command == "version":
        print("v{0}".format(storjnode.__version__))
        return
    if command == "deconstruct_unl":
        pprint.PrettyPrinter(indent=4).pprint(
            UNL(value=args["unl"]).deconstruct()
        )
        return

    # setup
    node = setup_node(args)
    if args["skip_dht_bootstrap"] is None:
        print("Waiting %fsec to find peers ..." % WALK_TIMEOUT)
        time.sleep(WALK_TIMEOUT)

    # run command
    {
        "run": command_run,
        "put": command_put,
        "get": command_get,
        "direct_message": command_direct_message,
        "relay_message": command_relay_message,
        "showid": command_showid,
        "showtype": command_showtype,
        "host_file": command_host_file,
        "showunl": command_showunl,
        "upload": command_upload,
        "download": command_download,
    }[command](node, args)

    print("Stopping node")
    node.stop()
