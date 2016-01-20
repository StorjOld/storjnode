import traceback
import apigen
import btctxstore
import storjnode
import crochet
from threading import RLock


__version__ = storjnode.__version__  # for auto generated version command
_log = storjnode.log.getLogger(__name__)


_NO_WALLET_AND_COLD_STORAGE = """
Error: No wallet or cold storage address provided!

    You must provide either a wallet via the arguments
    or at least one cold storage address in the config!

    This is to prmessage loss of funds. Please back up your provided
    wallet and the cold storage keys to prmessage any loss of funds.
"""


def _reformat_kademlia_node(knode):
    return {
        "address": storjnode.util.node_id_to_address(knode.id),
        "ip": knode.ip, "port": knode.port
    }


class StorjNode(apigen.Definition):
    """Storj protocol reference implementation."""

    def __init__(self, wallet=None, quiet=False, debug=False, verbose=False,
                 config=storjnode.common.CONFIG_PATH):
        self._init_conifg(config)
        self._init_wallet(wallet)
        self._init_node()
        self._init_messages()

    def _init_wallet(self, wallet):

        # make sure a wallet or cold storage address was provided
        if wallet is None and len(self._cfg["cold_storage"]) == 0:
            print(_NO_WALLET_AND_COLD_STORAGE)
            exit(1)

        # create wallet if needed and validate
        self.wallet = wallet or btctxstore.BtcTxStore().create_wallet()
        assert(btctxstore.validate.mainnet_wallet(self.wallet) or
               btctxstore.validate.mainnet_key(self.wallet))

    def _init_conifg(self, config):
        if isinstance(config, dict):
            storjnode.config.validate(config)
            self._cfg = config
        else:
            self._cfg = storjnode.config.get(path=config)

    def _init_node(self):
        port = self._cfg["network"]["port"]
        notransfer = self._cfg["network"]["disable_data_transfer"]
        bootstrap_nodes = self._cfg["network"]["bootstrap_nodes"]
        self._node = None
        try:
            self._node = storjnode.network.Node(
                self.wallet, disable_data_transfer=notransfer,
                port=port if port != "random" else None,
                config=self._cfg, bootstrap_nodes=bootstrap_nodes,
            )
        except Exception as e:
            _log.error(repr(e))
            traceback.print_exc()
            if self._node is not None:
                self._node.stop()
                self._node = None
            raise

    def _init_messages(self):
        self._messages = []
        self._messages_mutex = RLock()
        self._node.add_message_handler(self._on_message)

    def _enable_monitor_responses(self):
        storjnode.network.messages.info.enable(self._node, self._cfg)
        storjnode.network.messages.peers.enable(self._node)
        if not self._cfg["network"]["disable_data_transfer"]:
            self._node.bandwidth_test.enable()
            storjnode.network.file_transfer.enable_unl_requests(self._node)

    def _on_message(self, node, message):
        with self._messages_mutex:
            self._messages.append(message)

    def on_shutdown(self):
        if self._node is not None:
            self._node.stop()

    def startserver(self, hostname="localhost", port=8080, daemon=False):
        # remove startserver call from api (use farm istead)
        raise NotImplementedError("Not implemented by design.")

    def _init_monitor(self):
        notransfer = self._cfg["network"]["disable_data_transfer"]

        # enable monitor responses
        enable_responses = self._cfg["network"]["monitor"]["enable_responses"]
        if enable_responses and not notransfer:
            _log.info("Enabling monitor responses.")
            self._enable_monitor_responses()

        # start monitor crawler
        enable_crawler = self._cfg["network"]["monitor"]["enable_crawler"]
        limit = self._cfg["network"]["monitor"]["crawler_limit"]
        interval = self._cfg["network"]["monitor"]["crawler_interval"]
        if enable_crawler and not notransfer:
            _log.info("Starting monitor crawler.")
            self.monitor = storjnode.network.monitor.Monitor(
                self._node, self._cfg, limit=limit, interval=interval,
                on_crawl_complete=self._on_crawl_complete
            )

        if not notransfer:
            self._node.add_transfer_request_handler(
                self._on_transfer_request
            )

            self._node.add_transfer_complete_handler(
                self._on_transfer_complete
            )

    def _on_transfer_request(self, nodeid, shardid, direction, file_size):

        # do not accept push requests
        if direction == "receive":
            txt = "Push request from node {nodeid} for shard {shardid}."
            _log.warning(txt.format(nodeid=nodeid, shardid=shardid,
                                    size=file_size))
            return False

        # do not accept pull request if data doesnt exist
        store_config = self._cfg["storage"]
        if storjnode.storage.manager.find(store_config, shardid) is None:
            txt = ("Pull request from node {nodeid} "
                   "for shard {shardid} not in store.")
            _log.warning(txt.format(nodeid=nodeid, shardid=shardid))
            return False

        # accept any pull request if the data exists
        else:
            txt = ("Accepting pull request from node {nodeid} "
                   "for shard {shardid}.")
            _log.info(txt.format(nodeid=nodeid, shardid=shardid))
            return True

    def _on_transfer_complete(self, nodeid, shardid, direction):
        if direction == "receive":
            txt = "Completed push of shard {shardid} from {nodeid}"
            _log.critical(txt.format(shardid=shardid, nodeid=nodeid))
            exit(1)
        elif direction == "send":
            txt = "Completed pull of shard {shardid} from {nodeid}"
            _log.info(txt.format(shardid=shardid, nodeid=nodeid))

    def _on_crawl_complete(self, key, shard):
        _log.info("Crawl complete, {shardid} publshed at {key}".format(
            key=key, shardid=storjnode.storage.shard.get_id(shard)
        ))

    #########
    # BASIC #
    #########

    @apigen.command()
    def info(self):
        """Get node information."""

        peers = list(map(_reformat_kademlia_node, self._node.get_neighbours()))
        try:
            transport = self._node.sync_get_transport_info(add_unl=False)
        except crochet.TimeoutError:
            _log.warning("Timeout getting transport info.")
            transport = None
        # TODO review structure as it will be hard to change going forward
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

    @apigen.command(rpc=False)
    def farm(self, hostname="localhost", port=8080):
        """Start the farmer and the json-rpc service."""
        self.monitor = None
        try:
            # start monitor handlers and crawler if needed
            self._init_monitor()

            # start rpc service
            super(StorjNode, self).startserver(hostname=hostname, port=port)

        except KeyboardInterrupt:
            pass
        finally:
            if self.monitor is not None:
                self.monitor.stop()

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

    #######
    # DHT #
    #######

    @apigen.command()
    def dht_put(self, key, value):
        """Insert a key/value pair into the DHT."""
        try:
            return self._node.put(key, value)
        except crochet.TimeoutError:
            _log.warning("Timeout putting key/value in DHT.")
            return False

    @apigen.command()
    def dht_get(self, key):
        """Get value from the DHT for a given key."""
        try:
            return self._node.get(key)
        except crochet.TimeoutError:
            _log.warning("Timeout getting key/value in DHT.")
            return None

    ############
    # MESSAGES #
    ############

    @apigen.command()
    def msg_send(self, node_address, msg_json):
        """Relay a message to a specific node."""
        raise NotImplementedError()

    @apigen.command()
    def msg_list(self, json_schema=None, flush=True):
        """Messages received for the given subscription schema."""
        raise NotImplementedError()

    @apigen.command()
    def msg_publish(self, msg_json):
        """Publish an message on the network."""
        raise NotImplementedError()

    @apigen.command()
    def msg_subscribe(self, json_schema):
        """Subscribe to matching messages on the network."""
        raise NotImplementedError()

    @apigen.command()
    def msg_unsubscribe(self, json_schema):
        """Unsubscribe to matching messages on the network."""
        raise NotImplementedError()

    #################
    # DATA TRANSFER #
    #################

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
