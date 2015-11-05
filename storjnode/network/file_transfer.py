"""
Issues:
    * Delete con_info and con_transfers when con is closed
    * Should contract also be deleted when its transfered? Prob
"""

import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg

from collections import OrderedDict
from btctxstore import BtcTxStore
import time
import json
import hashlib
import sys
import os
import shutil
import binascii
import platform


def process_transfers(client):
    # Process contract messages.
    if client.net.dht_node.has_messages():
        for msg in client.net.dht_node.get_messages():
            print(msg)
            client.protocol(msg)

    # Process connections.
    for con in client.net:
        print("In con.")

        # This is an new (or old) connection.
        if con not in client.con_info:
            print("Con not in con_info")
            continue

        # Get active contract ID.
        if con not in client.con_transfer:
            client.con_transfer[con] = u""
        contract_id = client.con_transfer[con]
        if len(contract_id) < 64:
            remaining = 64 - len(contract_id)
            partial = con.recv(remaining)
            client.con_transfer[con] += partial
            print("Skipping contract id.")
            continue

        # Anything left to do?
<<<<<<< HEAD
        con_info = client.con_info[con][contract_id]
=======
        con_info = client.con_info[con]
>>>>>>> eaefdea82575fbc746c4ebe8b85dc4f9aa868ff1
        if not con_info["remaining"]:
            print("Skipping remaining.")
            continue

        # Upload.
        contract = client.contracts[contract_id]
        if client.net.unl == pyp2p.unl.UNL(value=contract["host_unl"]):
            print("Uploading: Found our UNL")

            # Get next chunk from file.
            position = contract["file_size"] - con_info["remaining"]
            data_chunk = client.get_data_chunk(
                contract["data_id"],
                position
            )

            # Upload chunk binary to socket.
            bytes_sent = con.send(data_chunk)
            print(bytes_sent)
            if bytes_sent:
                con_info["remaining"] -= bytes_sent

            # Everything uploaded.
            if not con_info["remaining"]:
                client.queue_next_upload(con)
        else:
            print("Attempting to download.")

            # Download.
            data = con.recv(
                con_info["remaining"],
                encoding="ascii"
            )
            print(con.connected)

            if len(data):
                con_info["remaining"] -= len(data)
                client.save_data_chunk(contract["data_id"], data)

            # When done downloading close con.
            if not con_info["remaining"]:
                # Remove that we're downloading this.
                data_id = contract["data_id"]
                if data_id in client.downloading:
                    del client.downloading[data_id]

                # Delete file if it doesn't hash right!
                path = client.get_data_path(data_id)
                if client.hash_file(path) != data_id:
                    print("Error: downloaded file doesn't hash right!")
                    os.remove(path)

                # Ready for a new transfer (if there are any.)
                client.con_transfer[con] = u""




def map_path(path):
    return os.path.realpath(os.path.expandvars(os.path.expanduser(path)))


