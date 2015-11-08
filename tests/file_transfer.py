import storjnode
from storjnode.network.file_transfer import FileTransfer, process_transfers
import btctxstore
import pyp2p
import random
import hashlib
import os
import time
import requests
import unittest
from crochet import setup
setup()

def map_path(path):
    return os.path.realpath \
    (
        os.path.expandvars \
        (
            os.path.expanduser(path)
        )
    )

def multiple_transfers():
    test_node = {
        "unl": "AWVRcVVhRXVIRlVWNGhEZWVDQ2tTcGdt8OsG79qiBu/aohkOP1YAAAAAiJCD36pqWoo=",
        "web": "http://162.218.239.6/"
    }

    def make_random_file(file_size=1024 * 100, directory="~/Storj"):
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
    wif = wallet.get_key(wallet.create_wallet())
    client = FileTransfer(
        pyp2p.net.Net(
            node_type="simultaneous",
            nat_type="preserving",
            net_type="direct",
            passive_port=60400,
            dht_node=pyp2p.dht_msg.DHT(),
            debug=1
        ),
        wif=wif,
        storage_path="/home/laurence/Storj/storage"
    )

    print("Net started")

    # Make random file in home directory.
    rand_file_infos = [make_random_file(), make_random_file()]

    # Move file to storage directory.
    file_infos = [
        client.move_file_to_storage(rand_file_infos[0]["path"]),
        client.move_file_to_storage(rand_file_infos[1]["path"])
    ]

    # Delete original file.
    os.remove(rand_file_infos[0]["path"])
    os.remove(rand_file_infos[1]["path"])

    # Upload file from storage.
    for file_info in file_infos:
        client.data_request(
            "upload",
            file_info["data_id"],
            file_info["file_size"],
            test_node["unl"]
        )

    # Process file transfers.
    duration = 40
    timeout = time.time() + duration
    while time.time() <= timeout or client.is_queued():
        process_transfers(client)
        time.sleep(0.02)

    # Check upload exists.
    for i in range(0, 2):
        url = test_node["web"] + file_infos[i]["data_id"]
        r = requests.get(url, timeout=3)
        if r.status_code != 200:
            print(r.status_code)
            assert(0)
        else:
            assert(r.content == rand_file_infos[i]["content"])
    print("File upload succeeded.")

    # Delete storage file copy.
    client.remove_file_from_storage(file_infos[0]["data_id"])
    client.remove_file_from_storage(file_infos[1]["data_id"])

    # Download file from storage.
    print("Testing download.")
    for file_info in file_infos:
        client.data_request(
            "download",
            file_info["data_id"],
            file_info["file_size"],
            test_node["unl"]
        )

    # Process file transfers.
    duration = 40
    timeout = time.time() + duration
    while time.time() <= timeout or client.is_queued():
        process_transfers(client)
        time.sleep(0.02)

    # Check we received this file.
    for i in range(0, 2):
        path = client.get_data_path(file_infos[i]["data_id"])
        if not os.path.isfile(path):
            assert(0)
        else:
            with open(path, "r") as fp:
                content = fp.read()
                assert(content == rand_file_infos[i]["content"])

    # Delete storage file copy.
    client.remove_file_from_storage(file_infos[0]["data_id"])
    client.remove_file_from_storage(file_infos[1]["data_id"])

    # Stop networking.
    client.net.stop()

    print("Upload succeeded.")

class test_file_transfer(unittest.TestCase):
    def test_multiple_transfers(self):
        multiple_transfers()


if __name__ == "__main__":
    unittest.main()