import storjnode
import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
import storjnode
from collections import OrderedDict
from btctxstore import BtcTxStore
import six
import time
import hashlib
import sys
import json
from threading import Lock
from twisted.internet import defer
from storjnode.util import address_to_node_id, node_id_to_address
from storjnode.util import parse_node_id_from_unl, ordered_dict_to_list
from storjnode.network.message import verify_signature
from storjnode.network.message import sign
from storjnode.network.file_handshake import is_valid_syn

from storjnode.network.process_transfers import process_transfers

_log = storjnode.log.getLogger(__name__)


def process_unl_requests(node, src_id, msg):
    unl = node._data_transfer.net.unl.value
    try:
        msg = OrderedDict(msg)

        # Not a UNL request.
        if msg[u"type"] != u"unl_request":
            return

        # Check signature.
        their_node_id = address_to_node_id(msg[u"requester"])
        if not verify_signature(msg, node.get_key(), their_node_id):
            return

        # Response.
        response = sign(OrderedDict(
            {
                u"type": u"unl_response",
                u"requestee": node.get_address(),
                u"unl": unl
            }
        ), node.get_key())

        # Send response.
        node.relay_message(their_node_id, response.items())

    except (ValueError, KeyError) as e:
        global _log
        _log.debug(str(e))
        _log.debug("Protocol: invalid JSON")


