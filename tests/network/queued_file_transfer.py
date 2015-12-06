import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
import storjnode
from storjnode.util import address_to_node_id
from storjnode.network.file_transfer import FileTransfer
from storjnode.network.process_transfers import process_transfers
from btctxstore import BtcTxStore
import tempfile
import time
import os
import unittest


_log = storjnode.log.getLogger(__name__)


queue_succeeded = 0


def test_queued():
    from crochet import setup
    setup()

    # Alice sample node.
    alice_wallet = BtcTxStore(testnet=False, dryrun=True)
    alice_wif = alice_wallet.create_key()
    alice_node_id = address_to_node_id(alice_wallet.get_address(alice_wif))
    alice_dht = pyp2p.dht_msg.DHT(
        node_id=alice_node_id,
        networking=0
    )
    alice = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=63400,
            dht_node=alice_dht,
            wan_ip="8.8.8.8",
            debug=1
        ),
        wif=alice_wif,
        store_config={tempfile.mkdtemp(): None},
    )

    # Bob sample node.
    bob_wallet = BtcTxStore(testnet=False, dryrun=True)
    bob_wif = bob_wallet.create_key()
    bob_node_id = address_to_node_id(bob_wallet.get_address(bob_wif))
    bob_dht = pyp2p.dht_msg.DHT(
        node_id=bob_node_id,
        networking=0
    )
    bob = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=63401,
            dht_node=bob_dht,
            wan_ip="8.8.8.8",
            debug=1
        ),
        wif=bob_wif,
        store_config={tempfile.mkdtemp(): None}
    )

    # Simulate Alice + Bob "connecting"
    alice_dht.add_relay_link(bob_dht)
    bob_dht.add_relay_link(alice_dht)

    # Accept all transfers.
    def accept_handler(contract_id, src_unl, data_id, file_size):
        return 1

    # Add accept handler.
    alice.handlers["accept"].add(accept_handler)
    bob.handlers["accept"].add(accept_handler)

    # Create file we're suppose to be uploading.
    data_id = ("5feceb66ffc86f38d952786c6d696c"
               "79c2dbc239dd4e91b46729d73a27fb57e9")
    path = os.path.join(list(alice.store_config)[0], data_id)
    if not os.path.exists(path):
        with open(path, "w") as fp:
            fp.write("0")

    # Alice wants to upload data to Bob.
    upload_contract_id = alice.data_request(
        "download",
        data_id,
        0,
        bob.net.unl.value
    )

    # Delete source file.
    def callback_builder(path, alice, bob, data_id):
        def callback(client, contract_id, con):
            print("Upload succeeded")
            print("Removing content and downloading back")
            os.remove(path)

            # Fix transfers.
            bob.handlers["complete"] = []

            # Synchronize cons and check con.unl.
            time.sleep(1)
            clients = {"alice": alice, "bob": bob}
            for client in list({"alice": alice, "bob": bob}):
                print()
                print(client)
                clients[client].net.synchronize()
                nodes_out = clients[client].net.outbound
                nodes_in = clients[client].net.inbound
                for node in nodes_out + nodes_in:
                    print(node["con"].unl)
                print(clients[client].cons)

            # Queued transfer:
            download_contract_id = alice.data_request(
                "upload",
                data_id,
                0,
                bob.net.unl.value
            )

            print("Download contract ID =")
            print(download_contract_id)

            # Indicate Bob's download succeeded.
            def alice_callback(val):
                print("Download succeeded")
                global queue_succeeded
                queue_succeeded = 1

            def alice_errback(val):
                print("Download failed! Error:")
                print(val)

            # Hook upload from bob.
            d = alice.defers[download_contract_id]
            d.addCallback(alice_callback)
            d.addErrback(alice_errback)

        return callback

    # Register callback for bob (when he's downloaded the data.)
    bob.handlers["complete"] = [
        callback_builder(path, alice, bob, data_id)
    ]

    # d = alice.defers[upload_contract_id]
    # d.addCallback(callback_builder(path, alice, bob, data_id))

    # Main event loop.
    timeout = time.time() + 40
    while not queue_succeeded and time.time() < timeout:
        for client in [alice, bob]:
            if client == alice:
                _log.debug("Alice")
            else:
                _log.debug("Bob")
            process_transfers(client)

        time.sleep(1)

    if not queue_succeeded:
        print("\a")

    for client in [alice, bob]:
        client.net.stop()

    assert(queue_succeeded == 1)


class TestQueuedTransfers(unittest.TestCase):
    def test_00001(self):
        test_queued()


if __name__ == "__main__":
    unittest.main()
