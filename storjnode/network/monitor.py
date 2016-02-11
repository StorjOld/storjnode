import time
import random
import os
import bisect
import json
import copy
import storjnode
from collections import OrderedDict
from storjkademlia.node import Node as KadNode
from io import BytesIO
from threading import Thread, RLock
from storjnode.common import THREAD_SLEEP
from storjnode.util import node_id_to_address
from storjnode.network.messages.peers import read as read_peers
from storjnode.network.messages.peers import request as request_peers
from storjnode.network.messages.info import read as read_info
from storjnode.network.messages.info import request as request_info
from crochet import TimeoutError


_log = storjnode.log.getLogger(__name__)


SKIP_BANDWIDTH_TEST = False
if os.environ.get("STORJNODE_MONITOR_MAX_TRIES"):
    MAX_TRIES = int(os.environ.get("STORJNODE_MONITOR_MAX_TRIES"))
else:
    MAX_TRIES = 0


DEFAULT_DATA = OrderedDict([
    ("peers", None),                # [nodeid, ...]
    ("storage", None),              # {"total": int, "used": int, "free": int}
    ("network", OrderedDict()),     # {
                                    #     "transport": [ip, port],
                                    #     "unl": str "is_public": bool
                                    # }
    ("version", None),              # {"protocol: str, "storjnode": str}
    ("platform", None),             # {
                                    #   "system": str, "release": str,
                                    #   "version": str, "machine": str
                                    # }
    ("btcaddress", None),
    ("bandwidth", None),            # {"send": int, "receive": int}
    ("latency", OrderedDict([
        ("info", None),
        ("peers", None),
        ("direct", None),
        # TODO add transfer latency
    ])),
    ("request", OrderedDict([("tries", 0), ("last", 0)])),
])


