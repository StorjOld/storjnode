from .pyp2p.unl import UNL, is_valid_unl
from .pyp2p.net import Net
from .pyp2p.dht_msg import DHT
from collections import OrderedDict
from btctxstore import BtcTxStore
import time
import json
import hashlib
import sys
import os
import shutil
import binascii

class FileTransfer():
    def __init__(self, net, wallet, storage_path):
        # Accept direct connections.
        self.net = net

        # Used for signing messages.
        self.wallet = wallet
        self.wif = self.wallet.create_key()

        # Where will the data be stored?
        self.storage_path = storage_path

        # Start networking.
        self.net.start()

        # Dict of data requests.
        self.contracts = {}

        # Threeway handshake status for contracts.
        self.handshake = {}

        #Associated with contracts.
        self.con_info = {}

    def is_valid_syn(self, msg):
        # List of expected fields.
        syn_schema = (
            "status",
            "data_id",
            "file_size",
            "host_unl",
            "dest_unl",
            "src_unl",
            "signature"
        )

        # Check all fields exist.
        if not all (key in msg for key in syn_schema):
            return 0

        # Check the UNLs are valid.
        unl_tuple = ("host_unl", "dest_unl", "src_unl")
        for unl_key in unl_tuple:
            if not is_valid_unl(msg[unl_key]):
                return 0

        # Check file size.
        file_size_type = type(msg["file_size"])
        if sys.version_info >= (3,0,0):
            expr = file_size_type != int
        else:
            expr = file_size_type != int and file_size_type != long
        if expr:
            return 0

        # Are we the host?
        if self.net.unl == UNL(value=msg["host_unl"]):
            # Then check we have this file.
            path = self.get_data_path(msg["data_id"])
            if not os.path.isfile(path):
                return 0

            # Did they specify the right size?
            if os.path.getsize(path) != msg["file_size"]:
                return 0

        return 1

    def protocol(self, msg):
        msg = json.loads(msg, object_pairs_hook=OrderedDict)

        # Associate TCP con with contract.
        def success_wrapper(self, contract_id):
            def success(con):
                #Associate TCP con with contract.
                file_size = self.contracts[contract_id]["file_size"]
                self.con_info[con] = {
                    "contract_id": contract_id,
                    "remaining": file_size
                }

            return success

        # Sanity checking.
        if "status" not in msg:
            return

        # Accept data request.
        if msg["status"] == "SYN":
            # Check syn is valid.
            if not self.is_valid_syn(msg):
                return

            # Save contract.
            self.save_contract(msg)

            # Create reply.
            reply = OrderedDict({
                "status": "SYN-ACK",
                "syn": msg,
            })

            # Sign reply.
            reply = self.sign_contract(reply)

            # Save reply.
            self.send_msg(reply, msg["src_unl"])
            print("SYN")

        # Confirm accept and make connection if needed.
        if msg["status"] == "SYN-ACK":
            # Valid syn-ack?
            if "syn" not in msg:
                return

            # Is this a reply to our SYN?
            contract_id = self.contract_id(msg["syn"])
            if contract_id not in self.contracts:
                return

            # Check syn is valid.
            if not self.is_valid_syn(msg["syn"]):
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg["syn"]):
                return

            # Update handshake.
            contract = self.contracts[contract_id]
            self.handshake[contract_id] = "SYN-ACK"

            # Create reply contract.
            reply = OrderedDict({
                "status": "ACK",
                "syn_ack": msg
            })

            # Sign reply.
            reply = self.sign_contract(reply)

            # Try make TCP con.
            self.net.unl.connect(
                contract["dest_unl"],
                {
                    "success": success_wrapper(self, contract_id)
                },
                force_master=0
            )

            # Send reply.
            self.send_msg(reply, msg["syn"]["dest_unl"])
            print("SYN-ACK")

        if msg["status"] == "ACK":
            # Valid ack.
            if "syn_ack" not in msg:
                return
            if "syn" not in msg["syn_ack"]:
                return

            # Is this a reply to our SYN-ACK?
            contract_id = self.contract_id(msg["syn_ack"]["syn"])
            if contract_id not in self.contracts:
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg["syn_ack"]):
                return

            # Is the syn valid?
            if not self.is_valid_syn(msg["syn_ack"]["syn"]):
                return

            # Update handshake.
            contract = self.contracts[contract_id]
            self.handshake[contract_id] = "ACK"

            # Try make TCP con.
            self.net.unl.connect(
                contract["src_unl"],
                {
                    "success": success_wrapper(self, contract_id)
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
        self.net.dht_node.send_message(
            node_id,
            msg
        )

    def contract_id(self, contract):
        if sys.version_info >= (3,0,0):
            contract = str(contract).encode("ascii")
        else:
            contract = str(contract)

        return hashlib.sha256(contract).hexdigest()

    def sign_contract(self, contract):
        if sys.version_info >= (3,0,0):
            msg = str(contract).encode("ascii")
        else:
            msg = str(contract)

        msg = binascii.hexlify(msg)
        sig = self.wallet.sign_data(self.wif, msg)

        if sys.version_info >= (3,0,0):
            contract["signature"] = sig.decode("utf-8")
        else:
            contract["signature"] = unicode(sig)

        return contract

    def is_valid_contract_sig(self, contract):
        sig = contract["signature"][:]
        del contract["signature"]

        if sys.version_info >= (3,0,0):
            msg = str(contract).encode("ascii")
        else:
            msg = str(contract)

        msg = binascii.hexlify(msg)
        address = self.wallet.get_address(self.wif)

        ret = self.wallet.verify_signature(address, sig, msg)
        contract["signature"] = sig[:]

        return ret

    def data_request(self, action, data_id, file_size, node_unl):
        """
        Action = put (upload), get (download.)
        """
        #Who is hosting this data?
        if action == "upload":
            #We store this data.
            host_unl = self.net.unl.value
        else:
            #They store the data.
            host_unl = node_unl

        # Create contract.
        contract = OrderedDict({
            "status": "SYN",
            "data_id": data_id,
            "file_size": file_size,
            "host_unl": host_unl,
            "dest_unl": node_unl,
            "src_unl": self.net.unl.value
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
        buf_size = 1048576 #1 MB
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
        shutil.copyfile(path, destination)

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
        Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60400,
            dht_node=DHT(),
            debug=1
        ),
        wallet=alice_wallet,
        storage_path="/home/laurence/Storj/Alice"
    )

    # ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab
    # alice.move_file_to_storage("/home/laurence/Firefox_wallpaper.png")

    # Bob sample node.
    bob_wallet = BtcTxStore(testnet=True, dryrun=True)
    bob = FileTransfer(
        Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60401,
            dht_node=DHT(),
            debug=1
        ),
        wallet=bob_wallet,
        storage_path="/home/laurence/Storj/Bob"
    )

    print(alice.net.unl.deconstruct())
    print(bob.net.unl.deconstruct())

    # Alice wants data from Bob.
    alice.data_request(
        "download",
        "ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab",
        2631451,
        bob.net.unl.value
    )

    def process_transfers(client):
       # Process contract messages.
        for msg in client.net.dht_node.get_messages():
            client.protocol(msg)

        # Process connections.
        for con in client.net:
            print("In con.")

            # This is a new connection.
            if con not in client.con_info:
                continue

            #Anything left to do?
            con_info = client.con_info[con]
            if not con_info["remaining"]:
                continue

            #Upload.
            contract = client.contracts[con_info["contract_id"]]
            if client.net.unl == UNL(value=contract["host_unl"]):
                print("Uploading: Found our UNL")

                #Get next chunk from file.
                position = contract["file_size"] - con_info["remaining"]
                data_chunk = client.get_data_chunk(
                    contract["data_id"],
                    position
                )

                #Upload chunk binary to socket.
                bytes_sent = con.send(data_chunk)
                print(bytes_sent)
                if bytes_sent:
                    con_info["remaining"] -= bytes_sent
            else:
                print("Attempting to download.")

                #Download.
                data = con.recv(
                    con_info["remaining"],
                    encoding="ascii"
                )
                print(con.connected)
                if len(data):
                    con_info["remaining"] -= len(data)
                    client.save_data_chunk(contract["data_id"], data)

                #When done downloading close con.
                if not con_info["remaining"]:
                    con.close()

    # Main event loop.
    while 1:
        for client in [alice, bob]:
            if client == alice:
                print("Alice")
            else:
                print("Bob")
            process_transfers(client)

        time.sleep(0.5)

