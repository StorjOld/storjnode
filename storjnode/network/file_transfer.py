"""
Issues:
    * Delete con_info and con_transfers when con is closed
    * Should contract also be deleted when its transfered? Prob
    * To do: add a clean up routine based on old cons

    * If you do a session with this and transfer a series of files down the con,
      finish, close your side. Then reconnect and start a new session you can
      succeed with upload (but then not download.) The temp work around is to
      close old connections but at some point the underlying issue as to why
      connection reuse doesnt work should be investigated.
    * Another work around would be to change the code that identifies duplicate
      connections in URL and change it based on source:IP instead of
      just IP .. that would probably be a better solution
"""

import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
import logging
import storjnode.storage as storage
from collections import OrderedDict
from btctxstore import BtcTxStore
import tempfile
import time
import json
import hashlib
import sys
import os
import binascii
from threading import Lock


mutex = Lock()

DEBUG_MODE = 1
def debug_print(msg):
    if DEBUG_MODE:
        print(msg)


def process_transfers(client):
    debug_print("In process transfers")

    # Process contract messages.
    try:
        if client.net.dht_node.has_messages():
            for msg in client.net.dht_node.get_messages():
                debug_print("Processing: " + msg["message"])
                client.protocol(msg["message"])
    except Exception as e:
        debug_print(e)
        pass

    # Process new connections.
    client.net.synchronize()

    # Process connections.
    for con in client.net:
        debug_print("In con.")

        # This is an new (or old) connection.
        if con not in client.con_info:
            debug_print("Con not in con_info")
            continue

        # Wait until there's new transfers to process.
        if not client.is_queued(con):
            # Socket has hung ungracefully.
            duration = time.time() - con.alive
            if duration >= 60.0:
                debug_print("Ungraceful socket close")
                con.close()
                break

            debug_print("Not queued: skipping")
            continue

        # Get active contract ID.
        if con not in client.con_transfer:
            debug_print("Con not in con_Transfer")
            continue

        contract_id = client.con_transfer[con]
        debug_print("Contract id =")
        debug_print(contract_id)
        if len(contract_id) < 64:
            remaining = 64 - len(contract_id)
            debug_print("Blocking = " + str(con.blocking))
            partial = con.recv(remaining)
            debug_print("Contract id chunk = " + partial)
            debug_print("Connected = " + str(con.connected))
            if not len(partial):
                debug_print("Did not receive contract id")
                continue

            client.con_transfer[con] += partial
            debug_print("Skipping contract id.")
            continue

        # Reached end of transfer queue.
        if contract_id == u"0" * 64:
            debug_print("Skippng end of queue")
            continue

        # Anything left to do?
        if contract_id not in client.con_info[con]:
            continue
        con_info = client.con_info[con][contract_id]
        if not con_info["remaining"]:
            debug_print("Skipping remaining.")
            continue

        # Upload.
        contract = client.contracts[contract_id]
        transfer_complete = 0
        if client.net.unl == pyp2p.unl.UNL(value=contract["host_unl"]):
            debug_print("Uploading: Found our UNL")

            # Get next chunk from file.
            position = contract["file_size"] - con_info["remaining"]
            data_chunk = client.get_data_chunk(
                contract["data_id"],
                position
            )

            # Upload chunk binary to socket.
            bytes_sent = con.send(data_chunk)
            debug_print(bytes_sent)
            if bytes_sent:
                con_info["remaining"] -= bytes_sent

            debug_print("Remaining = ")
            debug_print(con_info["remaining"])

            # Everything uploaded.
            if not con_info["remaining"]:
                transfer_complete = 1
        else:
            debug_print("Attempting to download.")

            # Download.
            data = con.recv(
                con_info["remaining"],
                encoding="ascii"
            )
            debug_print(con.connected)

            if len(data):
                con_info["remaining"] -= len(data)
                client.save_data_chunk(contract["data_id"], data)

            debug_print("Remaining = ")
            debug_print(con_info["remaining"])

            # When done downloading close con.
            if not con_info["remaining"]:
                # Check download.
                data_id = contract["data_id"]
                temp_path = client.downloading[data_id]
                with open(temp_path, "rw") as shard:
                    # Delete file if it doesn't hash right!
                    found_hash = storage.shard.get_id(shard)
                    if found_hash != data_id:
                        debug_print(found_hash)
                        debug_print(data_id)
                        debug_print("Error: downloaded file doesn't hash right!")
                        os.remove(temp_path)
                        continue

                    # Move shard to storage.
                    storage.manager.add(
                        client.store_config,
                        shard
                    )

                # Remove that we're downloading this.
                del client.downloading[data_id]

                # Ready for a new transfer (if there are any.)
                transfer_complete = 1

        their_unl = client.get_their_unl(contract)
        is_master = client.net.unl.is_master(their_unl)
        debug_print("Is master = " + str(is_master))
        if transfer_complete:
            if is_master:
                client.queue_next_transfer(con)
            else:
                client.con_transfer[con] = u""


