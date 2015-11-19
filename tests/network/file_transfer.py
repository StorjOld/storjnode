import storjnode
from storjnode.network.api import DEFAULT_BOOTSTRAP_NODES
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.process_transfers import process_transfers
from storjnode.util import address_to_node_id
import storjnode.storage as storage
import btctxstore
import pyp2p
import hashlib
import tempfile
import os
import time
import requests
import unittest
import shutil
import logging
from crochet import setup
setup()


_log = logging.getLogger(__name__)


TEST_NODE = {
    "unl": ("AhaVDlV5HtHJlddtqgpDHdIFWdr5cGdt8OsG79qiBu/aouc/Ru4="),
    "web": "http://162.218.239.6/"
}


class TestFileTransfer(unittest.TestCase):

    def setUp(self):
        self.test_storage_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_storage_dir)

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

        # Sample node.
        wallet = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        wif = wallet.get_key(wallet.create_wallet())
        node_id = address_to_node_id(wallet.get_address(wif))
        store_config = {
            os.path.join(self.test_storage_dir, "storage"): {"limit": 0}
        }
        #dht_node = pyp2p.dht_msg.DHT(node_id=node_id)
        dht_node = storjnode.network.Node(wif, bootstrap_nodes=DEFAULT_BOOTSTRAP_NODES, disable_data_transfer=True)
        client = FileTransfer(
            pyp2p.net.Net(
                node_type="simultaneous",
                nat_type="preserving",
                net_type="direct",
                passive_port=60400,
                dht_node=dht_node,
                debug=1
            ),
            wif=wif,
            store_config=store_config
        )


        #print("Giving nodes some time to find peers.")
        time.sleep(storjnode.network.WALK_TIMEOUT)
        dht_node.refresh_neighbours()
        time.sleep(storjnode.network.WALK_TIMEOUT)

        _log.debug("Net started")

        # Make random file
        rand_file_infos = [make_random_file()]

        # Move file to storage directory.
        file_infos = [
            client.move_file_to_storage(rand_file_infos[0]["path"])
        ]

        # Delete original file.
        os.remove(rand_file_infos[0]["path"])

        _log.debug("Testing upload")

        # Upload file from storage.
        for file_info in file_infos:
            client.data_request(
                "upload",
                file_info["data_id"],
                0,
                TEST_NODE["unl"]
            )

        # Process file transfers.
        duration = 15
        timeout = time.time() + duration
        while time.time() <= timeout or client.is_queued():
            process_transfers(client)
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
        client.remove_file_from_storage(file_infos[0]["data_id"])

        # Download file from storage.
        _log.debug("Testing download.")
        for file_info in file_infos:
            client.data_request(
                "download",
                file_info["data_id"],
                0,
                TEST_NODE["unl"]
            )

        # Process file transfers.
        duration = 15
        timeout = time.time() + duration
        while time.time() <= timeout or client.is_queued():
            process_transfers(client)
            time.sleep(0.002)

        # Check we received this file.
        for i in range(0, 1):
            path = storage.manager.find(store_config, file_infos[i]["data_id"])
            if not os.path.isfile(path):
                assert(0)
            else:
                with open(path, "r") as fp:
                    content = fp.read()
                    assert(content == rand_file_infos[i]["content"])

        # Delete storage file copy.
        client.remove_file_from_storage(file_infos[0]["data_id"])

        # Stop networking.
        dht_node.stop()

        _log.debug("Download succeeded.")


if __name__ == "__main__":
    unittest.main()