class Crawler(object):  # will not scale but good for now

    def __init__(self, node, limit=5, timeout=600):

        # CRAWLER PIPELINE
        self.pipeline_mutex = RLock()

        # sent info and peer requests but not yet received a response
        self.pipeline_scanning = {}  # {node_id: data}
        # |
        # | received info and peer responses and ready for bandwidth test
        # V user ordered dict to have a fifo for bandwidth test
        self.pipeline_scanned_fifo = OrderedDict()  # {node_id: data}
        # |
        # V only test bandwidth of one node at a time to ensure best results
        self.pipeline_bandwidth_test = None  # (node_id, data)
        # |
        # V peers processed and ready to save
        self.pipeline_processed = {}  # {node_id: data}

        self.stop_thread = False
        self.node = node
        self.server = self.node.server
        self.timeout = time.time() + timeout
        self.limit = limit

    def stop(self):
        self.stop_thread = True

    def _add_peer_to_pipeline(self, peerid, ip, port):
        with self.pipeline_mutex:
            scanning = peerid in self.pipeline_scanning
            scanned = peerid in self.pipeline_scanned_fifo
            processed = peerid in self.pipeline_processed
            testing_bandwidth = (
                self.pipeline_bandwidth_test is not None and
                peerid == self.pipeline_bandwidth_test[0]
            )
            if not (scanning or scanned or processed or testing_bandwidth):
                self.pipeline_scanning[peerid] = copy.deepcopy(DEFAULT_DATA)

            if scanning and ip is not None and port is not None:
                data = self.pipeline_scanning[peerid]
                if "transport" not in data["network"]:
                    data["network"]["transport"] = [ip, port]

    def _handle_peers_message(self, node, message):
        received = time.time()
        message = read_peers(node.server.btctxstore, message)
        if message is None:
            return  # dont care about this message
        with self.pipeline_mutex:
            data = self.pipeline_scanning.get(message.sender)
            if data is None:  # not being scanned anymore
                return
            _log.info("Received peers from {0}!".format(
                node_id_to_address(message.sender))
            )
            if data["peers"] is None:
                data["latency"]["peers"] = received - data["latency"]["peers"]
                data["peers"] = storjnode.util.chunks(message.body, 20)

            # add to pipeline if needed
            for peer in data["peers"]:
                self._add_peer_to_pipeline(peer, None, None)

            self._check_scan_complete(message.sender, data)

    def _handle_info_message(self, node, message):
        received = time.time()
        message = read_info(node.server.btctxstore, message)
        if message is None:
            return  # dont care about this message
        with self.pipeline_mutex:
            data = self.pipeline_scanning.get(message.sender)
            if data is None:
                return  # not being scanned
            _log.info("Received info from {0}!".format(
                node_id_to_address(message.sender))
            )
            data["latency"]["info"] = received - data["latency"]["info"]
            data["version"] = OrderedDict([
                ("protocol", message.version),
                ("storjnode", message.body.version),
            ])
            data["storage"] = message.body.storage._asdict()

            # save network info we dont already have
            network = message.body.network._asdict()
            if "transport" not in data["network"]:
                data["network"]["transport"] = network["transport"]
            if "unl" not in data["network"]:
                data["network"]["unl"] = network["unl"]
            if "is_public" not in data["network"]:
                data["network"]["is_public"] = network["is_public"]

            data["platform"] = message.body.platform._asdict()
            data["btcaddress"] = storjnode.util.node_id_to_address(
                message.body.btcaddress
            )
            self._check_scan_complete(message.sender, data)

    def _check_scan_complete(self, nodeid, data):
        # expect caller to have pipeline mutex

        if data["peers"] is None:
            return  # peers not yet received
        if data["version"] is None:
            return  # info not yet received

        # move to scanned
        _log.info("Moving {0} to scanned".format(
            storjnode.util.node_id_to_address(nodeid))
        )
        del self.pipeline_scanning[nodeid]
        self.pipeline_scanned_fifo[nodeid] = data

        txt = ("Scan complete for {0}, "
               "scanned:{1}, scanning:{2}, processed:{3}!")
        _log.info(txt.format(
            node_id_to_address(nodeid),
            len(self.pipeline_scanned_fifo),
            len(self.pipeline_scanning),
            len(self.pipeline_processed),
        ))

    def _handle_neighbours_message(self, knode, neighbours):
        received = time.time()
        with self.pipeline_mutex:
            data = self.pipeline_scanning.get(knode.id)
            if data is None:  # not being scanned anymore
                return
            _log.info("Received neighbours from {0}!".format(
                node_id_to_address(knode.id))
            )
            # add peers
            if data["peers"] is None:
                data["latency"]["peers"] = received - data["latency"]["peers"]
                data["peers"] = [nodeid for nodeid, ip, port in neighbours]

            # add to pipeline if needed
            for nodeid, ip, port in neighbours:
                self._add_peer_to_pipeline(nodeid, ip, port)

            self._check_scan_complete(knode.id, data)

    def _request_peers(self, nodeid, data):
        with self.pipeline_mutex:

            # get neighbours (old nodes don't respond to peers request)
            if "transport" in data["network"]:
                ip, port = data["network"]["transport"]
                knode = KadNode(nodeid, ip, port)
                defered = self.node.server.protocol.callFindNode(knode, knode)
                defered = storjnode.util.default_defered(defered, [])

                def _on_get_neighbours(neighbours):
                    self._handle_neighbours_message(knode, neighbours)
                defered.addCallback(_on_get_neighbours)

            # send request peers message (for new nodes behind nat)
            request_peers(self.node, nodeid)

    def _process_scanning(self, nodeid, data):
        with self.pipeline_mutex:

            # request with exponential backoff
            now = time.time()
            window = storjnode.network.WALK_TIMEOUT ** data["request"]["tries"]
            if time.time() < data["request"]["last"] + window:
                return  # wait for response

            _log.info("Requesting info/peers for {0}, try {1}!".format(
                node_id_to_address(nodeid),
                data["request"]["tries"]
            ))

            # request peers
            if data["peers"] is None:
                _log.info("Requesting peers/neighbours from {0}!".format(
                    node_id_to_address(nodeid))
                )
                self._request_peers(nodeid, data)
                if data["latency"]["peers"] is None:
                    data["latency"]["peers"] = now

            # request info
            if data["version"] is None:
                _log.info("Requesting info from {0}!".format(
                    node_id_to_address(nodeid))
                )
                request_info(self.node, nodeid)
                if data["latency"]["info"] is None:
                    data["latency"]["info"] = now

            data["request"]["last"] = now
            data["request"]["tries"] = data["request"]["tries"] + 1

    def _handle_bandwidth_test_error(self, err):
        with self.pipeline_mutex:
            _log.error("Bandwidth test failed: {0}".format(repr(err)))

            # move to the back to scanned fifo and try again later
            nodeid, data = self.pipeline_bandwidth_test
            self.pipeline_scanned_fifo[nodeid] = data

            # free up bandwidth test for next peer
            self.pipeline_bandwidth_test = None

        # Return exception so the success handler doesn't fire.
        return err

    def _handle_bandwidth_test_success(self, results):
        with self.pipeline_mutex:
            _log.info("Bandwidth test successfull: {0}".format(repr(results)))
            nodeid, data = self.pipeline_bandwidth_test

            # free up bandwidth test for next peer
            self.pipeline_bandwidth_test = None

            # save test results
            if results is not None:
                data["bandwidth"] = {
                    "send": results["upload"],
                    "receive": results["download"],
                }
                data["latency"]["direct"] = results["latency"]

                # move peer to processed
                self.pipeline_processed[nodeid] = data
                txt = "Processed:{0}, scanned:{1},"
                txt += "scanning:{2}, processed:{3}!"
                _log.info(txt.format(
                    node_id_to_address(nodeid),
                    len(self.pipeline_scanned_fifo),
                    len(self.pipeline_scanning),
                    len(self.pipeline_processed),
                ))
            else:
                # move to the back to scanned fifo and try again later
                self.pipeline_scanned_fifo[nodeid] = data

                _log.error("No test results for success callback")
                raise Exception("Bandwidth test none results")

    def _process_bandwidth_test(self):
        # expects caller to have pipeline mutex
        not_testing_bandwidth = self.pipeline_bandwidth_test is None
        if not_testing_bandwidth and len(self.pipeline_scanned_fifo) > 0:

            # pop first entry
            nodeid = self.pipeline_scanned_fifo.keys()[0]
            data = self.pipeline_scanned_fifo[nodeid]
            del self.pipeline_scanned_fifo[nodeid]
            assert(nodeid != self.node.get_id())

            # skip bandwidth test
            skip_bandwidth_test = SKIP_BANDWIDTH_TEST
            if self.node.sim_dht is not None:
                if not self.node.sim_dht.has_mutex:
                    skip_bandwidth_test = True
                else:
                    if not self.node.sim_dht.can_test_knode(nodeid):
                        skip_bandwidth_test = True
            if skip_bandwidth_test:
                _log.info("Skipping bandwidth test")
                self.pipeline_processed[nodeid] = data
                return

            _log.info("Starting bandwidth test for: {0}".format(
                node_id_to_address(nodeid))
            )

            # start bandwidth test (timeout after 5min)
            time.sleep(random.randint(0, 10))
            self.pipeline_bandwidth_test = (nodeid, data)
            on_success = self._handle_bandwidth_test_success
            on_error = self._handle_bandwidth_test_error
            deferred = self.node.test_bandwidth(nodeid)
            deferred.addCallback(on_success)
            deferred.addErrback(on_error)

    def _scanning_complete(self):
        with self.pipeline_mutex:
            scanning = self.pipeline_scanning.copy()
            if MAX_TRIES > 0:
                for nodeid, data in scanning.copy().items():
                    if data["request"]["tries"] >= MAX_TRIES:
                        del scanning[nodeid]

            return len(scanning) == 0

    def _process_pipeline(self):
        while not self.stop_thread and time.time() < self.timeout:
            time.sleep(THREAD_SLEEP)

            with self.pipeline_mutex:

                # exit condition pipeline empty
                if (self._scanning_complete() and
                        len(self.pipeline_scanned_fifo) == 0 and
                        self.pipeline_bandwidth_test is None):
                    return

                # exit condition enough peers processed
                if (0 < self.limit <= len(self.pipeline_processed)):
                    return

                # send info and peer requests to found peers
                for nodeid, data in self.pipeline_scanning.copy().items():
                    self._process_scanning(nodeid, data)

                self._process_bandwidth_test()

        # done! because of timeout or stop flag

    def _log_crawl_statistics(self):
        _log.info("MONITOR POST CRAWL STATISTICS: {0}".format(json.dumps({
            "scanning_info_and_peers": len(self.pipeline_scanning),
            "waiting_for_bandwidth_test": len(self.pipeline_scanned_fifo),
            "testing_bandwidth": self.pipeline_bandwidth_test is not None,
            "successfully_processed": len(self.pipeline_processed)
        }, indent=2)))

    def crawl(self):
        # add info and peers message handlers
        self.node.add_message_handler(self._handle_info_message)
        self.node.add_message_handler(self._handle_peers_message)

        # skip self
        self.pipeline_processed[self.node.get_id()] = None

        # add initial peers
        peers = self.node.get_neighbours()
        x = []
        y = []
        for peer in peers:
            if peer.can_test:
                x.append(peer)
            else:
                y.append(peer)

        for peer in x + y:
            if peer.id == self.node.get_id():
                continue

            self._add_peer_to_pipeline(peer.id, peer.ip, peer.port)

        # process pipeline until done
        self._process_pipeline()

        # remove info and peers message handlers
        self.node.remove_message_handler(self._handle_info_message)
        self.node.remove_message_handler(self._handle_peers_message)

        # remove self from results
        del self.pipeline_processed[self.node.get_id()]

        self._log_crawl_statistics()

        return self.pipeline_processed