class FileTransfer:
    def __init__(self, net, wif=None, store_config=None):
        # Accept direct connections.
        self.net = net

        # Used for signing messages.
        self.wallet = BtcTxStore(testnet=True, dryrun=True)
        self.wif = wif or self.wallet.create_key()

        # Where will the data be stored?
        self.store_config = store_config
        assert(len(list(store_config)))

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

    def get_their_unl(self, contract):
        if self.net.unl == pyp2p.unl.UNL(value=contract["dest_unl"]):
            their_unl = contract["src_unl"]
        else:
            their_unl = contract["dest_unl"]

        return their_unl

    def is_queued(self, con=None):
        if con is not None:
            if con not in self.con_info:
                return 0

        if con is None:
            con_list = list(self.con_info)
        else:
            con_list = [con]

        for con in con_list:
            for contract_id in list(self.con_info[con]):
                con_info = self.con_info[con][contract_id]
                if con_info["remaining"]:
                    return 1

        return 0

    def cleanup_transfers(self, con):
        # Close con - there's nothing left to download.
        if not self.is_queued(con):
            # Cleanup con transfers.
            if con in self.con_transfer:
                del self.con_transfer[con]

            # Cleanup con_info.
            if con in self.con_info:
                del self.con_info[con]

            # Todo: cleanup contract + handshake state.

    def queue_next_transfer(self, con):
        debug_print("Queing next transfer")
        for contract_id in list(self.con_info[con]):
            con_info = self.con_info[con][contract_id]
            if con_info["remaining"]:
                self.con_transfer[con] = contract_id
                con.send(contract_id, send_all=1)
                return

        # Mark end of transfers.
        self.con_transfer[con] = u"0" * 64

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
            debug_print("Missing required key.")
            return 0

        # Check the UNLs are valid.
        unl_tuple = (u"host_unl", u"dest_unl", u"src_unl")
        for unl_key in unl_tuple:
            if not pyp2p.unl.is_valid_unl(msg[unl_key]):
                debug_print("Invalid UNL for " + unl_key)
                debug_print(msg[unl_key])
                return 0

        # Check file size.
        file_size_type = type(msg[u"file_size"])
        if sys.version_info >= (3, 0, 0):
            expr = file_size_type != int
        else:
            expr = file_size_type != int and file_size_type != long
        if expr:
            debug_print("File size validation failed")
            debug_print(type(msg[u"file_size"]))
            return 0

        # Are we the host?
        if self.net.unl == pyp2p.unl.UNL(value=msg[u"host_unl"]):
            # Then check we have this file.
            path = storage.manager.find(self.store_config,
                                                  msg[u"data_id"])
            if path is None:
                debug_print("Failed to find file we're uploading")
                return 0

            # Did they specify the right size?
            if os.path.getsize(path) != msg[u"file_size"]:
                debug_print("Client did not specify correct file siz.e")
                return 0
        else:
            # Do we already have this file?
            path = storage.manager.find(self.store_config,
                                                  msg[u"data_id"])
            if path is not None:
                debug_print("Attempting to download file we already have")
                return 0

            # Are we already trying to download this?
            if msg[u"data_id"] in self.downloading:
                debug_print("We're already trying to download this")
                return 0

        return 1

    def protocol(self, msg):
        msg = json.loads(msg, object_pairs_hook=OrderedDict)

        # Associate TCP con with contract.
        def success_wrapper(self, contract_id, host_unl):
            def success(con):
                mutex.acquire()
                debug_print("IN SUCCESS CALLBACK")
                debug_print("Success() contract_id = " + str(contract_id))

                # Associate TCP con with contract.
                contract = self.contracts[contract_id]
                file_size = contract["file_size"]

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
                data_id = contract["data_id"]
                if self.net.unl != pyp2p.unl.UNL(value=host_unl):
                    debug_print("Success: download")
                    fp, self.downloading[data_id] = tempfile.mkstemp()
                else:
                    # Set initial upload for this con.
                    debug_print("Success: upload")

                # Queue first transfer.
                their_unl = self.get_their_unl(contract)
                is_master = self.net.unl.is_master(their_unl)
                debug_print("Is master = " + str(is_master))
                if con not in self.con_transfer:
                    if is_master:
                        # A transfer to queue processing.
                        self.queue_next_transfer(con)
                    else:
                        # A transfer to receive (unknown.)
                        self.con_transfer[con] = u""
                else:
                    if self.con_transfer[con] == u"0" * 64:
                        if is_master:
                            self.queue_next_transfer(con)
                        else:
                            self.con_transfer[con] = u""

                mutex.release()

            return success

        # Sanity checking.
        if u"status" not in msg:
            return

        # Accept data request.
        if msg[u"status"] == u"SYN":
            # Check syn is valid.
            if not self.is_valid_syn(msg):
                debug_print("SYN: invalid syn.")
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
            debug_print("SYN")

        # Confirm accept and make connection if needed.
        if msg[u"status"] == u"SYN-ACK":
            # Valid syn-ack?
            if u"syn" not in msg:
                debug_print("SYN-ACK: syn not in msg.")
                return

            # Is this a reply to our SYN?
            contract_id = self.contract_id(msg[u"syn"])
            if contract_id not in self.contracts:
                debug_print("--------------")
                debug_print(msg)
                debug_print("--------------")
                debug_print(self.contracts)
                debug_print("--------------")
                debug_print("SYN-ACK: contract not found.")
                return

            # Check syn is valid.
            if not self.is_valid_syn(msg[u"syn"]):
                debug_print("SYN-ACK: invalid syn.")
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg[u"syn"]):
                debug_print("SYN-ACK: sig is invalid.")
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
                force_master=0,
                nonce=contract_id
            )

            # Send reply.
            self.send_msg(reply, msg[u"syn"][u"dest_unl"])
            debug_print("SYN-ACK")

        if msg[u"status"] == u"ACK":
            # Valid ack.
            if u"syn_ack" not in msg:
                debug_print("ACK: syn_ack not in msg.")
                return
            if u"syn" not in msg[u"syn_ack"]:
                debug_print("ACK: syn not in msg.")
                return

            # Is this a reply to our SYN-ACK?
            contract_id = self.contract_id(msg[u"syn_ack"][u"syn"])
            if contract_id not in self.contracts:
                debug_print("ACK: contract not found.")
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg[u"syn_ack"]):
                debug_print("--------------")
                debug_print(msg)
                debug_print("--------------")
                debug_print(self.contracts)
                debug_print("--------------")
                debug_print("ACK: sig is invalid.")
                return

            # Is the syn valid?
            if not self.is_valid_syn(msg[u"syn_ack"][u"syn"]):
                debug_print("ACK: syn is invalid.")
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
                force_master=0,
                nonce=contract_id
            )

            debug_print("ACK")

    def save_contract(self, contract):
        # Record contract details.
        contract_id = self.contract_id(contract)
        self.contracts[contract_id] = contract

        return contract_id

    def send_msg(self, dict_obj, unl):
        node_id = self.net.unl.deconstruct(unl)["node_id"]
        msg = json.dumps(dict_obj, ensure_ascii=True)
        self.net.dht_node.direct_message(
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

        msg = binascii.hexlify(msg).decode("utf-8")
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

        msg = binascii.hexlify(msg).decode("utf-8")
        address = self.wallet.get_address(self.wif)

        ret = self.wallet.verify_signature(address, sig, msg)
        contract[u"signature"] = sig[:]

        return ret

    def data_request(self, action, data_id, file_size, node_unl):
        """
        Action = put (upload), get (download.)
        """
        print("In data request function")

        # Who is hosting this data?
        if action == "upload":
            # We store this data.
            host_unl = self.net.unl.value
            assert(storage.manager.find(self.store_config, data_id) != None)
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
        print("Sending data request")

        # Update handshake.
        self.handshake[contract_id] = "SYN"

    def remove_file_from_storage(self, data_id):
        storage.manager.remove(self.store_config, data_id)

    def move_file_to_storage(self, path):
        with open(path, "rb") as shard:
            storage.manager.add(self.store_config, shard)
            return {
                "file_size": storage.shard.get_size(shard),
                "data_id": storage.shard.get_id(shard)
            }

    def get_data_chunk(self, data_id, position, chunk_size=1048576):
        path = storage.manager.find(self.store_config, data_id)
        buf = b""
        with open(path, "rb") as fp:
            fp.seek(position, 0)
            buf = fp.read(chunk_size)

            return buf

    def save_data_chunk(self, data_id, chunk):
        debug_print("Saving data chunk for " + str(data_id))
        debug_print("of size + " + str(len(chunk)))
        assert(data_id in self.downloading)

        # Find temp file path.
        path = self.downloading[data_id]

        print(path)
        with open(path, "ab") as fp:
            fp.write(chunk)

if __name__ == "__main__":


    #store_config = { "/home/laurence/Storj/Alice": None }
    #print(storage.manager.find(store_config, "ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab"))

    #exit()

    # Alice sample node.
    alice_wallet = BtcTxStore(testnet=True, dryrun=True)
    alice = FileTransfer(
        pyp2p.net.Net(
            net_type="direct",
            node_type="passive",
            nat_type="preserving",
            passive_port=60400,
            dht_node=pyp2p.dht_msg.DHT(),
        ),
        wif=alice_wallet.create_key(),
        store_config = { "/home/laurence/Storj/Alice": None }  # FIXME use temppath
    )

    print(alice.net.unl.deconstruct("ATRuSlZJWFQ1QjBRVWFrakJYOTQ5c2dtRcU4OEZziAGowPm3RVYAAAAA7UbbEs1238g="))

    exit()

    # ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab
    # print(debug_print(alice.move_file_to_storage("/home/laurence/Firefox_wallpaper.png")))

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
        ),
        wif=bob_wallet.create_key(),
        store_config = { "/home/laurence/Storj/Bob": None }  # FIXME use temppath
    )

    debug_print(alice.net.unl.deconstruct())
    debug_print(bob.net.unl.deconstruct())


    # alice.net.unl == bob.net.unl



    debug_print(type(alice.net.unl))
    debug_print(type(pyp2p.unl.UNL(value=bob.net.unl.value)))

    # exit()

    # Alice wants data from Bob.
    alice.data_request(
        "download",
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
                debug_print("Alice")
            else:
                debug_print("Bob")
            process_transfers(client)

        time.sleep(0.002)

