import time
import copy
import storjnode
from threading import Thread, RLock
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


class _Monitor(object):  # will not scale but good for now

    def __init__(self, node, timeout=600):
        """Network monitor to crawl the network and gather information.

        Args:
            node: Node used to crawl the network.
        """

        # pipeline: scanning -> scanned
        self.scanning = {}  # {id: data}
        self.scanned = {}  # {id: data}

        self.mutex = RLock()
        self.node = node
        self.server = self.node.server
        self.timeout = time.time() + timeout

        # add handlers
        self.node.add_message_handler(self._handle_info_message)
        self.node.add_message_handler(self._handle_peers_message)

        # start crawl at self
        self.scanning[self.node.get_id()] = copy.deepcopy(DEFAULT_DATA)

    def _handle_peers_message(self, node, source_id, message):
        received = time.time()
        message = read_peers(node.server.btctxstore, message)
        if message is None:
            return  # dont care about this message
        with self.mutex:
            data = self.scanning.get(message.sender)
            if data is None:
                return  # not being scanned
            _log.debug("Received peers from {0}!".format(
                storjnode.util.node_id_to_address(message.sender))
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
            _log.debug("Received info from {0}!".format(
                storjnode.util.node_id_to_address(message.sender))
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
        _log.debug(txt.format(
            storjnode.util.node_id_to_address(nodeid),
            len(self.scanned), len(self.scanning)
        ))

    def process(self, nodeid, data):

        # request with exponential backoff
        now = time.time()
        window = storjnode.network.WALK_TIMEOUT ** data["request"]["tries"]
        if time.time() < data["request"]["last"] + window:
            return  # wait for response

        _log.debug("Requesting info/peers for {0}, try {1}!".format(
            storjnode.util.node_id_to_address(nodeid),
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

    def worker(self):
        while time.time() < self.timeout:
            time.sleep(0.002)

            # get next node to scan
            with self.mutex:

                if len(self.scanning) == 0:
                    return  # done! Nothing to scan and nothing being scanned

                for nodeid, data in self.scanning.copy().items():
                    self.process(nodeid, data)
                    time.sleep(0.1)  # not to fast

        # done! because of timeout

    def crawl(self):
        """Start workers and block until network is crawled."""
        worker = Thread(target=self.worker)
        worker.start()
        worker.join()

        # remove handlers
        self.node.remove_message_handler(self._handle_info_message)
        self.node.remove_message_handler(self._handle_peers_message)

        return (self.scanned, self.scanning)


def run(storjnode, timeout=600):
    return _Monitor(storjnode, timeout=timeout).crawl()