class FileTransfer:
    def __init__(self, net, wallet, storage_path=None, debug=1):
        # Accept direct connections.
        self.net = net

        # Used for signing messages.
        self.wallet = wallet
        self.wif = self.wallet.create_key()

        # Where will the data be stored?
        self.storage_path = storage_path
        if self.storage_path is None:
            if platform.system() == "Darwin":
                self.storage_path = "~/Library/Application Support/"
                self.storage_path += "Storj/storage"

            if platform.system() == "Windows":
                self.storage_path = "%APPDATA%\\Storj\\storage"

            if platform.system() == "Linux":
                self.storage_path = "~/.Storage/storage"

        # Does the path exist? If not create it.
        self.storage_path = map_path(self.storage_path)
        if not os.path.isdir(self.storage_path):
            os.makedirs(self.storage_path)

        # Enable debug print.
        self.debug = debug

        # Start networking.
        if not self.net.is_net_started:
            self.net.start()

        # Dict of data requests.
        self.contracts = {}

        # Three-way handshake status for contracts.
        self.handshake = {}

        # All contracts associated with this connection.
        self.con_info = {}

        # File transfer currently active on connection.
        self.con_transfer = {}

        # List of active downloads.
        # (Never try to download multiple copies of the same thing at once.)
        self.downloading = {}

    def debug_print(self, msg):
        if self.debug:
            print("> " + str(msg))

    def queue_next_upload(self, con):
        for contract_id in list(self.con_info[con]):
            con_info = self.con_info[con][contract_id]
            if con_info["remaining"]:
                self.con_transfer[con] = contract_id
                con.send(contract_id, send_all=1)
                return

        # No more uploads.
        con.close()
        del self.con_transfer[con]

    def is_valid_syn(self, msg):
        # List of expected fields.
        syn_schema = (
            u"status",
            u"data_id",
            u"file_size",
            u"host_unl",
            u"dest_unl",
            u"src_unl",
            u"signature"
        )

        # Check all fields exist.
        if not all(key in msg for key in syn_schema):
            self.debug_print("Missing required key.")
            return 0

        # Check the UNLs are valid.
        unl_tuple = (u"host_unl", u"dest_unl", u"src_unl")
        for unl_key in unl_tuple:
            if not pyp2p.unl.is_valid_unl(msg[unl_key]):
                self.debug_print("Invalid UNL for " + unl_key)
                self.debug_print(msg[unl_key])
                return 0

        # Check file size.
        file_size_type = type(msg[u"file_size"])
        if sys.version_info >= (3, 0, 0):
            expr = file_size_type != int
        else:
            expr = file_size_type != int and file_size_type != long
        if expr:
            self.debug_print("File size validation failed")
            self.debug_print(type(msg[u"file_size"]))
            return 0

        # Are we the host?
        if self.net.unl == pyp2p.unl.UNL(value=msg[u"host_unl"]):
            # Then check we have this file.
            path = self.get_data_path(msg[u"data_id"])
            if not os.path.isfile(path):
                self.debug_print("Failed to find file we're uploading")
                return 0

            # Did they specify the right size?
            if os.path.getsize(path) != msg[u"file_size"]:
                self.debug_print("Client did not specify correct file siz.e")
                return 0
        else:
            # Do we already have this file?
            path = self.get_data_path(msg[u"data_id"])
            if os.path.isfile(path):
                self.debug_print("Attempting to download file we already have")
                return 0

            # Are we already trying to download this?
            if msg[u"data_id"] in self.downloading:
                self.debug_print("We're already trying to download this")
                return 0

        return 1

    def protocol(self, msg):
        msg = json.loads(msg, object_pairs_hook=OrderedDict)

        # Associate TCP con with contract.
        def success_wrapper(self, contract_id, host_unl):
            def success(con):
                # Associate TCP con with contract.
                file_size = self.contracts[contract_id]["file_size"]

                # Store con association.
                if con not in self.con_info:
                    self.con_info[con] = {}

                # Associate contract with con.
                if contract_id not in self.con_info[con]:
                    self.con_info[con][contract_id] = {
                        "contract_id": contract_id,
                        "remaining": file_size
                    }

                # Record download state.
                data_id = self.contracts[contract_id]["data_id"]
                if self.net.unl != pyp2p.unl.UNL(value=host_unl):
                    self.downloading[data_id] = 1
                else:
                    # Set initial upload for this con.
                    if con not in self.con_transfer:
                        self.con_transfer[con] = contract_id
                        con.send(contract_id, send_all=1)

            return success

        # Sanity checking.
        if u"status" not in msg:
            return

        # Accept data request.
        if msg[u"status"] == u"SYN":
            # Check syn is valid.
            if not self.is_valid_syn(msg):
                self.debug_print("SYN: invalid syn.")
                return

            # Save contract.
            self.save_contract(msg)

            # Create reply.
            reply = OrderedDict({
                u"status": u"SYN-ACK",
                u"syn": msg,
            })

            # Sign reply.
            reply = self.sign_contract(reply)

            # Save reply.
            self.send_msg(reply, msg[u"src_unl"])
            print("SYN")

        # Confirm accept and make connection if needed.
        if msg[u"status"] == u"SYN-ACK":
            # Valid syn-ack?
            if u"syn" not in msg:
                self.debug_print("SYN-ACK: syn not in msg.")
                return

            # Is this a reply to our SYN?
            contract_id = self.contract_id(msg[u"syn"])
            if contract_id not in self.contracts:
                self.debug_print("--------------")
                self.debug_print(msg)
                self.debug_print("--------------")
                self.debug_print(self.contracts)
                self.debug_print("--------------")
                self.debug_print("SYN-ACK: contract not found.")
                return

            # Check syn is valid.
            if not self.is_valid_syn(msg[u"syn"]):
                self.debug_print("SYN-ACK: invalid syn.")
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg[u"syn"]):
                self.debug_print("SYN-ACK: sig is invalid.")
                return

            # Update handshake.
            contract = self.contracts[contract_id]
            self.handshake[contract_id] = u"SYN-ACK"

            # Create reply contract.
            reply = OrderedDict({
                u"status": u"ACK",
                u"syn_ack": msg
            })

            # Sign reply.
            reply = self.sign_contract(reply)

            # Try make TCP con.
            self.net.unl.connect(
                contract["dest_unl"],
                {
                    "success": success_wrapper(
                        self,
                        contract_id,
                        contract["host_unl"]
                    )
                },
                force_master=0
            )

            # Send reply.
            self.send_msg(reply, msg[u"syn"][u"dest_unl"])
            print("SYN-ACK")

        if msg[u"status"] == u"ACK":
            # Valid ack.
            if u"syn_ack" not in msg:
                self.debug_print("ACK: syn_ack not in msg.")
                return
            if u"syn" not in msg[u"syn_ack"]:
                self.debug_print("ACK: syn not in msg.")
                return

            # Is this a reply to our SYN-ACK?
            contract_id = self.contract_id(msg[u"syn_ack"][u"syn"])
            if contract_id not in self.contracts:
                self.debug_print("ACK: contract not found.")
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg[u"syn_ack"]):
                self.debug_print("--------------")
                self.debug_print(msg)
                self.debug_print("--------------")
                self.debug_print(self.contracts)
                self.debug_print("--------------")
                self.debug_print("ACK: sig is invalid.")
                return

            # Is the syn valid?
            if not self.is_valid_syn(msg[u"syn_ack"][u"syn"]):
                self.debug_print("ACK: syn is invalid.")
                return

            # Update handshake.
            contract = self.contracts[contract_id]
            self.handshake[contract_id] = u"ACK"

            # Try make TCP con.
            self.net.unl.connect(
                contract["src_unl"],
                {
                    "success": success_wrapper(
                        self,
                        contract_id,
                        contract["host_unl"]
                    )
                },
                force_master=0
            )

            print("ACK")

    def get_data_path(self, data_id):
        path = os.path.join(self.storage_path, data_id)

        return path

    def save_contract(self, contract):
        # Record contract details.
        contract_id = self.contract_id(contract)
        self.contracts[contract_id] = contract

        return contract_id

    def send_msg(self, dict_obj, unl):
        node_id = self.net.unl.deconstruct(unl)["node_id"]
        msg = json.dumps(dict_obj, ensure_ascii=True)
        self.net.dht_node.send_direct_message(
            node_id,
            msg
        )

    def contract_id(self, contract):
        if sys.version_info >= (3, 0, 0):
            contract = str(contract).encode("ascii")
        else:
            contract = str(contract)

        return hashlib.sha256(contract).hexdigest()

    def sign_contract(self, contract):
        if sys.version_info >= (3, 0, 0):
            msg = str(contract).encode("ascii")
        else:
            msg = str(contract)

        msg = binascii.hexlify(msg)
        sig = self.wallet.sign_data(self.wif, msg)

        if sys.version_info >= (3, 0, 0):
            contract[u"signature"] = sig.decode("utf-8")
        else:
            contract[u"signature"] = unicode(sig)

        return contract

    def is_valid_contract_sig(self, contract):
        sig = contract[u"signature"][:]
        del contract[u"signature"]

        if sys.version_info >= (3, 0, 0):
            msg = str(contract).encode("ascii")
        else:
            msg = str(contract)

        msg = binascii.hexlify(msg)
        address = self.wallet.get_address(self.wif)

        ret = self.wallet.verify_signature(address, sig, msg)
        contract[u"signature"] = sig[:]

        return ret

    def data_request(self, action, data_id, file_size, node_unl):
        """
        Action = put (upload), get (download.)
        """
        # Who is hosting this data?
        if action == "upload":
            # We store this data.
            host_unl = self.net.unl.value
        else:
            # They store the data.
            host_unl = node_unl
            if data_id in self.downloading:
                raise Exception("Already trying to download this.")

        # Encoding.
        if sys.version_info >= (3, 0, 0):
            if type(data_id) == bytes:
                data_id = data_id.decode("utf-8")

            if type(host_unl) == bytes:
                host_unl = host_unl.decode("utf-8")

            if type(node_unl) == bytes:
                node_unl = node_unl.decode("utf-8")
        else:
            if type(data_id) == str:
                data_id = unicode(data_id)

            if type(host_unl) == str:
                host_unl = unicode(host_unl)

            if type(node_unl) == str:
                node_unl = unicode(node_unl)

        # Create contract.
        contract = OrderedDict({
            u"status": u"SYN",
            u"data_id": data_id,
            u"file_size": file_size,
            u"host_unl": host_unl,
            u"dest_unl": node_unl,
            u"src_unl": self.net.unl.value
        })

        # Sign contract.
        contract = self.sign_contract(contract)

        # Route contract.
        contract_id = self.save_contract(contract)
        self.send_msg(contract, node_unl)

        # Update handshake.
        self.handshake[contract_id] = "SYN"

    def hash_file(self, path):
        sha256 = hashlib.sha256()
        buf_size = 1048576  # 1 MB
        with open(path, 'rb') as fp:
            while True:
                data = fp.read(buf_size)
                if not data:
                    break

                sha256.update(data)

        return sha256.hexdigest()

    def move_file_to_storage(self, path):
        file_name = self.hash_file(path)
        destination = self.get_data_path(file_name)
        if not os.path.isfile(destination):
            shutil.copyfile(path, destination)

        file_size = os.path.getsize(path)
        ret = {
            "file_size": file_size,
            "data_id": file_name
        }

        return ret

    def get_data_chunk(self, data_id, position, chunk_size=1048576):
        path = self.get_data_path(data_id)
        buf = b""
        with open(path, "rb") as fp:
            fp.seek(position, 0)
            buf = fp.read(chunk_size)

        return buf

    def save_data_chunk(self, data_id, chunk):
        path = self.get_data_path(data_id)
        with open(path, "ab") as fp:
            fp.write(chunk)

