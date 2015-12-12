import time
import json
import copy
import storjnode
from io import BytesIO
from threading import Thread, RLock
from storjnode.util import node_id_to_address
from storjnode.network.messages.peers import read as read_peers
from storjnode.network.messages.peers import request as request_peers
from storjnode.network.messages.info import read as read_info
from storjnode.network.messages.info import request as request_info


_log = storjnode.log.getLogger(__name__)


DEFAULT_DATA = {
    "peers": None,                       # [nodeid, ...]
    "storage": None,                     # [total, used, free]
    "network": None,                     # [[ip, port], is_public]
    "version": None,                     # [protocol, storjnode]
    "latency": {"info": None, "peers": None},
    "request": {"tries": 0, "last": 0},
}


class Crawler(object):  # will not scale but good for now

    def __init__(self, node, limit=20, timeout=600):
        # pipeline: scanning -> scanned
        self.scanning = {}  # {node_address: data}
        self.scanned = {}  # {node_address: data}

        self.stop_thread = False
        self.mutex = RLock()
        self.node = node
        self.server = self.node.server
        self.timeout = time.time() + timeout
        self.limit = limit

    def stop(self):
        self.stop_thread = True

    def _handle_peers_message(self, node, source_id, message):
        received = time.time()
        message = read_peers(node.server.btctxstore, message)
        if message is None:
            return  # dont care about this message
        with self.mutex:
            data = self.scanning.get(message.sender)
            if data is None:
                return  # not being scanned
            _log.info("Received peers from {0}!".format(
                node_id_to_address(message.sender))
            )
            data["latency"]["peers"] = received - data["latency"]["peers"]
            data["peers"] = storjnode.util.chunks(message.body, 20)
            for peer in data["peers"]:
                if (peer not in self.scanned and peer not in self.scanning):
                    self.scanning[peer] = copy.deepcopy(DEFAULT_DATA)
            self._check_scan_complete(message.sender, data)

    def _handle_info_message(self, node, source_id, message):
        received = time.time()
        message = read_info(node.server.btctxstore, message)
        if message is None:
            return  # dont care about this message
        with self.mutex:
            data = self.scanning.get(message.sender)
            if data is None:
                return  # not being scanned
            _log.info("Received info from {0}!".format(
                node_id_to_address(message.sender))
            )
            data["latency"]["info"] = received - data["latency"]["info"]
            data["storage"] = message.body.storage
            data["network"] = message.body.network
            data["version"] = (message.version, message.body.version)
            self._check_scan_complete(message.sender, data)

    def _check_scan_complete(self, nodeid, data):
        if data["peers"] is None:
            return  # peers not yet received
        if data["network"] is None:
            return  # info not yet received

        # move to scanned
        del self.scanning[nodeid]
        self.scanned[nodeid] = data

        txt = "Processed {0}, scanned {1}, scanning {2}!"
        _log.info(txt.format(
            node_id_to_address(nodeid),
            len(self.scanned), len(self.scanning)
        ))

    def _process(self, nodeid, data):

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
            request_peers(self.node, nodeid)
            if data["latency"]["peers"] is None:
                data["latency"]["peers"] = now

        # request info
        if data["network"] is None:
            request_info(self.node, nodeid)
            if data["latency"]["info"] is None:
                data["latency"]["info"] = now

        data["request"]["last"] = now
        data["request"]["tries"] = data["request"]["tries"] + 1

    def _process_scanning(self):
        while not self.stop_thread and time.time() < self.timeout:
            time.sleep(0.002)

            # get next node to scan
            with self.mutex:

                if len(self.scanning) == 0:
                    return  # done! Nothing to scan and nothing being scanned

                if self.limit > 0 and len(self.scanned) >= self.limit:
                    return  # done! limit set and reached

                for nodeid, data in self.scanning.copy().items():
                    self._process(nodeid, data)
                    time.sleep(0.1)  # not to fast

        # done! because of timeout or stop flag

    def crawl(self):

        # add info and peers message handlers
        self.node.add_message_handler(self._handle_info_message)
        self.node.add_message_handler(self._handle_peers_message)

        # start crawl at self
        self.scanning[self.node.get_id()] = copy.deepcopy(DEFAULT_DATA)

        # process scanning until done
        self._process_scanning()

        # remove info and peers message handlers
        self.node.remove_message_handler(self._handle_info_message)
        self.node.remove_message_handler(self._handle_peers_message)

        return self.scanned


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
    # FIXME probe with exponential increase then binary search lowest unused
    num = 0
    while node[predictable_key(node, num)] is not None:
        _log.info("Dataset {0} already exists!".format(num))
        num += 1
    return num


def create_shard(node, num, begin, end, scanned):

    # encode scanned data
    encoded_scanned = {}
    for nodeid, data in scanned:
        node_address = node_id_to_address(nodeid)
        data["peers"] = [node_id_to_address(p) for p in data["peers"]]
        encoded_scanned[node_address] = data

    # write info to shard
    shard = BytesIO()
    shard.write(json.dumps({
        "node": node.get_address(),
        "num": num,
        "begin": begin,
        "end": end,
        "scanned": encoded_scanned,
    }))
    return shard


class Monitor(object):

    def __init__(self, node, store_config, limit=20, interval=600):
        self.store_config = store_config
        self.node = node
        self.limit = limit
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
            time.sleep(0.002)

            if not ((self.last_crawl + self.interval) < time.time()):
                continue

            # crawl network
            _log.info("Crawling dataset {0}".format(self.dataset_num))
            begin = time.time()
            with self.mutex:
                self.crawler = Crawler(
                    self.node, limit=self.limit, timeout=self.interval
                )
            scanned = self.crawler.crawl()

            end = time.time()

            # create shard
            shard = create_shard(self.node, self.dataset_num,
                                 begin, end, scanned)

            # save results to store
            shardid = storjnode.storage.shard.get_id(shard)
            storjnode.storage.manager.add(self.store_config, shard)
            _log.info("Saved dataset {0} as shard {1}".format(
                self.dataset_num, shardid
            ))

            # add store predictable id to dht
            key = predictable_key(self.node, self.dataset_num)
            self.node[key] = shardid
            _log.info("Added DHT entry {0} => {1}".format(key, shardid))

            # update dataset num and last crawl time
            self.dataset_num = self.dataset_num + 1
            self.last_crawl = time.time()
