from .pyp2p.unl import UNL
from .pyp2p.net import Net
from .pyp2p.dht_msg import DHT
from .pyp2p.lib import is_ip_private
from collections import OrderedDict
import time
import json
import hashlib
import sys
import os
import shutil

class FileTransfer():
    def __init__(self, net, storage_path):
        # Accept direct connections.
        self.net = net

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

    def protocol(self, msg):
        msg = json.loads(msg, object_pairs_hook=OrderedDict)

        # Accept data request.
        if msg["status"] == "SYN":
            # Save contract.
            self.save_contract(msg)

            # Create reply.
            reply = OrderedDict({
                "status": "SYN-ACK",
                "syn": msg,
            })

            # Save reply.
            self.send_msg(reply, msg["src_unl"])
            print("SYN")

        # Confirm accept and make connection if needed.
        if msg["status"] == "SYN-ACK":
            # Is this a reply to our SYN?
            # Todo: if we signed it check.
            contract_id = self.contract_id(msg["syn"])
            if contract_id not in self.contracts:
                return

            # Update handshake.
            self.handshake[contract_id] = "SYN-ACK"

            # Create reply contract.
            reply = OrderedDict({
                "status": "ACK",
                "syn_ack": msg
            })

            # Send reply.
            self.send_msg(reply, msg["syn"]["dest_unl"])
            print("SYN-ACK")

        if msg["status"] == "ACK":
            # Is this a reply to our SYN-ACK?
            # Todo: if we signed it check.
            contract_id = self.contract_id(msg["syn_ack"]["syn"])
            if contract_id not in self.contracts:
                return

            # Update handshake.
            self.handshake[contract_id] = "ACK"

            # Associate TCP con with contract.
            def success_wrapper():
                def success(con):
                    #Associate TCP con with contract.
                    file_size = self.contracts[contract_id]["file_size"]
                    self.con_info[con] = {
                        "contract_id": contract_id,
                        "associated": True,
                        "remaining": file_size
                    }

                    #Tell them what contract to associate con with.
                    con.send(contract_id, send_all=1)

                return success

            # Try make TCP con.
            contract = self.contracts[contract_id]
            self.net.unl.connect(
                contract["src_unl"],
                {
                    "success": success_wrapper()
                }
            )

            print("ACK")

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

    def recv_contract_id(self, con):
        """
        Buffer contract ID. When received: connection is reading to send/recv binary data.
        """

        #Combine partial contract IDs.
        con_info = self.con_info[con]
        contract_id_len = len(con_info["contract_id"])
        partial = con.recv(64 - contract_id_len)
        print("Partial = ")
        print(partial)
        con_info["contract_id"] += partial

        #Full ID received: check it.
        if len(con_info["contract_id"]) == 64:
            print("Contract ID received.")
            print(con_info["contract_id"])
            print(list(self.contracts))

            if con_info["contract_id"] in self.contracts:
                print("Found contract.")
                contract = self.contracts[con_info["contract_id"]]
                con_addr, con_port = con.s.getpeername()
                print(con_addr)
                for unl in [contract["src_unl"], contract["dest_unl"]]:
                    unl = self.net.unl.deconstruct(unl)
                    if is_ip_private(con_addr):
                        if unl["lan_ip"] == con_addr:
                            con_info["associated"] = True
                            con_info["remaining"] = contract["file_size"]
                            print("\a")
                            print("Con ready to receive binary data.")
                            break
                    else:
                        if unl["wan_ip"] == con_addr:
                            con_info["associated"] = True
                            con_info["remaining"] = contract["file_size"]
                            print("\a")
                            print("Con ready to receive binary data.")
                            break

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

        #Route contract.
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
        destination = os.path.join(self.storage_path, file_name)
        shutil.copyfile(path, destination)

    def get_data_chunk(self, data_id, position, chunk_size=1048576):
        path = os.path.join(self.storage_path, data_id)
        buf = b""
        with open(path, "rb") as fp:
            fp.seek(position, 0)
            buf = fp.read(chunk_size)

        return buf

    def save_data_chunk(self, data_id, chunk):
        path = os.path.join(self.storage_path, data_id)
        with open(path, "ab") as fp:
            fp.write(chunk)

if __name__ == "__main__":
    # Alice sample node.
    alice = FileTransfer(
        Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60400,
            dht_node=DHT(),
            debug=1
        ),
        storage_path="/home/laurence/Storj/Alice"
    )

    # ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab
    # alice.move_file_to_storage("/home/laurence/Firefox_wallpaper.png")

    # Bob sample node.
    bob = FileTransfer(
        Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60401,
            dht_node=DHT(),
            debug=1
        ),
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
                client.con_info[con] = {
                    "contract_id": "",
                    "associated": False,
                    "remaining": 0
                }

            # Attempt to associate connection with contract.
            con_info = client.con_info[con]
            if not con_info["associated"]:
                client.recv_contract_id(con)

            # Handle binary chunks.
            print(con_info)
            if con_info["associated"]:
                #Anything left to do?
                if not con_info["remaining"]:
                    continue

                #Upload.
                contract = client.contracts[con_info["contract_id"]]
                print(client.net.unl.deconstruct())
                if client.net.unl == UNL(value=contract["host_unl"]):
                    print("Found our UNL")

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

