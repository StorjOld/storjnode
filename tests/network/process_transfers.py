import storjnode
from storjnode.network import DEFAULT_BOOTSTRAP_NODES
from storjnode.network.file_transfer import FileTransfer
from storjnode.util import address_to_node_id
import btctxstore
import pyp2p
import tempfile
import os
import unittest
import shutil
import time
import hashlib
from twisted.internet import defer
from storjnode.network.process_transfers import get_contract_id
from storjnode.network.process_transfers import cleanup_cons
from storjnode.network.process_transfers import expire_handshakes
from storjnode.network.process_transfers import do_upload
from storjnode.network.process_transfers import do_download
from storjnode.network.process_transfers import process_dht_messages
from pyp2p.sock import Sock
from crochet import setup
setup()


_log = storjnode.log.getLogger(__name__)


class TestProcessTransfers(unittest.TestCase):

    def setUp(self):
        self.test_storage_dir = tempfile.mkdtemp()

        # Sample node.
        self.wallet = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.wallet.get_key(self.wallet.create_wallet())
        self.node_id = address_to_node_id(self.wallet.get_address(self.wif))
        self.store_config = {
            os.path.join(self.test_storage_dir, "storage"): {"limit": 0}
        }

        self.dht_node = pyp2p.dht_msg.DHT(
            node_id=self.node_id,
            networking=0
        )

        # Transfer client.
        self.client = FileTransfer(
            pyp2p.net.Net(
                node_type="simultaneous",
                nat_type="preserving",
                net_type="direct",
                passive_port=60500,
                dht_node=self.dht_node,
                wan_ip="8.8.8.8",
                debug=1
            ),
            wif=self.wif,
            store_config=self.store_config
        )

    def tearDown(self):
        shutil.rmtree(self.test_storage_dir)
        self.client.net.stop()

    def test_get_contract_id(self):
        con = Sock("towel.blinkenlights.nl", 23, blocking=1)
        self.client.con_transfer[con] = b""
        contract_id = b""
        assert(get_contract_id(self.client, con, contract_id) == 1)
        con.close()

    def test_cleanup_cons(self):
        con = Sock()
        con.close()
        self.client.con_info[con] = {}
        self.client.con_info[con]["something"] = 1
        self.client.defers["something"] = defer.Deferred()
        self.client.cons.append(con)
        cleanup_cons(self.client)

    def test_expired_handshake(self):
        contract_id = "something"
        self.client.contracts[contract_id] = {}
        self.client.handshake[contract_id] = {
            "timestamp": time.time() - 10000
        }
        self.client.defers[contract_id] = defer.Deferred()
        expire_handshakes(self.client)
        self.assertTrue(contract_id not in self.client.defers)

    def test_do_upload(self):
        contract = {
            "data_id": hashlib.sha256(b"0").hexdigest()
        }

        con_info = {
            "file_size": 0
        }

        con = Sock()

        # Data id doesn't exist.
        self.assertTrue(do_upload(self.client, con, contract, con_info) == 0)

    def test_do_download(self):
        contract = {
            "data_id": hashlib.sha256(b"0").hexdigest()
        }

        con_info = {
            "file_size": 0,
            "file_size_buf": b"x"
        }

        con = Sock("93.184.216.34", 80, blocking=1, timeout=15)
        con.send_line("GET / HTTP/1.1")
        con.send_line("Host: www.example.com\r\n\r\n")

        # Invalid file size.
        self.assertTrue(
            do_download(
                self.client,
                con,
                contract,
                con_info
            ) == -2)
        con.close()

        # Invalid found data hash.
        con = Sock("93.184.216.34", 80, blocking=1, timeout=15)
        con.send_line("GET / HTTP/1.1")
        con.send_line("Host: www.example.com\r\n\r\n")
        data_id = hashlib.sha256(b"0").hexdigest()
        contract = {
            "data_id": data_id
        }
        con_info = {
            "file_size": 2,
            "file_size_buf": b"x",
            "remaining": 1
        }
        junk, self.client.downloading[data_id] = tempfile.mkstemp()
        print(do_download(self.client, con, contract, con_info))
        con.close()

    def test_process_dht(self):
        process_dht_messages(None)


if __name__ == "__main__":
    unittest.main()
