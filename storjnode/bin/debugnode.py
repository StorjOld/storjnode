import sys
import time
import argparse
import storjnode


def _add_programm_args(parser):

    # ip
    default = "127.0.0.1"
    parser.add_argument(
        "--ip", default=default,
        help="Node ip address. Default: {0}.".format(default)
    )

    # port
    default = 4653
    parser.add_argument(
        "--port", default=default, type=int,
        help="Node port. Default: {0}.".format(default)
    )

    # bootstrap ip
    default = "1.2.3.4"
    parser.add_argument(
        "--bootstrap_ip", default=default,
        help="Bootstrap node ip address. Default: {0}.".format(default)
    )

    # bootstrap port
    default = 4653
    parser.add_argument(
        "--bootstrap_port", default=default, type=int,
        help="Bootstrap node port. Default: {0}.".format(default)
    )


def _add_put(command_parser):
    parser = command_parser.add_parser(
        "put", help="Put value into DHT."
    )
    parser.add_argument("key", help="Key to retrieve value by.")
    parser.add_argument("value", help="Value to insert into the DHT")


def _add_get(command_parser):
    parser = command_parser.add_parser(
        "get", help="Get value from DHT."
    )
    parser.add_argument("key", help="Key to retrieve value by.")


def _add_run(command_parser):
    parser = command_parser.add_parser(
        "run", help="Run node and extend DHT network."
    )


def _parse_args():
    class ArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)
    # TODO let user put in store path and max size shard size is 128

    # setup parser
    description = "Debug node command-line interface."
    parser = ArgumentParser(description=description)
    _add_programm_args(parser)
    command_parser = parser.add_subparsers(
        title='commands', dest='command', metavar="<command>"
    )
    _add_put(command_parser)
    _add_get(command_parser)
    _add_run(command_parser)

    # get values
    args = vars(parser.parse_args())
    command = args.pop("command")
    if not command:
        parser.error("No command given!")
    return command, args


def main():
    command, args = _parse_args()
    config = {
        "node_key": "not used yet ...",
        "node_address": (args["ip"], args["port"]),
        "bootstrap_nodes": [
            (args["bootstrap_ip"], args["bootstrap_port"])
        ]
    }
    print("CONFIG:", config)
    node = storjnode.network.kademlianode.KademliaNode(config)
    node.start()
    if command == "run":
        print("RUN")
        while True:
            time.sleep(1)
    elif command == "put":
        print("PUT")
        key = args["key"]
        value = args["value"]
        node[key] = value
        print("{0} => {1}".format(key, value))
    elif command == "get":
        print("GET")
        key = args["key"]
        value = node[key]
        # node.get(key, "defaultvalue")  # also works
        print("{0} => {1}".format(key, value))
    node.stop()


if __name__ == "__main__":
    main()
