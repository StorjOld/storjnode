from storjnode.network.file_transfer import map_path, FileTransfer, process_transfers
import btctxstore
import pyp2p
import random
import hashlib
import os
import time
import requests
import unittest

class TestBlockingNode(unittest.TestCase):
    def test_sequential_upload_and_download(self):
        test_node = {
            "unl": "AWl6STFvQTJCdzFiQWxrRVB3SDFlcGdmlcUG79qiBu/aotq7PFYAAAAAEHcoHLmdnHw=",
            "web": "http://162.218.239.6/"
        }

        def make_random_file(file_size=1024 * 100, directory="~/"):
            content = b""
            for i in range(0, file_size):
                code = int(random.randrange(0, 256))
                content += chr(code)

            file_name = hashlib.sha256(content[0:64]).hexdigest()
            path = map_path(os.path.join(directory, file_name))
            with open(path, "wb") as fp:
                fp.write(content)

            ret = {
                "path": path,
                "content": content
            }

            return ret

        # Sample node.
        wallet = btctxstore.BtcTxStore(testnet=True, dryrun=True)
        client = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                passive_port=60400,
                dht_node=pyp2p.dht_msg.DHT(),
                debug=1
            ),
            wallet=wallet
        )

        # Make random file in home directory.
        rand_file_info = make_random_file()

        # Move file to storage directory.
        file_info = client.move_file_to_storage(rand_file_info["path"])

        # Delete original file.
        os.remove(rand_file_info["path"])

        # Upload file from storage.
        print("Testing upload.")
        client.data_request(
            "upload",
            file_info["data_id"],
            file_info["file_size"],
            test_node["unl"]
        )

        # Process file transfers.
        duration = 10
        timeout = time.time() + duration
        while time.time() <= timeout or client.net.get_connection_no():
            process_transfers(client)
            time.sleep(0.5)

        # Check upload exists.
        url = test_node["web"] + file_info["data_id"]
        r = requests.get(url, timeout=3)
        if r.status_code != 200:
            print(r.status_code)
            assert(0)
        else:
            assert(r.content == rand_file_info["content"])
        print("File upload succeeded.")

        # Delete storage file copy.
        client.remove_file_from_storage(file_info["data_id"])

        # Download file from storage.
        print("Testing download.")
        client.data_request(
            "download",
            file_info["data_id"],
            file_info["file_size"],
            test_node["unl"]
        )

        # Process file transfers.
        duration = 10
        timeout = time.time() + duration
        while time.time() <= timeout or client.net.get_connection_no():
            process_transfers(client)
            time.sleep(0.5)

        # Check we received this file.
        path = client.get_data_path(file_info["data_id"])
        if not os.path.isfile(path):
            assert(0)
        else:
            with open(path, "r") as fp:
                content = fp.read()
                assert(content == rand_file_info["content"])

        # Delete storage file copy.
        client.remove_file_from_storage(file_info["data_id"])

        # Stop networking.
        client.net.stop()

        print("Upload succeeded.")