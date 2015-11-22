from btctxstore import BtcTxStore
from storjnode.util import address_to_node_id
from collections import OrderedDict
import unittest
import pyp2p.dht_msg
import pyp2p.unl
from twisted.internet import defer
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.file_handshake import is_valid_syn, process_syn, process_syn_ack, process_ack, process_rst, protocol
import hashlib
import tempfile
import os
import time
import copy
import json

callbacks_work = 0
class TestFileHandshake(unittest.TestCase):

    def setUp(self):
        # Alice
        self.alice_wallet = BtcTxStore(testnet=False, dryrun=True)
        self.alice_wif = "L18vBLrz3A5QxJ6K4bUraQQZm6BAdjuAxU83e16y3x7eiiHTApHj"
        self.alice_node_id = address_to_node_id(
            self.alice_wallet.get_address(self.alice_wif))
        self.alice_dht_node = pyp2p.dht_msg.DHT(node_id=self.alice_node_id)
        self.alice_storage = tempfile.mkdtemp()
        self.alice = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=60405,
                dht_node=self.alice_dht_node,
                debug=1
            ),
            wif=self.alice_wif,
            store_config={self.alice_storage: None}
        )

        # Bob
        self.bob_wallet = BtcTxStore(testnet=False, dryrun=True)
        self.bob_wif = "L3DBWWbuL3da2x7qAmVwBpiYKjhorJuAGobecCYQMCV7tZMAnDsr"
        self.bob_node_id = address_to_node_id(
            self.bob_wallet.get_address(self.bob_wif))
        self.bob_dht_node = pyp2p.dht_msg.DHT(node_id=self.bob_node_id)
        self.bob_storage = tempfile.mkdtemp()
        self.bob = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=60409,
                dht_node=self.bob_dht_node,
                debug=1
            ),
            wif=self.bob_wif,
            store_config={self.bob_storage: None}
        )

        # Bypass sending messages for client.
        def send_msg(dict_obj, unl):
            print("Skipped sending message in test")
            print(dict_obj)
            print(unl)

        # Install send msg hooks.
        self.alice.send_msg = send_msg
        self.bob.send_msg = send_msg

        # Bypass sending relay messages for clients.
        def relay_msg(node_id, msg):
            print("Skipping relay message in test")
            print(node_id)
            print(msg)

        # Install relay msg hooks.
        if self.alice.net.dht_node is not None:
            self.alice.net.dht_node.relay_message = relay_msg

        if self.bob.net.dht_node is not None:
            self.bob.net.dht_node.relay_message = relay_msg

        # Bypass UNL.connect for clients.
        def unl_connect(their_unl, events, force_master=1, hairpin=1, nonce="0" * 64):
            print("Skipping UNL.connect!")
            print("Their unl = ")
            print(their_unl)
            print("Events = ")
            print(events)
            print("Force master = ")
            print(force_master)
            print("Hairpin = ")
            print(hairpin)
            print("Nonce = ")
            print(nonce)

        # Install UNL connect hooks.
        self.alice.net.unl.connect = unl_connect
        self.bob.net.unl.connect = unl_connect

        # Record syn.
        self.syn = OrderedDict({
            u"status": u"SYN",
            u"direction": u"send",
            u"data_id": u"5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
            u"file_size": 100,
            u"host_unl": self.alice.net.unl.value,
            u"dest_unl": self.bob.net.unl.value,
            u"src_unl": self.alice.net.unl.value
        })

    def tearDown(self):
        self.alice.net.stop()
        self.bob.net.stop()

    @unittest.skip("broken on travis")
    def test_message_flow(self):
        # Create file we're suppose to be uploading.
        path = os.path.join(self.alice_storage, self.syn[u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")

        # Clear existing contracts.
        self.clean_slate_all()

        # Alice: build SYN.
        contract_id = self.alice.simple_data_request(
            data_id=self.syn[u"data_id"],
            node_unl=self.bob.net.unl.value,
            direction=u"send"
        )
        syn = self.alice.contracts[contract_id]
        assert(type(syn) == OrderedDict)

        # Bob: process SYN, build SYN-ACK.
        syn_ack = process_syn(self.bob, syn)
        assert(syn_ack != 0)

        # Alice: process SYN-ACK, build ACK.
        ack = process_syn_ack(self.alice, syn_ack)
        assert(ack != 0)

        # Bob: process ack.
        fin = process_ack(self.bob, ack)
        assert(fin == 1)

    @unittest.skip("broken on travis")
    def test_protocol(self):
        # Create file we're suppose to be uploading.
        path = os.path.join(self.alice_storage, self.syn[u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")

        # Clear existing contracts.
        self.clean_slate_all()

        # Test broken JSON.
        msg = "{"
        assert(protocol(self.bob, msg) == 0)

        # No status in message.
        msg = '{}'
        assert(protocol(self.bob, msg) == 0)

        # Invalid status.
        msg = '{u"status": "X"}'
        assert(protocol(self.bob, msg) == 0)

        # Test valid message handlers.
        syn = copy.deepcopy(self.syn)
        syn = self.alice.sign_contract(syn)
        msg = json.dumps(syn, ensure_ascii=True)
        assert(protocol(self.bob, msg) == 1)

    def clean_slate(self, client):
        client.contracts = {}
        client.cons = []
        client.defers = {}
        client.handshake = {}
        client.con_info = {}
        client.con_transfer = {}
        client.downloading = {}

    def clean_slate_all(self):
        for client in [self.alice, self.bob]:
            self.clean_slate(client)

    @unittest.skip("broken on travis")
    def test_sign_syn(self):
        self.clean_slate_all()

        syn = copy.deepcopy(self.syn)
        signed_syn = self.alice.sign_contract(syn)
        print(signed_syn)

        print(self.alice.is_valid_contract_sig(signed_syn))
        node_id = self.alice.net.dht_node.get_id()
        print(node_id)
        assert(self.alice.is_valid_contract_sig(signed_syn, node_id) == 1)
        node_id = self.alice.get_node_id_from_unl(self.alice.net.unl.value)
        assert(self.alice.is_valid_contract_sig(signed_syn, node_id) == 1)
        print(node_id)

        assert(syn[u"src_unl"] == self.alice.net.unl.value)

        print("----")
        print(signed_syn)

    @unittest.skip("broken on travis")
    def test_process_syn(self):
        self.clean_slate_all()
        syn = copy.deepcopy(self.syn)

        # Create file we're suppose to be uploading.
        path = os.path.join(self.alice_storage, syn[u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")

        # Test accept SYN with a handler.
        def request_handler(src_node_id, data_id, direction):
            return 1
        self.bob.handlers["accept"] = [request_handler]
        assert(process_syn(self.bob, self.alice.sign_contract(syn), enable_accept_handlers=1) != 0)

        # Test reject SYN with a handler.
        def request_handler(src_node_id, data_id, direction):
            return 0
        self.bob.handlers["accept"] = [request_handler]
        assert(process_syn(self.bob, self.alice.sign_contract(syn), enable_accept_handlers=1) == 0)

        # Our UNL is incorrect.
        syn[u"dest_unl"] = self.alice.net.unl.value
        assert(process_syn(self.bob, self.alice.sign_contract(syn), enable_accept_handlers=0) == 0)
        syn[u"dest_unl"] = self.bob.net.unl.value

        # Their sig is invalid.
        syn[u"signature"] = "x"
        assert(process_syn(self.bob, syn, enable_accept_handlers=0) == 0)

        # Handshake state is incorrect.
        syn = self.alice.sign_contract(syn)
        contract_id = self.bob.contract_id(syn)
        self.bob.handshake[contract_id] = "SYN"
        assert(process_syn(self.bob, syn, enable_accept_handlers=0) == 0)
        del self.bob.handshake[contract_id]

        # This should pass.
        assert(process_syn(self.bob, syn, enable_accept_handlers=0))

    @unittest.skip("broken on travis")
    def test_valid_syn_ack(self):
        self.clean_slate_all()

        syn = self.alice.sign_contract(copy.deepcopy(self.syn))
        syn_ack = OrderedDict([(u'status', u'SYN-ACK'), (u'syn', syn), (u'signature', u'HwPZ1dVns8Q5GBMAxVVyKx/0tKJ/CxniCV5rBdX14ZvGzNcsQUMEjqn6IWgfOnfQpmmH53ShYgu7lTZVO7wt8yA=')])

        # Clear any old contracts that might exist.
        self.alice.contracts = {}

        # Save original SYN as a contract.
        contract_id = self.alice.contract_id(syn_ack[u"syn"])
        self.alice.contracts[contract_id] = syn_ack[u"syn"]

        # Create file we're suppose to be uploading.
        path = os.path.join(self.alice_storage, syn_ack[u"syn"][u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")

        # Syn not in message.
        syn_ack_2 = syn_ack.copy()
        del syn_ack_2[u"syn"]
        assert(process_syn_ack(self.alice, syn_ack_2) == 0)

        # Not a reply to something we sent.
        syn_ack_2 = syn_ack.copy()
        assert(process_syn_ack(self.alice, syn_ack_2) == 0)

        # Is SYN valid.
        syn_ack_2 = syn_ack.copy()
        data_id = syn_ack_2[u"syn"][u"data_id"]
        syn_ack_2[u"syn"][u"data_id"] = "x"
        contract_id = self.alice.contract_id(syn_ack_2[u"syn"])
        self.alice.contracts[contract_id] = syn_ack_2[u"syn"]
        assert(process_syn_ack(self.alice, syn_ack_2) == 0)
        syn_ack_2[u"syn"][u"data_id"] = data_id

        # Did we sign this?
        our_sig = syn_ack[u"syn"][u"signature"]
        syn_ack[u"syn"][u"signature"] = "x"
        contract_id = self.alice.contract_id(syn_ack[u"syn"])
        self.alice.contracts[contract_id] = syn_ack[u"syn"]
        assert(process_syn_ack(self.alice, syn_ack) == 0)
        syn_ack[u"syn"][u"signature"] = our_sig

        # Check their sig is valid.
        their_sig = syn_ack[u"signature"]
        syn_ack[u"signature"] = "x"
        contract_id = self.alice.contract_id(syn_ack[u"syn"])
        self.alice.contracts[contract_id] = syn_ack[u"syn"]
        assert(process_syn_ack(self.alice, syn_ack) == 0)
        syn_ack[u"signature"] = their_sig

        # Check handshake state is valid.
        assert(process_syn_ack(self.alice, syn_ack) == 0)
        self.alice.handshake[contract_id] = {
            u"state": u"ACK",
            u"timestamp": time.time()
        }
        contract_id = self.alice.contract_id(syn_ack[u"syn"])
        self.alice.contracts[contract_id] = syn_ack[u"syn"]
        assert(process_syn_ack(self.alice, syn_ack) == 0)
        self.alice.handshake[contract_id] = {
            u"state": u"SYN",
            u"timestamp": time.time()
        }

        # This should pass.
        contract_id = self.alice.contract_id(syn_ack[u"syn"])
        self.alice.contracts[contract_id] = syn_ack[u"syn"]
        ret = process_syn_ack(self.alice, syn_ack)
        print(ret)
        assert(ret != 0)

        # Invalid fields.
        syn_ack[u"xxx"] = "0"
        assert(process_syn_ack(self.alice, syn_ack) == 0)

    @unittest.skip("broken on travis")
    def test_valid_ack(self):
        self.clean_slate_all()

        syn = self.alice.sign_contract(copy.deepcopy(self.syn))
        ack = OrderedDict([(u'status', u'ACK'), (u'syn_ack', OrderedDict([(u'status', u'SYN-ACK'), (u'syn', syn), (u'signature', u'HwPZ1dVns8Q5GBMAxVVyKx/0tKJ/CxniCV5rBdX14ZvGzNcsQUMEjqn6IWgfOnfQpmmH53ShYgu7lTZVO7wt8yA=')])), (u'signature', u'ILaiKx9mrIoaRzk1V6ZphMJGkFPnaoto7rUihq/2k3igbOZ9aAWWkJ8KNteoW9ohr4aAhl2xVAvDstzlbLRoI7o=')])

        # SYN ack not in message.
        ack_2 = copy.deepcopy(ack)
        del ack_2[u"syn_ack"]
        assert(process_ack(self.bob, ack_2) == 0)

        # Invalid length.
        ack_2 = copy.deepcopy(ack)
        ack_2["yy"] = 1
        assert(process_ack(self.bob, ack_2) == 0)

        # Not a reply to our syn-ack.
        ack_2 = copy.deepcopy(ack)
        assert(process_ack(self.bob, ack_2) == 0)

        # Our sig is invalid.
        ack_2 = copy.deepcopy(ack)
        ack_2[u"syn_ack"][u"signature"] = "x"
        contract_id = self.bob.contract_id(ack_2[u"syn_ack"][u"syn"])
        self.bob.contracts[contract_id] = ack_2[u"syn_ack"][u"syn"]
        assert(process_ack(self.bob, ack_2) == 0)

        # Contract ID not in handshakes.
        ack_2 = copy.deepcopy(ack)
        contract_id = self.bob.contract_id(ack_2[u"syn_ack"][u"syn"])
        self.bob.contracts[contract_id] = ack_2[u"syn_ack"][u"syn"]
        assert(process_ack(self.bob, ack_2) == 0)

        # Handshake state is invalid.
        ack_2 = copy.deepcopy(ack)
        contract_id = self.bob.contract_id(ack_2[u"syn_ack"][u"syn"])
        self.bob.contracts[contract_id] = ack_2[u"syn_ack"][u"syn"]
        self.bob.handshake[contract_id] = {
            u"state": "SYN",
            u"timestamp": time.time()
        }
        assert(process_ack(self.bob, ack_2) == 0)

        # This should pass.
        ack_2 = copy.deepcopy(ack)
        contract_id = self.bob.contract_id(ack_2[u"syn_ack"][u"syn"])
        self.bob.contracts[contract_id] = ack_2[u"syn_ack"][u"syn"]
        self.bob.handshake[contract_id] = {
            u"state": "SYN-ACK",
            u"timestamp": time.time()
        }
        ret = process_ack(self.bob, ack_2)
        print(ret)

        assert(ret != 0)

    @unittest.skip("broken on travis")
    def test_valid_rst(self):
        self.clean_slate_all()

        syn = self.alice.sign_contract(self.syn)

        # Rest contract state.
        self.bob.contracts = {}

        contract_id = self.alice.contract_id(syn)

        rst = OrderedDict({
                u"status": u"RST",
                u"contract_id": contract_id,
                u"src_unl": self.bob.net.unl.value
        })

        # Contract ID not in message.
        rst_2 = copy.deepcopy(rst)
        del rst_2["contract_id"]
        assert(process_rst(self.alice, rst_2) == 0)

        # SRC UNL not in message.
        rst_2 = copy.deepcopy(rst)
        del rst_2["src_unl"]
        assert(process_rst(self.alice, rst_2) == 0)

        # Contract not found.
        rst_2 = copy.deepcopy(rst)
        assert(process_rst(self.alice, rst_2) == 0)

        # UNLs don't match for this contract.
        self.alice.contracts[contract_id] = syn
        rst_2 = copy.deepcopy(rst)
        rst_2[u"src_unl"] = self.alice.net.unl.value
        assert(process_rst(self.alice, rst_2) == 0)

        # Sig doesn't match for this contract.
        rst_2 = copy.deepcopy(rst)
        assert(process_rst(self.alice, rst_2) == 0)

        # This should pass.
        rst_2 = copy.deepcopy(rst)
        rst_2 = self.bob.sign_contract(rst_2)
        assert(process_rst(self.alice, rst_2) == 1)

        # Setup callback.
        def callback(ret):
            global callbacks_work
            callbacks_work = 1

        # Check defer callbacks.
        d = defer.Deferred()
        self.alice.defers[contract_id] = d
        d.addErrback(callback)
        assert(process_rst(self.alice, rst_2) == 1)
        assert(callbacks_work == 1)

    @unittest.skip("broken on travis")
    def test_valid_syn(self):
        self.clean_slate_all()

        # Non existing fields.
        syn = {}
        assert(is_valid_syn(self.alice, syn) == 0)

        # Huge syn.
        syn = OrderedDict({
            u"status": u"SYN",
            u"direction": "send",
            u"data_id": "0" * (5242880 + 10),
            u"file_size": 100,
            u"host_unl": self.alice.net.unl.value,
            u"dest_unl": self.alice.net.unl.value,
            u"src_unl": self.alice.net.unl.value
        })
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)
        syn["data_id"] = hashlib.sha256(b"0").hexdigest()

        # Invalid number of fields.
        syn["test"] = "test"
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)
        del syn["test"]

        # Invalid direction.
        syn["direction"] = "x"
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)
        syn["direction"] = "send"

        # Invalid UNLs.
        syn["host_unl"] = "0"
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)
        syn["host_unl"] = self.alice.net.unl.value

        # Invalid file size.
        syn["file_size"] = str("0")
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)
        syn["file_size"] = 20

        # The data ID is wrong.
        syn["data_id"] = "x"
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)
        syn["data_id"] = hashlib.sha256(b"0").hexdigest()

        # We're the host and we don't have this file.
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)

        # We're not the host. We're downloading this.
        # and we already have the file.
        syn[u"host_unl"] = self.bob.net.unl.value
        path = os.path.join(self.alice_storage, syn[u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")
        assert(is_valid_syn(self.alice, self.alice.sign_contract(syn)) == 0)

        # We're not the host and we're already downloading this
        os.remove(path)
        self.alice.downloading[syn[u"data_id"]] = path
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 0)
        del self.alice.downloading[syn[u"data_id"]]

        # This should pass.
        del syn["signature"]
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) != 0)


if __name__ == "__main__":
    unittest.main()

