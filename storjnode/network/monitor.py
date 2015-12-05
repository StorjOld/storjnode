import time
import copy
import storjnode
import datetime
from datetime import timedelta
from threading import Thread, RLock
from storjnode.network.messages.peers import read as read_peers
from storjnode.network.messages.peers import request as request_peers
from storjnode.network.messages.info import read as read_info
from storjnode.network.messages.info import request as request_info


_now = datetime.datetime.now
_log = storjnode.log.getLogger(__name__)


DEFAULT_DATA = {
    "peers": None,            # [nodeid, ...]
    "storage": None,          # (total, used, free)
    "network": None,          # ((ip, port), is_public)
    "version": None,          # (protocol, storjnode)
    "latency": [None, None],  # (relay_info, relay_peers)
}


class _Monitor(object):  # will not scale but good for now

    def __init__(self, node, worker_num=4, timeout=600):
        """Network monitor to crawl the network and gather information.

        Args:
            node: Node used to crawl the network.
            worker_num: Number of workers used to crawl the network.
        """

        # pipeline: toscan -> scanning -> scanned
        self.toscan = {}  # {id: data}
        self.scanning = {}  # {id: data}
        self.scanned = {}  # {id: data}

        self.mutex = RLock()
        self.node = node
        self.server = self.node.server
        self.timeout = _now() + timedelta(seconds=timeout)
        self.worker_num = worker_num

        self.node.add_message_handler(self._handle_info_message)
        self.node.add_message_handler(self._handle_peers_message)

        # start crawl at self
        self.toscan[self.node.get_id()] = copy.deepcopy(DEFAULT_DATA)

    def _handle_peers_message(self, node, source_id, message):
        received = _now()
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
            data["latency"][1] = received - data["latency"][1]
            data["peers"] = storjnode.util.chunks(message.body, 20)
            for peer in data["peers"]:
                if (peer not in self.scanned and
                        peer not in self.scanning and
                        peer not in self.toscan):
                    self.toscan[peer] = copy.deepcopy(DEFAULT_DATA)
            self._check_scan_complete(message.sender, data)

    def _handle_info_message(self, node, source_id, message):
        received = _now()
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
            data["latency"][0] = received - data["latency"][0]
            data["storage"] = message.body.storage
            data["network"] = message.body.network
            data["version"] = (message.version, message.body.version)
            self._check_scan_complete(message.sender, data)

    def _check_scan_complete(self, nodeid, data):
        if data["peers"] is None:
            return  # peers not yet received
        if data["network"] is None:
            return  # info not yet received
        self._processed(nodeid, data)  # move to scanned

    def get_next_node(self):
        """Moves node from toscan to scanning.

        Returns moved node or None if toscan is empty.
        """
        with self.mutex:
            if len(self.toscan) > 0:
                nodeid, data = self.toscan.popitem()
                self.scanning[nodeid] = data
                return (nodeid, data)
            else:
                return None

    def _processed(self, nodeid, data):
        """Move node from scanning to scanned and add new nodes to pipeline."""
        _log.debug("Processed {0}!".format(
            storjnode.util.node_id_to_address(nodeid))
        )
        with self.mutex:
            del self.scanning[nodeid]
            self.scanned[nodeid] = data
            for peerid in data["peers"]:
                if peerid not in self.scanning and peerid not in self.scanned:
                    self.toscan[peerid] = copy.deepcopy(DEFAULT_DATA)

    def worker(self):
        while _now() < self.timeout:
            time.sleep(0.002)

            # get next node to scan
            with self.mutex:
                entry = self.get_next_node()
                if entry is None and len(self.scanning) == 0:
                    return  # done! Nothing to scan and nothing being scanned

                # none to scan but others still scanning, more may come
                if entry is None:
                    continue

                nodeid, data = entry
                _log.debug("Requesting info/peers for {0}!".format(
                    storjnode.util.node_id_to_address(nodeid))
                )
                request_peers(self.node, nodeid)
                request_info(self.node, nodeid)
                data["latency"] = [_now(), _now()]

    def crawl(self):
        """Start workers and block until network is crawled."""
        workers = [Thread(target=self.worker) for i in range(self.worker_num)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        return (self.scanned, self.scanning, self.toscan)


def run(storjnode, worker_num=4, timeout=600):
    return _Monitor(storjnode, worker_num=worker_num, timeout=timeout).crawl()