class FileTransfer:

    def __init__(self, net, wif=None, store_config=None, handlers=None):
        # Accept direct connections.
        self.net = net

        # Returned by callbacks.
        self.success_value = ("127.0.0.1", 7777)

        # Used for signing messages.
        self.wallet = BtcTxStore(testnet=False, dryrun=True)
        self.wif = wif or self.wallet.create_key()

        # Where will the data be stored?
        self.store_config = store_config
        assert(len(list(store_config)))

        # Handlers for certain events.
        self.handlers = handlers
        if self.handlers is None:
            self.handlers = {}
        if "complete" not in self.handlers:
            self.handlers["complete"] = set()
        if "accept" not in self.handlers:
            self.handlers["accept"] = set()
        if "start" not in self.handlers:
            self.handlers["start"] = set()

        # Start networking.
        if not self.net.is_net_started:
            self.net.start()

        # Dict of data requests: [contract_id] > contract
        self.contracts = {}

        # List of Sock objects returned from UNL.connect.
        self.cons = []

        # Dict of defers for contracts: [contract_id] > defer
        self.defers = {}

        # Three-way handshake status for contracts: [contract_id] > state
        self.handshake = {}

        # All contracts associated with this connection.
        # [con] > [contract_id] > con_info
        self.con_info = {}

        # File transfer currently active on connection.
        # [con] > contract_id
        self.con_transfer = {}

        # List of active downloads.
        # (Never try to download multiple copies of the same thing at once.)
        self.downloading = {}

        # Lock threads.
        self.mutex = Lock()

    def add_handler(self, type, handler):
        # todo: change handler for when new data is transferred
        # might be helpful to have for updating UI progress
        if type in list(self.handlers):
            self.handlers[type].add(handler)

    def remove_handler(self, type, handler):
        if type in list(self.handlers):
            self.handlers[type].remove(handler)

    def get_their_unl(self, contract):
        if self.net.unl == pyp2p.unl.UNL(value=contract["dest_unl"]):
            their_unl = contract["src_unl"]
        else:
            their_unl = contract["dest_unl"]

        return their_unl

    def is_queued(self, con=None):
        if con is not None:
            if con not in self.con_info:
                return 0

        if con is None:
            con_list = list(self.con_info)
        else:
            con_list = [con]

        for con in con_list:
            for contract_id in list(self.con_info[con]):
                con_info = self.con_info[con][contract_id]
                if con_info["remaining"]:
                    return 1

        return 0

    def cleanup_transfers(self, con, contract_id):
        # Cleanup downloading.
        if contract_id in self.contracts:
            contract = self.contracts[contract_id]
            if contract["data_id"] in self.downloading:
                if self.get_direction(contract_id) == u"receive":
                    del self.downloading[contract["data_id"]]

        # Cleanup handshakes.
        if contract_id in self.handshake:
            del self.handshake[contract_id]

        # Cleanup defers.
        if contract_id in self.defers:
            del self.defers[contract_id]

        # Cleanup con transfers.
        if con in self.con_transfer:
            del self.con_transfer[con]

        # Cleanup con_info.
        if con in self.con_info:
            del self.con_info[con]

        # Cleanup contracts.
        if contract_id in self.contracts:
            del self.contracts[contract_id]

    def queue_next_transfer(self, con):
        _log.debug("Queing next transfer")
        for contract_id in list(self.con_info[con]):
            con_info = self.con_info[con][contract_id]
            if con_info["remaining"]:
                self.con_transfer[con] = contract_id
                con.send(contract_id, send_all=1)
                return

        # Mark end of transfers.
        self.con_transfer[con] = u"0" * 64

    def save_contract(self, contract):
        # Record contract details.
        contract_id = self.contract_id(contract)
        self.contracts[contract_id] = contract

        return contract_id

    def send_msg(self, msg, unl):
        assert(type(msg) == OrderedDict)
        node_id = self.net.unl.deconstruct(unl)["node_id"]
        msg = ordered_dict_to_list(msg)
        self.net.dht_node.relay_message(node_id, msg)

    def contract_id(self, contract):
        if sys.version_info >= (3, 0, 0):
            contract = str(contract).encode("ascii")
        else:
            contract = str(contract)

        return hashlib.sha256(contract).hexdigest()

    def sign_contract(self, contract):
        return storjnode.network.message.sign(contract, self.wif)

    def is_valid_contract_sig(self, contract, node_id=None):
        return storjnode.network.message.verify_signature(contract, self.wif,
                                                          node_id=node_id)

    def get_direction(self, contract_id, contract=None):
        """
        The direction of a transfer is relative to the node.
        """
        contract = contract or self.contracts[contract_id]
        our_unl = self.net.unl
        host_unl = pyp2p.unl.UNL(value=contract[u"host_unl"])
        if our_unl == host_unl:
            direction = u"send"
        else:
            direction = u"receive"

        return direction

    def simple_data_request(self, data_id, node_unl, direction):
        file_size = 0
        if direction == u"send":
            action = u"download"
        else:
            # We're download: so tell the peer to upload to us.
            action = u"upload"

        return self.data_request(action, data_id, file_size, node_unl)

    def data_request(self, action, data_id, file_size, node_unl):
        """
        Action = put (upload), get (download.)
        """
        _log.debug("In data request function")
        node_unl = node_unl.decode("utf-8")
        d = defer.Deferred()
        if node_unl == self.net.unl.value:
            e = "Can;t send data request to ourself"
            _log.debug(e)
            d.errback(Exception(e))
            return d

        # Who is hosting this data?
        if action == u"download":
            # We store this data.
            host_unl = self.net.unl.value.decode("utf-8")
            cfg = self.store_config
            _log.debug(cfg)
            _log.debug(data_id)
            assert(storjnode.storage.manager.find(cfg, data_id) is not None)
        else:
            # They store the data.
            host_unl = node_unl
            if data_id in self.downloading:
                e = "Already trying to download this."
                _log.debug(e)
                d.errback(Exception(e))
                return d

        # Create contract.
        contract = OrderedDict([
            (u"status", u"SYN"),
            (u"data_id", data_id.decode("utf-8")),
            (u"file_size", file_size),
            (u"host_unl", host_unl),
            (u"dest_unl", node_unl),
            (u"src_unl", self.net.unl.value)
        ])

        # Sign contract.
        contract = self.sign_contract(contract)

        # Check contract is valid.
        if is_valid_syn(self, contract) != 1:
            e = "our syn is invalid"
            _log.debug(e)
            d.errback(Exception(e))
            return d

        # Route contract.
        contract_id = self.save_contract(contract)
        self.send_msg(contract, node_unl)
        _log.debug("Sending data request")

        # Update handshake.
        self.handshake[contract_id] = {
            u"state": u"SYN",
            u"timestamp": time.time()
        }

        # For async code.
        self.defers[contract_id] = d

        # Return defer for async code.
        return contract_id

    def get_con_by_contract_id(self, needle):
        for con in list(self.con_info):
            for contract_id in list(self.con_info[con]):
                if contract_id == needle:
                    return con

        return None

    def remove_file_from_storage(self, data_id):
        storjnode.storage.manager.remove(self.store_config, data_id)

    def move_file_to_storage(self, path):
        with open(path, "rb") as shard:
            storjnode.storage.manager.add(self.store_config, shard)
            return {
                "file_size": storjnode.storage.shard.get_size(shard),
                "data_id": storjnode.storage.shard.get_id(shard)
            }

    def get_data_chunk(self, data_id, position, chunk_size=1048576):
        path = storjnode.storage.manager.find(self.store_config, data_id)
        buf = b""
        with open(path, "rb") as fp:
            fp.seek(position, 0)
            buf = fp.read(chunk_size)

            return buf

    def save_data_chunk(self, data_id, chunk):
        assert(data_id in self.downloading)

        # Find temp file path.
        path = self.downloading[data_id]

        with open(path, "ab") as fp:
            fp.write(chunk)