def crawl(node, limit=20, timeout=600):
    """Crawl the net and gather info of the nearest peers.

    The crawler will scan nodes from nearest to farthest.

    Args:
        node: Node used to crawl the network.
        limit: Number of results after which to stop, 0 to crawl entire net.
        timeout: Time in seconds after which to stop.
    """
    return Crawler(node, limit=limit, timeout=timeout).crawl()


def predictable_key(node, num):
    return "monitor_dataset_{0}_{1}".format(node.get_address(), str(num))


def find_next_free_dataset_num(node):

    def _get_value(key):
        while True:
            try:
                return node[key]
            except TimeoutError:
                txt = "TimeoutError when getting key: {0}"
                _log.warning(txt.format(key))

    # probe for free slots with exponentially increasing steps
    lower_bound, upper_bound, exponant = 0, 0, 0
    while _get_value(predictable_key(node, upper_bound)) is not None:
        lower_bound = upper_bound
        upper_bound = 2 ** exponant
        exponant += 1

    # wrapper to find used slots
    class CompareObject(object):
        def __gt__(bisect_self, index):
            key = predictable_key(node, index)
            return _get_value(key) is not None

    # A list where the value is the index + lower_bound: [3, 4, 5, 6 ...]
    class ListObject(object):
        def __getitem__(self, index):
            return index + lower_bound

        def __len__(self):
            return upper_bound + 1 - lower_bound

    # binary search to find fist free slot btween lower and upper bound
    return bisect.bisect_left(ListObject(), CompareObject()) + lower_bound