if __name__ == "__main__":
    # Alice sample node.
    alice_wallet = BtcTxStore(testnet=True, dryrun=True)
    alice = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60400,
            dht_node=pyp2p.dht_msg.DHT(),
            debug=1
        ),
        wallet=alice_wallet,
        storage_path="/home/laurence/Storj/Alice"
    )

    # ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab
    # print(alice.move_file_to_storage("/home/laurence/small_file"))

    # exit()

    # Bob sample node.
    bob_wallet = BtcTxStore(testnet=True, dryrun=True)
    bob = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60401,
            dht_node=pyp2p.dht_msg.DHT(),
            debug=1
        ),
        wallet=bob_wallet,
        storage_path="/home/laurence/Storj/Bob"
    )

    print(alice.net.unl.deconstruct())
    print(bob.net.unl.deconstruct())


    # alice.net.unl == bob.net.unl



    print(type(alice.net.unl))
    print(type(pyp2p.unl.UNL(value=bob.net.unl.value)))

    # exit()

    # Alice wants data from Bob.
    alice.data_request(
        "upload",
        "ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab",
        2631451,
        bob.net.unl.value
    )



    """
    alice.data_request(
        "upload",
        "f2ca1bb6c7e907d06dafe4687e579fce76b37e4e93b7605022da52e6ccc26fd2",
        5,
        bob.net.unl.value
    )
    """

    # Main event loop.
    while 1:
        for client in [alice, bob]:
            if client == alice:
                print("Alice")
            else:
                print("Bob")
            process_transfers(client)

        time.sleep(0.5)

