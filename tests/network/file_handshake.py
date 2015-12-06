from btctxstore import BtcTxStore
from storjnode.util import address_to_node_id
from collections import OrderedDict
import unittest
import pyp2p.dht_msg
import pyp2p.unl
import json
from twisted.internet import defer
from storjnode.util import parse_node_id_from_unl
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.file_handshake import (is_valid_syn, process_syn,
                                              process_syn_ack, process_ack,
                                              process_rst, protocol)
import hashlib
import tempfile
import os
import time
import copy


callbacks_work = 0


class TestFileHandshake(unittest.TestCase):

    def setUp(self):
        # Alice
        self.alice_wallet = BtcTxStore(testnet=False, dryrun=True)
        self.alice_wif = "L18vBLrz3A5QxJ6K4bUraQQZm6BAdjuAxU83e16y3x7eiiHTApHj"
        self.alice_node_id = address_to_node_id(
            self.alice_wallet.get_address(self.alice_wif)
        )
        self.alice_dht_node = pyp2p.dht_msg.DHT(
            node_id=self.alice_node_id,
            networking=0
        )
        self.alice_storage = tempfile.mkdtemp()
        self.alice = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=0,
                dht_node=self.alice_dht_node,
                wan_ip="8.8.8.8",
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
        self.bob_dht_node = pyp2p.dht_msg.DHT(
            node_id=self.bob_node_id,
            networking=1
        )
        self.bob_storage = tempfile.mkdtemp()
        self.bob = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=0,
                dht_node=self.bob_dht_node,
                wan_ip="8.8.8.8",
                debug=1
            ),
            wif=self.bob_wif,
            store_config={self.bob_storage: None}
        )

        # Accept all transfers.
        def accept_handler(contract_id, src_unl, data_id, file_size):
            return 1

        # Add accept handler.
        self.alice.handlers["accept"].add(accept_handler)
        self.bob.handlers["accept"].add(accept_handler)

        # Link DHT nodes.
        self.alice_dht_node.add_relay_link(self.bob_dht_node)
        self.bob_dht_node.add_relay_link(self.alice_dht_node)

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
        def unl_connect(their_unl, events, force_master=1, hairpin=1,
                        nonce="0" * 64):
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
        data_id = u"5feceb66ffc86f38d952786c6d696c79"
        data_id += u"c2dbc239dd4e91b46729d73a27fb57e9"
        self.syn = OrderedDict([
            (u"status", u"SYN"),
            (u"data_id", data_id),
            (u"file_size", 100),
            (u"host_unl", self.alice.net.unl.value),
            (u"dest_unl", self.bob.net.unl.value),
            (u"src_unl", self.alice.net.unl.value)
        ])

    def tearDown(self):
        self.alice.net.stop()
        self.bob.net.stop()

    def test_message_flow(self):
        print("")
        print("Testing message flow")
        print("")

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
        self.assertIsInstance(syn, OrderedDict)

        print(self.alice.net.unl.value)
        print(self.bob.net.unl.value)
        print(syn)

        # Bob: process SYN, build SYN-ACK.
        syn_ack = process_syn(self.bob, syn)
        self.assertIsInstance(syn_ack, OrderedDict)

        # Alice: process SYN-ACK, build ACK.
        ack = process_syn_ack(self.alice, syn_ack)
        self.assertIsInstance(ack, OrderedDict)

        # Bob: process ack.
        fin = process_ack(self.bob, ack)
        self.assertTrue(fin == 1)

        print("")
        print("Done testing message flow")
        print("")

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

    def test_sign_syn(self):
        print("")
        print("Testing sign syn")
        print("")

        self.clean_slate_all()

        syn = copy.deepcopy(self.syn)
        signed_syn = self.alice.sign_contract(syn)
        print(signed_syn)

        print(self.alice.is_valid_contract_sig(signed_syn))
        node_id = self.alice.net.dht_node.get_id()
        print(node_id)
        self.assertEqual(
            self.alice.is_valid_contract_sig(signed_syn, node_id), 1
        )
        node_id = parse_node_id_from_unl(self.alice.net.unl.value)
        self.assertEqual(
            self.alice.is_valid_contract_sig(signed_syn, node_id), 1
        )
        print(node_id)

        self.assertTrue(syn[u"src_unl"] == self.alice.net.unl.value)

        print("Bob's perspective")
        assert(self.bob.is_valid_contract_sig(signed_syn, node_id))

        print("----")
        print(signed_syn)

        print("")
        print("End sign syn")
        print("")

    def test_process_syn(self):
        print("")
        print("Testing process syn")
        print("")

        self.clean_slate_all()
        syn = copy.deepcopy(self.syn)

        # Create file we're suppose to be uploading.
        path = os.path.join(self.alice_storage, syn[u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")

        # Test accept SYN with a handler.
        def request_handler(contract_id, src_unl, data_id, file_size):
            return 1
        self.bob.handlers["accept"] = [request_handler]
        syn = copy.deepcopy(self.syn)
        self.assertIsInstance(process_syn(
            self.bob, self.alice.sign_contract(syn), enable_accept_handlers=1
        ), OrderedDict)
        del syn["signature"]

        # Test reject SYN with a handler.
        def request_handler(contract_id, src_unl, data_id, file_size):
            return 0
        self.bob.handlers["accept"] = [request_handler]
        syn = copy.deepcopy(self.syn)
        self.assertTrue(process_syn(
            self.bob, self.alice.sign_contract(syn), enable_accept_handlers=1
        ) == -2)
        del syn["signature"]

        # Our UNL is incorrect.
        syn = copy.deepcopy(self.syn)
        syn[u"dest_unl"] = self.alice.net.unl.value
        self.assertTrue(process_syn(
            self.bob, self.alice.sign_contract(syn), enable_accept_handlers=0
        ) == -3)
        syn[u"dest_unl"] = self.bob.net.unl.value
        del syn["signature"]

        # Their sig is invalid.
        syn = copy.deepcopy(self.syn)
        syn[u"signature"] = "x"
        self.assertTrue(process_syn(
            self.bob, syn, enable_accept_handlers=0
        ) == -4)
        del syn["signature"]

        # Handshake state is incorrect.
        syn = copy.deepcopy(self.syn)
        syn = self.alice.sign_contract(syn)
        contract_id = self.bob.contract_id(syn)
        self.bob.handshake[contract_id] = "SYN"
        self.assertTrue(process_syn(
            self.bob, syn, enable_accept_handlers=0
        ) == -5)
        del self.bob.handshake[contract_id]

        # This should pass.
        self.assertIsInstance(process_syn(
            self.bob, syn, enable_accept_handlers=0
        ), OrderedDict)

        print("")
        print("Ending process syn")
        print("")

    def test_valid_syn_ack(self):
        print("")
        print("Testing process syn-ack")
        print("")

        self.clean_slate_all()

        syn = self.alice.sign_contract(copy.deepcopy(self.syn))
        syn_ack = OrderedDict([(u'status', u'SYN-ACK'), (u'syn', syn)])
        syn_ack = self.bob.sign_contract(syn_ack)

        # Clear any old contracts that might exist.
        self.alice.contracts = {}

        # Create file we're suppose to be uploading.
        path = os.path.join(self.alice_storage, syn_ack[u"syn"][u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")

        # Syn not in message.
        syn_ack_2 = copy.deepcopy(syn_ack)
        del syn_ack_2[u"syn"]
        self.assertTrue(process_syn_ack(self.alice, syn_ack_2) == -1)

        # Invalid fields.
        syn_ack_2 = copy.deepcopy(syn_ack)
        syn_ack_2[u"xxx"] = "0"
        self.assertTrue(process_syn_ack(self.alice, syn_ack_2) == -2)

        # Not a reply to something we sent.
        syn_ack_2 = copy.deepcopy(syn_ack)
        self.assertTrue(process_syn_ack(self.alice, syn_ack_2) == -3)

        # Save original SYN as a contract.
        contract_id = self.alice.contract_id(syn_ack_2[u"syn"])
        self.alice.contracts[contract_id] = syn_ack_2[u"syn"]

        # Is SYN valid.
        syn_ack_2 = copy.deepcopy(syn_ack)
        syn_ack_2[u"syn"][u"file_size"] = "10"
        contract_id = self.alice.contract_id(syn_ack_2[u"syn"])
        self.alice.contracts[contract_id] = syn_ack_2[u"syn"]
        self.assertTrue(process_syn_ack(self.alice, syn_ack_2) == -4)

        # Did we sign this?
        syn_ack_2 = copy.deepcopy(syn_ack)
        syn_ack_2[u"syn"][u"signature"] = "x"
        contract_id = self.alice.contract_id(syn_ack_2[u"syn"])
        self.alice.contracts[contract_id] = syn_ack_2[u"syn"]
        self.assertTrue(process_syn_ack(self.alice, syn_ack_2) == -5)

        # Check their sig is valid.
        syn_ack_2 = copy.deepcopy(syn_ack)
        syn_ack_2[u"signature"] = "x"
        contract_id = self.alice.contract_id(syn_ack_2[u"syn"])
        self.alice.contracts[contract_id] = syn_ack_2[u"syn"]
        self.assertTrue(process_syn_ack(self.alice, syn_ack_2) == -6)

        # Check handshake state is valid.
        syn_ack_2 = copy.deepcopy(syn_ack)
        self.alice.handshake = {}
        ret = process_syn_ack(self.alice, syn_ack_2)
        print("ERror 1")
        print(ret)
        self.assertTrue(ret == -7)
        self.alice.handshake[contract_id] = {
            u"state": u"ACK",
            u"timestamp": time.time()
        }
        contract_id = self.alice.contract_id(syn_ack_2[u"syn"])
        self.alice.contracts[contract_id] = syn_ack_2[u"syn"]
        self.assertTrue(process_syn_ack(self.alice, syn_ack_2) == -8)
        self.alice.handshake[contract_id] = {
            u"state": u"SYN",
            u"timestamp": time.time()
        }

        # This should pass.
        syn_ack_2 = copy.deepcopy(syn_ack)
        contract_id = self.alice.contract_id(syn_ack_2[u"syn"])
        self.alice.contracts[contract_id] = syn_ack_2[u"syn"]
        ret = process_syn_ack(self.alice, syn_ack_2)
        print(ret)
        self.assertIsInstance(ret, OrderedDict)

        print("")
        print("Ending process syn-ack")
        print("")

    def test_valid_ack(self):
        print("")
        print("Testing process ack")
        print("")

        self.clean_slate_all()

        syn = self.alice.sign_contract(copy.deepcopy(self.syn))
        syn_ack = OrderedDict([(u'status', u'SYN-ACK'), (u'syn', syn)])
        syn_ack = self.bob.sign_contract(syn_ack)
        ack = OrderedDict([(u'status', u'ACK'), (u'syn_ack', syn_ack)])
        ack = self.alice.sign_contract(ack)

        # SYN ack not in message.
        ack_2 = copy.deepcopy(ack)
        del ack_2[u"syn_ack"]
        self.assertTrue(process_ack(self.bob, ack_2) == -1)

        # Invalid length.
        ack_2 = copy.deepcopy(ack)
        ack_2["yy"] = 1
        self.assertTrue(process_ack(self.bob, ack_2) == -2)

        # Not a reply to our syn-ack.
        ack_2 = copy.deepcopy(ack)
        self.assertTrue(process_ack(self.bob, ack_2) == -3)

        # Our sig is invalid.
        ack_2 = copy.deepcopy(ack)
        ack_2[u"syn_ack"][u"signature"] = "x"
        contract_id = self.bob.contract_id(ack_2[u"syn_ack"][u"syn"])
        self.bob.contracts[contract_id] = ack_2[u"syn_ack"][u"syn"]
        self.assertTrue(process_ack(self.bob, ack_2) == -4)

        # Contract ID not in handshakes.
        ack_2 = copy.deepcopy(ack)
        contract_id = self.bob.contract_id(ack_2[u"syn_ack"][u"syn"])
        self.bob.contracts[contract_id] = ack_2[u"syn_ack"][u"syn"]
        self.alice.handshake = {}
        self.assertTrue(process_ack(self.bob, ack_2) == -5)

        # Handshake state is invalid.
        ack_2 = copy.deepcopy(ack)
        contract_id = self.bob.contract_id(ack_2[u"syn_ack"][u"syn"])
        self.bob.contracts[contract_id] = ack_2[u"syn_ack"][u"syn"]
        self.bob.handshake[contract_id] = {
            u"state": "SYN",
            u"timestamp": time.time()
        }
        self.assertTrue(process_ack(self.bob, ack_2) == -6)

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

        self.assertTrue(ret == 1)

        print("")
        print("Ending process ack")
        print("")

    def test_valid_rst(self):
        print("")
        print("Testing process rst")
        print("")

        self.clean_slate_all()

        syn = self.alice.sign_contract(copy.deepcopy(self.syn))

        # Rest contract state.
        self.bob.contracts = {}

        contract_id = self.alice.contract_id(syn)

        rst = OrderedDict([
            (u"status", u"RST"),
            (u"contract_id", contract_id),
            (u"src_unl", self.bob.net.unl.value)
        ])

        # Contract ID not in message.
        rst_2 = copy.deepcopy(rst)
        del rst_2["contract_id"]
        self.assertTrue(process_rst(self.alice, rst_2) == -1)

        # SRC UNL not in message.
        rst_2 = copy.deepcopy(rst)
        del rst_2["src_unl"]
        self.assertTrue(process_rst(self.alice, rst_2) == -2)

        # Contract not found.
        rst_2 = copy.deepcopy(rst)
        self.assertTrue(process_rst(self.alice, rst_2) == -3)

        # UNLs don't match for this contract.
        self.alice.contracts[contract_id] = syn
        rst_2 = copy.deepcopy(rst)
        rst_2[u"src_unl"] = self.alice.net.unl.value
        self.assertTrue(process_rst(self.alice, rst_2) == -4)

        # Sig doesn't match for this contract.
        rst_2 = copy.deepcopy(rst)
        self.assertTrue(process_rst(self.alice, rst_2) == -5)

        # This should pass.
        rst_2 = copy.deepcopy(rst)
        rst_2 = self.bob.sign_contract(rst_2)
        self.assertTrue(process_rst(self.alice, rst_2) == 1)

        # Setup callback.
        def callback(ret):
            global callbacks_work
            callbacks_work = 1

        # Check defer callbacks.
        d = defer.Deferred()
        self.alice.defers[contract_id] = d
        d.addErrback(callback)
        self.assertTrue(process_rst(self.alice, rst_2) == 1)
        self.assertTrue(callbacks_work == 1)

        print("")
        print("Ending process rst")
        print("")

    def test_valid_syn(self):
        print("")
        print("Testing is_valid_syn")
        print("")

        self.clean_slate_all()

        # Non existing fields.
        syn = {}
        self.assertTrue(is_valid_syn(self.alice, syn) == -1)

        # Invalid number of fields.
        syn = copy.deepcopy(self.syn)
        syn["test"] = "test"
        self.assertTrue(is_valid_syn(
            self.alice, self.alice.sign_contract(syn)) == -2
        )
        del syn["test"]
        del syn["signature"]

        # The data ID is wrong.
        syn["data_id"] = "x"
        self.assertTrue(is_valid_syn(
            self.alice, self.alice.sign_contract(syn)) == -3
        )
        syn["data_id"] = hashlib.sha256(b"0").hexdigest()
        del syn["signature"]

        # Syn is too big.
        """
        syn[u"file_size"] = int("9" * (5242880 + 10))
        self.assertTrue(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == -4)
        syn[u"file_size"] = 1
        """

        # Invalid UNLs.
        syn["host_unl"] = "0"
        self.assertTrue(is_valid_syn(
            self.alice, self.alice.sign_contract(syn)) == -6
        )
        syn["host_unl"] = self.alice.net.unl.value
        del syn["signature"]

        # Invalid file size.
        syn["file_size"] = str("0")
        self.assertTrue(is_valid_syn(
            self.alice, self.alice.sign_contract(syn)) == -7
        )
        syn["file_size"] = 20
        del syn["signature"]

        # We're the host and we don't have this file.
        self.assertTrue(is_valid_syn(
            self.alice, self.alice.sign_contract(syn)) == -8
        )
        del syn["signature"]

        # We're not the host. We're downloading this.
        # and we already have the file.
        syn[u"host_unl"] = self.bob.net.unl.value
        path = os.path.join(self.alice_storage, syn[u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")
        self.assertTrue(is_valid_syn(
            self.alice, self.alice.sign_contract(syn)) == -9
        )
        del syn["signature"]

        # We're not the host and we're already downloading this
        os.remove(path)
        self.alice.downloading[syn[u"data_id"]] = path
        self.assertTrue(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == -10)
        del self.alice.downloading[syn[u"data_id"]]
        del syn["signature"]

        # This should pass.
        self.assertTrue(is_valid_syn(
            self.alice, self.alice.sign_contract(syn)
        ) == 1)

        print("")
        print("Ending is_valid_syn")
        print("")


if __name__ == "__main__":
    unittest.main()