def create_shard(node, num, begin, end, processed):

    # encode processed data
    encoded_processed = {}
    if processed:
        for nodeid, data in processed.items():
            node_address = node_id_to_address(nodeid)
            data["peers"] = [node_id_to_address(p) for p in data["peers"]]
            del data["request"]
            encoded_processed[node_address] = data

    # sign data
    node_address = node.get_address()
    data = json.dumps(OrderedDict([
        ("num", num),
        ("begin", begin),
        ("end", end),
        ("processed", encoded_processed),
    ]), indent=2)
    key = node.get_key()
    signature = node.server.btctxstore.sign_unicode(key, data)

    # write info to shard
    shard = BytesIO()
    shard.write(json.dumps(OrderedDict([
        ("address", node_address),
        ("data", data),
        ("signature", signature),
    ]), indent=2))
    return shard


class Monitor(object):

    def __init__(self, node, limit=20,
                 interval=3600, on_crawl_complete=None):
        self.on_crawl_complete = on_crawl_complete
        self.node = node
        self.limit = limit + 1  # + 1 because of initial node
        self.interval = interval
        self.mutex = RLock()
        self.crawler = None
        self.last_crawl = 0
        self.stop_thread = False
        self.dataset_num = find_next_free_dataset_num(self.node)
        self.thread = Thread(target=self.monitor)
        self.thread.start()

    def stop(self):
        _log.info("Stopping monitor!")
        with self.mutex:
            if self.crawler is not None:
                self.crawler.stop()
        self.stop_thread = True
        self.thread.join()

    def monitor(self):
        _log.debug("started monitor thread")
        while not self.stop_thread:
            time.sleep(THREAD_SLEEP)

            # When the interval has elapsed -- stop processing.
            if not ((self.last_crawl + self.interval) < time.time()):
                continue

            # crawl network
            _log.info("Crawling dataset {0}".format(self.dataset_num))
            begin = time.time()
            with self.mutex:
                self.crawler = Crawler(
                    self.node, limit=self.limit, timeout=self.interval,
                )
            processed = self.crawler.crawl()

            end = time.time()

            # create shard
            shard = create_shard(self.node, self.dataset_num,
                                 begin, end, processed)

            # save results to store
            shardid = storjnode.storage.shard.get_id(shard)
            storjnode.storage.manager.add(self.node.config["storage"], shard)
            _log.info("Saved dataset {0} as shard {1}".format(
                self.dataset_num, shardid
            ))

            # add store predictable id to dht
            key = predictable_key(self.node, self.dataset_num)
            while True:
                try:
                    self.node[key] = shardid
                    break
                except TimeoutError:
                    txt = "TimeoutError when saving key: {0}"
                    _log.warning(txt.format(key))
            _log.info("Added DHT entry {0} => {1}".format(key, shardid))

            # call handler if given
            if self.on_crawl_complete is not None:
                self.on_crawl_complete(key, shard)

            # update dataset num and last crawl time
            self.dataset_num = self.dataset_num + 1
            self.last_crawl = time.time()
