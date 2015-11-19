import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
import logging
import storjnode.storage as storage
import storjnode
from storjnode.util import address_to_node_id
from storjnode.network.process_transfers import process_transfers
from collections import OrderedDict
from btctxstore import BtcTxStore
import tempfile
import time
import json
import hashlib
import sys
import os
import binascii
import struct
from threading import Lock
from twisted.internet import defer
from pycoin.encoding import a2b_hashed_base58, b2a_hashed_base58, a2b_base58, b2a_base58

_log = logging.getLogger(__name__)

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
            self.handlers["complete"] = []
        if "accept" not in self.handlers:
            self.handlers["accept"] = []

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

    def get_their_unl(self, contract):
        if self.net.unl == pyp2p.unl.UNL(value=contract["dest_unl"]):
            their_unl = contract["src_unl"]
        else:
            their_unl = contract["dest_unl"]

        return their_unl

    def get_node_id_from_unl(self, unl):
        unl = pyp2p.unl.UNL(value=unl).deconstruct()

        return unl["node_id"]

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
        contract = self.contracts[contract_id]
        if contract["data_id"] in self.downloading:
            if contract["direction"] == "receive":
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

    def send_msg(self, dict_obj, unl):
        node_id = self.net.unl.deconstruct(unl)["node_id"]
        msg = json.dumps(dict_obj, ensure_ascii=True)
        self.net.dht_node.relay_message(
            node_id,
            msg
        )

    def contract_id(self, contract):
        if sys.version_info >= (3, 0, 0):
            contract = str(contract).encode("ascii")
        else:
            contract = str(contract)

        return hashlib.sha256(contract).hexdigest()

    def sign_contract(self, contract):
        if sys.version_info >= (3, 0, 0):
            msg = str(contract).encode("ascii")
        else:
            msg = str(contract)

        msg = binascii.hexlify(msg).decode("utf-8")
        sig = self.wallet.sign_data(self.wif, msg)

        if sys.version_info >= (3, 0, 0):
            contract[u"signature"] = sig.decode("utf-8")
        else:
            contract[u"signature"] = unicode(sig)

        return contract

    def is_valid_contract_sig(self, contract, node_id=None):
        sig = contract[u"signature"][:]
        del contract[u"signature"]

        if sys.version_info >= (3, 0, 0):
            msg = str(contract).encode("ascii")
        else:
            msg = str(contract)

        # Use our address.
        msg = binascii.hexlify(msg).decode("utf-8")
        if node_id is None:
            address = self.wallet.get_address(self.wif)
            ret = self.wallet.verify_signature(address, sig, msg)
        else:
            # Use their node ID: try testnet.
            address = b2a_hashed_base58(b'o' + node_id)
            ret = self.wallet.verify_signature(address, sig, msg)
            if not ret:
                # Use their node ID: try mainnet.
                address = b2a_hashed_base58(b'\0' + node_id)
                ret = self.wallet.verify_signature(address, sig, msg)

        # Move sig back.
        contract[u"signature"] = sig[:]

        return ret

    def simple_data_request(self, data_id, node_unl, direction):
        file_size = 0
        if direction == u"send":
            action = u"upload"
        else:
            action = u"download"

        return self.data_request(action, data_id, file_size, node_unl)

    def data_request(self, action, data_id, file_size, node_unl):
        """
        Action = put (upload), get (download.)
        """
        _log.debug("In data request function")

        # Who is hosting this data?
        if action == "upload":
            # We store this data.
            direction = u"send"
            host_unl = self.net.unl.value
            assert(storage.manager.find(self.store_config, data_id) is not None)
        else:
            # They store the data.
            direction = u"receive"
            host_unl = node_unl
            if data_id in self.downloading:
                raise Exception("Already trying to download this.")

        # Encoding.
        if sys.version_info >= (3, 0, 0):
            if type(data_id) == bytes:
                data_id = data_id.decode("utf-8")

            if type(host_unl) == bytes:
                host_unl = host_unl.decode("utf-8")

            if type(node_unl) == bytes:
                node_unl = node_unl.decode("utf-8")
        else:
            if type(data_id) == str:
                data_id = unicode(data_id)

            if type(host_unl) == str:
                host_unl = unicode(host_unl)

            if type(node_unl) == str:
                node_unl = unicode(node_unl)

        # Create contract.
        contract = OrderedDict({
            u"status": u"SYN",
            u"direction": direction,
            u"data_id": data_id,
            u"file_size": file_size,
            u"host_unl": host_unl,
            u"dest_unl": node_unl,
            u"src_unl": self.net.unl.value,
        })

        # Sign contract.
        contract = self.sign_contract(contract)

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
        d = defer.Deferred()
        self.defers[contract_id] = d

        # Return defer for async code.
        return d

    def get_con_by_contract_id(self, needle):
        for con in list(self.con_info):
            for contract_id in list(self.con_info[con]):
                if contract_id == needle:
                    return con

        return None

    def remove_file_from_storage(self, data_id):
        storage.manager.remove(self.store_config, data_id)

    def move_file_to_storage(self, path):
        with open(path, "rb") as shard:
            storage.manager.add(self.store_config, shard)
            return {
                "file_size": storage.shard.get_size(shard),
                "data_id": storage.shard.get_id(shard)
            }

    def get_data_chunk(self, data_id, position, chunk_size=1048576):
        path = storage.manager.find(self.store_config, data_id)
        buf = b""
        with open(path, "rb") as fp:
            fp.seek(position, 0)
            buf = fp.read(chunk_size)

            return buf

    def save_data_chunk(self, data_id, chunk):
        _log.debug("Saving data chunk for " + str(data_id))
        _log.debug("of size + " + str(len(chunk)))
        assert(data_id in self.downloading)

        # Find temp file path.
        path = self.downloading[data_id]

        _log.debug(path)
        with open(path, "ab") as fp:
            fp.write(chunk)

