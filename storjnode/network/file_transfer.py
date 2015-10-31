from .pyp2p.net import Net
from .pyp2p.dht_msg import DHT
from .pyp2p.lib import is_ip_private
from collections import OrderedDict
import time
import json
import hashlib
import sys

class FileTransfer():
    def __init__(self, net):
        # Accept direct connections.
        self.net = net

        # Start networking.
        self.net.start()

        # Dict of data requests.
        self.contracts = {}

        # Threeway handshake status for contracts.
        self.handshake = {}

        #Associated with contracts.
        self.cons = {}

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
            self.send_msg(reply, msg["syn"]["host_unl"])
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
                    self.cons[con] = {
                        "contract_id": contract_id,
                        "associated": True
                    }

                    #Tell them what contract to associate con with.
                    con.send(contract_id, send_all=1)

                return success

            # Try make TCP con.
            contract = self.contracts[contract_id]
            self.net.unl.connect(
                contract["host_unl"],
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

    def get_data(self, data_id, node_unl):
        # Create contract.
        contract = OrderedDict({
            "status": "SYN",
            "data_id": data_id,
            "host_unl": node_unl,
            "src_unl": self.net.unl.value
        })

        #Route contract.
        contract_id = self.save_contract(contract)
        self.send_msg(contract, node_unl)

        # Update handshake.
        self.handshake[contract_id] = "SYN"

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
        )
    )

    # Bob sample node.
    bob = FileTransfer(
        Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60401,
            dht_node=DHT(),
            debug=1
        )
    )

    # Alice wants data from Bob.
    alice.get_data("data_id", bob.net.unl.value)

    def process_client(client):
       # Process contract messages.
        for msg in client.net.dht_node.get_messages():
            client.protocol(msg)

        # Process connections.
        for con in client.net:
            #This is a new connection.
            if con not in client.cons:
                client.cons[con] = {
                    "contract_id": "",
                    "associated": False
                }

            #Attempt to associate connections.
            net_con = client.cons[con]
            if not net_con["associated"]:
                print("Not associated.")

                #Combine partial contract IDs.
                contract_id_len = len(net_con["contract_id"])
                partial = con.recv(64 - contract_id_len)
                print("Partial = ")
                print(partial)

                net_con["contract_id"] += partial

                #Full ID received: check it.
                if len(net_con["contract_id"]) == 64:
                    print("Contract ID received.")
                    print(net_con["contract_id"])
                    print(list(client.contracts))

                    if net_con["contract_id"] in client.contracts:
                        print("Found contract.")

                        contract = client.contracts[net_con["contract_id"]]
                        con_addr, con_port = con.s.getpeername()
                        print(con_addr)
                        for unl in [
                            contract["src_unl"],
                            contract["host_unl"]
                        ]:
                            unl = client.net.unl.deconstruct(unl)
                            if is_ip_private(con_addr):
                                if unl["lan_ip"] == con_addr:
                                    net_con["associated"] = True
                                    print("\a")
                                    print("Con ready to receive binary data.")
                                    break
                            else:
                                if unl["wan_ip"] == con_addr:
                                    net_con["associated"] = True
                                    print("\a")
                                    print("Con ready to receive binary data.")
                                    break

            #Handle binary chunks.

    # Main event loop.
    while 1:
        for client in [alice, bob]:
            process_client(client)

        time.sleep(0.5)

