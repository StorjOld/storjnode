import time
import apigen
import btctxstore
import storjnode
from threading import RLock
from storjnode.network import BandwidthLimit


_log = storjnode.log.getLogger(__name__)


class StorjNode(apigen.Definition):
    """Storj protocol reference implementation."""

    def __init__(self, quiet=False, debug=False, verbose=False,
                 config=storjnode.config.DEFAULT_CONFIG_PATH):

        # load config
        self._btctxstore = btctxstore.BtcTxStore()
        self._cfg = storjnode.config.ConfigFile(
            path=config, btctxstore=self._btctxstore
        )

        # get config values
        hwif = self._cfg["wallet"]["hwif"]
        port = self._cfg["network"]["port"]
        notransfer = self._cfg["network"]["disable_data_transfer"]
        enable_monitor = self._cfg["network"]["enable_monitor_responses"]

        # start node
        self._node = storjnode.network.Node(
            hwif, disable_data_transfer=notransfer,
            bandwidth=BandwidthLimit(self._cfg) if not notransfer else None,
            port=port if port != "random" else None
        )
        self._setup_message_list()
        if enable_monitor:
            self._enable_monitor_responses()

        # wait to find peers
        sleep_time = storjnode.network.server.WALK_TIMEOUT
        _log.info("Waiting {0} seconds to find peers".format(sleep_time))
        time.sleep(sleep_time)

    def _setup_message_list(self):
        self._events = []
        self._events_mutex = RLock()
        self._node.add_message_handler(self._on_message)

    def _enable_monitor_responses(self):
        storjnode.network.messages.info.enable(self._node, self._cfg)
        storjnode.network.messages.peers.enable(self._node)
        self._node.bandwidth_test.enable()
        storjnode.network.file_transfer.enable_unl_requests(self._node)

    def _on_message(self, node, msg):
        with self._events_mutex:
            self._events.append(msg)

    def on_shutdown(self):
        self._node.stop()

    ##################
    # END USER CALLS #
    ##################

    @apigen.command()
    def info(self):
        """Get node information."""
        neighbours = self._node.get_neighbours()
        return {
            "version": {
                "storjnode": storjnode.__version__,
                "protocol": storjnode.common.PROTOCOL_VERSION,
            },
            "network": {
                "address": self._node.get_address(),
                "transport": self._node.sync_get_transport_info(add_unl=False),
                "neighbours": neighbours,
            },
        }

    @apigen.command()
    def farm(self):
        """TODO doc string"""
        while True:
            print("shitty farm")
            time.sleep(1)

    ##########
    # CONFIG #
    ##########

    @apigen.command()
    def cfg_current(self):
        """The current config."""
        return self._cfg

    @apigen.command()
    def cfg_default(self):
        """The default storj config."""
        return storjnode.config.create(self._btctxstore)

    @apigen.command()
    def cfg_schema(self):
        """The jsonschema for config validation."""
        return storjnode.config.SCHEMA

    ###############
    # NETWORK DHT #
    ###############

    @apigen.command()
    def net_put(self, key, value):
        """Insert a key/value pair into the DHT."""
        return self._node.put(key, value)

    @apigen.command()
    def net_get(self, key):
        """Get value from the DHT for a given key."""
        return self._node.get(key)

    ##################
    # NETWORK EVENTS #
    ##################

    @apigen.command()
    def net_send(self, node_address, event):
        """Relay an event to a node."""
        nodeid = storjnode.util.address_to_node_id(node_address)
        return self._node.relay_message(nodeid, event)

    @apigen.command()
    def net_events(self, flush=True):
        """Events received."""
        # TODO add mapping to subscription schemas
        with self._events_mutex:
            messages = self._events
            if flush:
                self._events = []
            return messages

    @apigen.command()
    def net_publish(self, event_json):
        """Publish an event on the network."""
        raise NotImplementedError()

    @apigen.command()
    def net_subscribe(self, json_schema):
        """Subscribe to matching events on the network."""
        raise NotImplementedError()

    ####################
    # NETWORK TRANSFER #
    ####################

    # TODO define api calls

    ############
    # Contract #
    ############

    # TODO define api calls

    #########
    # AUDIT #
    #########

    # TODO define api calls

    #########
    # NOTER #
    #########

    # TODO define api calls