if __name__ == "__main__":
    from crochet import setup
    setup()

    # Alice sample node.
    alice_wallet = BtcTxStore(testnet=False, dryrun=True)
    alice_wif = alice_wallet.create_key()

    alice_node_id = address_to_node_id(alice_wallet.get_address(alice_wif))
    # print(type(alice_node_id))
    alice_dht_node = pyp2p.dht_msg.DHT(node_id=alice_node_id)
    # print(alice_dht_node.get_id())


    alice_dht_node = storjnode.network.Node(
        alice_wif, bootstrap_nodes=[("240.0.0.0", 1337)],
        disable_data_transfer=True
    )


    alice = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60400,
            dht_node=alice_dht_node,
        ),
        wif=alice_wif,
        store_config={"/home/laurence/Storj/Alice": None}  # FIXME temppath
    )

    #alice_unl = alice.net.unl.value

    #print(alice.get_node_id_from_unl(alice_unl) == alice_node_id)
    #print(alice.net.unl.deconstruct())

    #reply = OrderedDict({"test": 5})
    #reply = alice.sign_contract(reply)

    #print(alice.is_valid_contract_sig(reply, alice.get_node_id_from_unl(alice_unl)))
    #print(reply)

    # exit()
    #exit()

    # ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab
    # _log.debug(_log.debug(alice.move_file_to_storage("/home/laurence/Firefox_wallpaper.png")))

    # exit()

    # Bob handlers.
    def accept_handler(node_id, data_id, direction):
        return 0
    handlers = {
        "accept": [accept_handler]
    }

    # Bob sample node.
    bob_wallet = BtcTxStore(testnet=False, dryrun=True)
    bob_wif = bob_wallet.create_key()
    bob_node_id = address_to_node_id(bob_wallet.get_address(bob_wif))

    print(bob_wif)
    print()
    print(binascii.hexlify(bob_node_id))

    bob_dht = pyp2p.dht_msg.DHT(node_id=bob_node_id)
    print(bob_dht.password)

    #exit()
    bob_dht = storjnode.network.Node(
        bob_wif, bootstrap_nodes=[("127.0.0.1", alice_dht_node.port)], disable_data_transfer=True
    )

    bob = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60401,
            dht_node=bob_dht,
        ),
        wif=bob_wif,
        store_config={"/home/laurence/Storj/Bob": None},  # FIXME use temppath
        handlers=handlers
    )

    _log.debug(alice.net.unl.deconstruct())
    _log.debug(bob.net.unl.deconstruct())

    # alice.net.unl == bob.net.unl

    _log.debug(type(alice.net.unl))
    _log.debug(type(pyp2p.unl.UNL(value=bob.net.unl.value)))

    #print("Giving nodes some time to find peers.")
    time.sleep(storjnode.network.WALK_TIMEOUT)

    # exit()

    # Alice wants data from Bob.
    d = alice.data_request(
        "upload",
        "ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab",
        0,
        bob.net.unl.value
    )

    def do_beep(ret):
        if ret != None:
            print("\a")

    d.addCallback(do_beep)

    """
    alice.data_request(
        "upload",
        "f2ca1bb6c7e907d06dafe4687e579fce76b37e4e93b7605022da52e6ccc26fd2",
        5,
        bob.net.unl.value
    )
    """

    # Main event loop.
    while 1:
        for client in [alice, bob]:
            if client == alice:
                _log.debug("Alice")
            else:
                _log.debug("Bob")
            process_transfers(client)

        time.sleep(0.002)

