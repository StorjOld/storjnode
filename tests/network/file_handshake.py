from btctxstore import BtcTxStore
from storjnode.util import address_to_node_id
from collections import OrderedDict
import unittest
import pyp2p.dht_msg
import pyp2p.unl
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.file_handshake import is_valid_syn, process_syn
import hashlib
import tempfile
import os

class TestFileHandshake(unittest.TestCase):

    def setUp(self):
        # Alice
        self.alice_wallet = BtcTxStore(testnet=False, dryrun=True)
        self.alice_wif = self.alice_wallet.create_key()
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
            ),
            wif=self.alice_wif,
            store_config={self.alice_storage: None}
        )

        # Bob
        self.bob_wallet = BtcTxStore(testnet=False, dryrun=True)
        self.bob_wif = self.bob_wallet.create_key()
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

        # Bypass sending relay messages for client.
        def relay_msg(node_id, msg):
            print("Skipping relay message in test")
            print(node_id)
            print(msg)

        # Install relay msg hooks.
        self.alice.net.dht_node.relay_message = relay_msg
        self.bob.net.dht_node.relay_message = relay_msg

    def tearDown(self):
        self.alice.net.stop()
        self.bob.net.stop()

    def test_process_syn(self):
        syn = OrderedDict({
            u"status": u"SYN",
            u"direction": "send",
            u"data_id": "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
            u"file_size": 100,
            u"host_unl": self.alice.net.unl.value,
            u"dest_unl": self.bob.net.unl.value,
            u"src_unl": self.alice.net.unl.value
        })

        # Create file we're support to be uploading.
        path = os.path.join(self.alice_storage, syn[u"data_id"])
        if not os.path.exists(path):
            with open(path, "w") as fp:
                fp.write("0")

        # Test accept SYN with a handler.
        def request_handler(src_node_id, data_id, direction):
            return 1

        self.bob.handlers["accept"] = [request_handler]
        assert(process_syn(self.bob, self.alice.sign_contract(syn), enable_accept_handlers=1) == 1)

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

    @unittest.skip("")
    def test_valid_syn_ack(self):
        pass

    @unittest.skip("")
    def test_valid_ack(self):
        pass

    @unittest.skip("")
    def test_valid_rst(self):
        pass

    @unittest.skip("")
    def test_valid_syn(self):
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

        # Invalid signature.
        assert(is_valid_syn(
            self.alice,
            syn
        ) == 0)

        # This should pass.
        del syn["signature"]
        assert(is_valid_syn(
            self.alice,
            self.alice.sign_contract(syn)
        ) == 1)


if __name__ == "__main__":
    unittest.main()

