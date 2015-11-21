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

    def tearDown(self):
        self.alice.net.stop()
        self.bob.net.stop()

    def test_process_syn(self):
        """
        syn = OrderedDict({
            u"status": u"SYN",
            u"direction": "send",
            u"data_id": "0" * (5242880 + 10),
            u"file_size": 100,
            u"host_unl": self.alice.net.unl.value,
            u"dest_unl": self.alice.net.unl.value,
            u"src_unl": self.alice.net.unl.value
        })
        """

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
        ))


if __name__ == "__main__":
    unittest.main()

