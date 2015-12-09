import storjnode
from storjnode.network import DEFAULT_BOOTSTRAP_NODES
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.process_transfers import process_transfers
from storjnode.util import address_to_node_id
import btctxstore
import pyp2p
import hashlib
import tempfile
import os
import time
import requests
import unittest
import shutil
from crochet import setup
setup()


_log = storjnode.log.getLogger(__name__)
_log.setLevel("DEBUG")


TEST_NODE = {
    "unl": ("AhaVDlV5HtHJlddtqgpDHdIFWdr5cGdt8OsG79qiBu/aouc/Ru4="),
    "web": "http://162.218.239.6/"
}


class TestFileTransfer(unittest.TestCase):

    def setUp(self):
        self.test_storage_dir = tempfile.mkdtemp()

        # Sample node.
        self.wallet = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.wallet.get_key(self.wallet.create_wallet())
        self.node_id = address_to_node_id(self.wallet.get_address(self.wif))
        self.store_config = {
            os.path.join(self.test_storage_dir, "storage"): {"limit": 0}
        }

        # dht_node = pyp2p.dht_msg.DHT(node_id=node_id)
        self.dht_node = storjnode.network.Node(
            self.wif, bootstrap_nodes=DEFAULT_BOOTSTRAP_NODES,
            disable_data_transfer=True
        )

        # Transfer client.
        self.client = FileTransfer(
            pyp2p.net.Net(
                node_type="simultaneous",
                nat_type="preserving",
                net_type="direct",
                passive_port=0,
                dht_node=self.dht_node,
                debug=1
            ),
            wif=self.wif,
            store_config=self.store_config
        )

        # Accept all transfers.
        def accept_handler(contract_id, src_unl, data_id, file_size):
            return 1

        # Add accept handler.
        self.client.handlers["accept"].add(accept_handler)

    def tearDown(self):
        shutil.rmtree(self.test_storage_dir)
        self.client.net.dht_node.stop()

    def test_con_by_contract_id(self):
        contract_id = "something"
        con = 1
        self.client.con_info[con] = {
            contract_id: {}
        }

        assert(self.client.get_con_by_contract_id(contract_id) == con)

    def test_move_file_to_storage(self):
        junk, path = tempfile.mkstemp()
        with open(path, "rw+") as fp:
            fp.write("1")
            data_id = storjnode.storage.shard.get_id(fp)

        self.client.move_file_to_storage(path)
        self.client.remove_file_from_storage(data_id)

    def test_cleanup_transfers(self):
        con = "con"
        contract_id = "contract_id"
        data_id = "data_id"
        self.client.contracts[contract_id] = {
            "data_id": data_id,
            "host_unl": self.client.net.unl.value,
            "src_unl": self.client.net.unl.value,
            "dest_unl": self.client.net.unl.value
        }
        self.client.handshake[contract_id] = {}
        self.client.defers[contract_id] = {}
        self.client.con_transfer[con] = {}
        self.client.con_info[con] = {}
        self.client.cleanup_transfers(con, contract_id)

    def test_data_request(self):
        # Sending data to ourselves.
        self.client.data_request(
            "upload",
            "something",
            100,
            self.client.net.unl.value
        )

        # Already download this.
        data_id = "something"
        self.client.downloading[data_id] = 1
        try:
            self.client.data_request(
                "upload",
                data_id,
                100,
                "another hosts unl"
            )
            assert(0)
        except:
            return

    def test_simple_data_request(self):
        self.client.simple_data_request(
            "something",
            self.client.net.unl.value,
            "receive"
        )

    def test_invalid_our_syn(self):
        self.client.simple_data_request(
            "something",
            "invalid unl",
            "receive"
        )

    @unittest.skip("Disable because too slow: move to node test code")
    def test_multiple_transfers(self):

        def make_random_file(file_size=1024 * 100,
                             directory=self.test_storage_dir):
            content = os.urandom(file_size)
            file_name = hashlib.sha256(content[0:64]).hexdigest()
            path = storjnode.util.full_path(os.path.join(directory, file_name))
            with open(path, "wb") as fp:
                fp.write(content)
            return {
                "path": path,
                "content": content
            }

        # print("Giving nodes some time to find peers.")
        time.sleep(storjnode.network.WALK_TIMEOUT)
        self.dht_node.refresh_neighbours()
        time.sleep(storjnode.network.WALK_TIMEOUT)

        _log.debug("Net started")

        # Make random file
        rand_file_infos = [make_random_file()]

        # Move file to storage directory.
        file_infos = [
            self.client.move_file_to_storage(rand_file_infos[0]["path"])
        ]

        # Delete original file.
        os.remove(rand_file_infos[0]["path"])

        _log.debug("Testing upload")

        # Upload file from storage.
        for file_info in file_infos:
            self.client.data_request(
                "download",
                file_info["data_id"],
                0,
                TEST_NODE["unl"]
            )

        # Process file transfers.
        duration = 15
        timeout = time.time() + duration
        while time.time() <= timeout or self.client.is_queued():
            process_transfers(self.client)
            time.sleep(0.002)

        # Check upload exists.
        for i in range(0, 1):
            url = TEST_NODE["web"] + file_infos[i]["data_id"]
            r = requests.get(url, timeout=3)
            if r.status_code != 200:
                _log.debug(r.status_code)
                assert(0)
            else:
                assert(r.content == rand_file_infos[i]["content"])
        _log.debug("File upload succeeded.")

        # Delete storage file copy.
        self.client.remove_file_from_storage(file_infos[0]["data_id"])

        # Download file from storage.
        _log.debug("Testing download.")
        for file_info in file_infos:
            self.client.data_request(
                "upload",
                file_info["data_id"],
                0,
                TEST_NODE["unl"]
            )

        # Process file transfers.
        duration = 15
        timeout = time.time() + duration
        while time.time() <= timeout or self.client.is_queued():
            process_transfers(self.client)
            time.sleep(0.002)

        # Check we received this file.
        for i in range(0, 1):
            path = storjnode.storage.manager.find(self.store_config,
                                                  file_infos[i]["data_id"])
            if not os.path.isfile(path):
                assert(0)
            else:
                with open(path, "r") as fp:
                    content = fp.read()
                    assert(content == rand_file_infos[i]["content"])

        # Delete storage file copy.
        self.client.remove_file_from_storage(file_infos[0]["data_id"])

        _log.debug("Download succeeded.")

        # Test cleanup transfers.
        for con in list(self.client.con_info):
            con.close()
            for contract_id in list(self.client.con_info[con]):
                self.client.cleanup_transfers(con, contract_id)


if __name__ == "__main__":
    unittest.main()
