import time
import apigen
import btctxstore
import storjnode
import crochet
from threading import RLock
from storjnode.network import BandwidthLimit


_log = storjnode.log.getLogger(__name__)


class StorjNode(apigen.Definition):
    """Storj protocol reference implementation."""

    def __init__(self, wallet=None, quiet=False, debug=False, verbose=False,
                 config=storjnode.common.CONFIG_PATH):

        wallet = wallet or btctxstore.BtcTxStore().create_wallet()
        assert(btctxstore.validate.mainnet_wallet(wallet) or
               btctxstore.validate.mainnet_key(wallet))

        # setup config
        if isinstance(config, dict):
            storjnode.config.validate(config)
            self._cfg = config
        else:
            self._cfg = storjnode.config.get(path=config)
        port = self._cfg["network"]["port"]
        notransfer = self._cfg["network"]["disable_data_transfer"]

        # start node
        self._node = storjnode.network.Node(
            wallet, disable_data_transfer=notransfer,
            bandwidth=None if notransfer else BandwidthLimit(self._cfg),
            port=port if port != "random" else None,
            store_config=self._cfg["storage"]
        )
        self._setup_message_list()

        # shitty wait for network stabilization
        _log.info("Shitty wait for network stabilization.")
        time.sleep(storjnode.network.WALK_TIMEOUT)
        self._node.refresh_neighbours()
        time.sleep(storjnode.network.WALK_TIMEOUT)
        self._node.refresh_neighbours()
        time.sleep(storjnode.network.WALK_TIMEOUT)

    def _setup_message_list(self):
        self._events = []
        self._events_mutex = RLock()
        self._node.add_message_handler(self._on_message)

    def _enable_monitor_responses(self):
        storjnode.network.messages.info.enable(self._node, self._cfg)
        storjnode.network.messages.peers.enable(self._node)
        # FIXME self._node.bandwidth_test.enable()
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

        def reformat_kademlia_node(knode):
            return {
                "address": storjnode.util.node_id_to_address(knode.id),
                "ip": knode.ip, "port": knode.port
            }
        peers = list(map(reformat_kademlia_node, self._node.get_neighbours()))
        try:
            transport = self._node.sync_get_transport_info(add_unl=False)
        except crochet.TimeoutError:
            _log.warning("Timeout getting transport info.")
            transport = None
        return {
            "version": {
                "storjnode": storjnode.__version__,
                "protocol": storjnode.common.PROTOCOL_VERSION,
            },
            "network": {
                "address": self._node.get_address(),
                "transport": transport,
                "peers": peers,
            },
        }

    def _on_crawl_complete(self, key, shard):
        _log.info("Crawl complete, results saved at {0}".format(key))

    @apigen.command()
    def farm(self):
        """TODO doc string"""

        monitor = None
        monitor_cfg = self._cfg["network"]["monitor"]
        if monitor_cfg["enable_responses"]:
            self._enable_monitor_responses()
        try:
            if monitor_cfg["enable_crawler"]:
                monitor = storjnode.network.monitor.Monitor(
                    self._node,
                    self._cfg["storage"],
                    limit=monitor_cfg["crawler_limit"],
                    interval=monitor_cfg["crawler_interval"],
                    on_crawl_complete=self._on_crawl_complete
                )
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            if monitor is not None:
                monitor.stop()

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
        return storjnode.config.create()

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
        try:
            return self._node.put(key, value)
        except crochet.TimeoutError:
            _log.warning("Timeout putting key/value in DHT.")
            return False

    @apigen.command()
    def net_get(self, key):
        """Get value from the DHT for a given key."""
        try:
            return self._node.get(key)
        except crochet.TimeoutError:
            _log.warning("Timeout getting key/value in DHT.")
            return None

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
