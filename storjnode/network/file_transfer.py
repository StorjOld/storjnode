"""
Issues:
    * Delete con_info and con_transfers when con is closed
    * Should contract also be deleted when its transfered? Prob
    * To do: add a clean up routine based on old cons

    Todo: implement RST for -- will probably need to look at  transfer_request_handlers
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
import struct
from threading import Lock
from twisted.internet import defer


mutex = Lock()

_log = logging.getLogger(__name__)

class RequestDenied(Exception):
    pass

class TransferError(Exception):
    pass

def process_transfers(client):
    _log.debug("In process transfers")

    # Process contract messages.
    try:
        if client.net.dht_node.has_messages():
            for msg in client.net.dht_node.get_messages():
                _log.debug("Processing: " + msg["message"])
                client.protocol(msg["message"])
    except Exception as e:
        _log.debug(e)
        pass

    # Process new connections.
    client.net.synchronize()

    # Raise appropriate async callbacks for errors.
    for con in list(client.con_info):
        if not con.connected:
            # Broken connections.
            for contract_id in list(client.con_info[con]):
                if contract_id in client.defers:
                    e = TransferError("Connection died.")
                    client.defers[contract_id].errback(e)
                    del client.defers[contract_id]

                    if contract_id in client.contracts:
                        del client.contracts[contract_id]

    # Expired handshakes.
    for contract_id in list(client.contracts):
        if contract_id in client.handshake:
            handshake = client.handshake[contract_id]
            elapsed = time.time() - handshake["timestamp"]
            if elapsed >= 30:
                if contract_id in client.defers:
                    e = RequestDenied("Handshake timed out.")
                    client.defers[contract_id].errback(e)
                    del client.defers[contract_id]



    # Todo: cleanup con info and other structures.

    # Process connections.
    for con in client.net:
        _log.debug("In con.")

        # This is an new (or old) connection.
        if con not in client.con_info:
            _log.debug("Con not in con_info")
            continue

        # Connection is not synchronized yet.
        if con.nonce == None:
            _log.debug("Not synced yet")
            continue

        # Wait until there's new transfers to process.
        if not client.is_queued(con):
            # Socket has hung ungracefully.
            duration = time.time() - con.alive
            if duration >= 15.0:
                _log.debug("Ungraceful socket close")
                con.close()
                break

            _log.debug("Not queued: skipping")
            continue

        # Get active contract ID.
        if con not in client.con_transfer:
            _log.debug("Con not in con_Transfer")
            continue

        contract_id = client.con_transfer[con]
        _log.debug("Contract id =")
        _log.debug(contract_id)
        if len(contract_id) < 64:
            remaining = 64 - len(contract_id)
            _log.debug("Blocking = " + str(con.blocking))
            partial = con.recv(remaining)
            _log.debug("Contract id chunk = " + partial)
            _log.debug("Connected = " + str(con.connected))
            if not len(partial):
                _log.debug("Did not receive contract id")
                continue

            client.con_transfer[con] += partial
            _log.debug("Skipping contract id.")
            continue

        # Reached end of transfer queue.
        if contract_id == u"0" * 64:
            _log.debug("Skippng end of queue")
            continue

        # Anything left to do?
        if contract_id not in client.con_info[con]:
            continue
        con_info = client.con_info[con][contract_id]
        if not con_info["remaining"]:
            _log.debug("Skipping remaining.")
            continue

        # Upload.
        contract = client.contracts[contract_id]
        transfer_complete = 0
        if client.net.unl == pyp2p.unl.UNL(value=contract["host_unl"]):
            _log.debug("Uploading: Found our UNL")

            # Send file size.
            if not con_info["file_size"]:
                # Get file size.
                path = storage.manager.find(
                    client.store_config,
                    contract["data_id"]
                )
                file_size = os.path.getsize(path)
                con_info["file_size"] = file_size
                con_info["remaining"] = file_size

                # Marshal file size for network.
                if sys.version_info >= (3, 0, 0):
                    net_file_size = struct.pack(
                        "<20s",
                        str(file_size).encode("ascii")
                    )
                else:
                    net_file_size = struct.pack(
                        "<20s",
                        str(file_size)
                    )

                # Send file size.
                con.send(net_file_size, send_all=1)


            # Get next chunk from file.
            position = con_info["file_size"] - con_info["remaining"]
            data_chunk = client.get_data_chunk(
                contract["data_id"],
                position
            )

            # Upload chunk binary to socket.
            bytes_sent = con.send(data_chunk)
            _log.debug(bytes_sent)
            if bytes_sent:
                con_info["remaining"] -= bytes_sent

            _log.debug("Remaining = ")
            _log.debug(con_info["remaining"])

            # Everything uploaded.
            if not con_info["remaining"]:
                transfer_complete = 1
        else:
            _log.debug("Attempting to download.")

            # Get file size.
            if not con_info["file_size"]:
                file_size_buf = con_info["file_size_buf"]
                if len(file_size_buf) < 20:
                    remaining = 20 - len(file_size_buf)
                    partial = con.recv(remaining)
                    if not len(partial):
                        continue

                    file_size_buf += partial
                    if len(file_size_buf) == 20:
                        file_size, = struct.unpack("<20s", file_size_buf)
                        file_size = int(file_size_buf.rstrip(b"\0"))
                        con_info["file_size"] = file_size
                        con_info["remaining"] = file_size
                    else:
                        continue

            # Download.
            data = con.recv(
                con_info["remaining"],
                encoding="ascii"
            )
            _log.debug(con.connected)

            if len(data):
                con_info["remaining"] -= len(data)
                client.save_data_chunk(contract["data_id"], data)

            _log.debug("Remaining = ")
            _log.debug(con_info["remaining"])

            # When done downloading close con.
            if not con_info["remaining"]:
                # Check download.
                data_id = contract["data_id"]
                temp_path = client.downloading[data_id]
                with open(temp_path, "rw") as shard:
                    # Delete file if it doesn't hash right!
                    found_hash = storage.shard.get_id(shard)
                    if found_hash != data_id:
                        _log.debug(found_hash)
                        _log.debug(data_id)
                        _log.debug("Error: downloaded file doesn't hash right!")
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
        _log.debug("Is master = " + str(is_master))
        if transfer_complete:
            # Return async success.
            if contract_id in client.defers:
                # Call any callbacks registered with this defer.
                client.defers[contract_id].callback(client.success_value)
                del client.defers[contract_id]

            if is_master:
                client.queue_next_transfer(con)
            else:
                client.con_transfer[con] = u""


class FileTransfer:
    def __init__(self, net, wif=None, store_config=None, handlers=None):
        # Accept direct connections.
        self.net = net

        # Returned by callbacks.
        self.success_value = ("127.0.0.1", 7777)

        # Used for signing messages.
        self.wallet = BtcTxStore(testnet=True, dryrun=True)
        self.wif = wif or self.wallet.create_key()

        # Where will the data be stored?
        self.store_config = store_config
        assert(len(list(store_config)))

        # Handlers for certain events.
        self.handlers = handlers

        # Start networking.
        if not self.net.is_net_started:
            self.net.start()

        # Dict of data requests.
        self.contracts = {}

        # Dict of defers for contracts.
        self.defers = {}

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
        _log.debug("Queing next transfer")
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
            u"direction",
            u"data_id",
            u"file_size",
            u"host_unl",
            u"dest_unl",
            u"src_unl",
            u"signature"
        )

        # Check all fields exist.
        if not all(key in msg for key in syn_schema):
            _log.debug("Missing required key.")
            return 0

        # Check SYN size.
        if len(msg) > 5242880: # 5 MB.
            _log.debug("SYN is too big")
            return 0

        # Check direction is valid.
        direction_tuple = (u"send", u"receive")
        if msg[u"direction"] not in direction_tuple:
            _log.debug("Missing required direction tuple.")
            return 0

        # Check the UNLs are valid.
        unl_tuple = (u"host_unl", u"dest_unl", u"src_unl")
        for unl_key in unl_tuple:
            if not pyp2p.unl.is_valid_unl(msg[unl_key]):
                _log.debug("Invalid UNL for " + unl_key)
                _log.debug(msg[unl_key])
                return 0

        # Check file size.
        file_size_type = type(msg[u"file_size"])
        if sys.version_info >= (3, 0, 0):
            expr = file_size_type != int
        else:
            expr = file_size_type != int and file_size_type != long
        if expr:
            _log.debug("File size validation failed")
            _log.debug(type(msg[u"file_size"]))
            return 0

        # Are we the host?
        if self.net.unl == pyp2p.unl.UNL(value=msg[u"host_unl"]):
            # Then check we have this file.
            path = storage.manager.find(self.store_config, msg[u"data_id"])
            if path is None:
                _log.debug("Failed to find file we're uploading")
                return 0
        else:
            # Do we already have this file?
            path = storage.manager.find(self.store_config, msg[u"data_id"])
            if path is not None:
                _log.debug("Attempting to download file we already have")
                return 0

            # Are we already trying to download this?
            if msg[u"data_id"] in self.downloading:
                _log.debug("We're already trying to download this")
                return 0

        return 1

    def protocol(self, msg):
        msg = json.loads(msg, object_pairs_hook=OrderedDict)

        # Associate TCP con with contract.
        def success_wrapper(self, contract_id, host_unl):
            def success(con):
                with mutex:
                    _log.debug("IN SUCCESS CALLBACK")
                    _log.debug("Success() contract_id = " + str(contract_id))

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
                            "remaining": 350, # Tree fiddy.
                            "file_size": file_size,
                            "file_size_buf": b""
                        }

                    # Record download state.
                    data_id = contract["data_id"]
                    if self.net.unl != pyp2p.unl.UNL(value=host_unl):
                        _log.debug("Success: download")
                        fp, self.downloading[data_id] = tempfile.mkstemp()
                    else:
                        # Set initial upload for this con.
                        _log.debug("Success: upload")

                    # Queue first transfer.
                    their_unl = self.get_their_unl(contract)
                    is_master = self.net.unl.is_master(their_unl)
                    _log.debug("Is master = " + str(is_master))
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
            return success

        # Sanity checking.
        if u"status" not in msg:
            return

        # Accept data request.
        if msg[u"status"] == u"SYN":
            # Check syn is valid.
            if not self.is_valid_syn(msg):
                _log.debug("SYN: invalid syn.")
                return

            # Save contract.
            contract_id = self.contract_id(msg)
            self.save_contract(msg)
            self.handshake[contract_id] = {
                "state": u"SYN-ACK",
                "timestamp": time.time()
            }

            # Create reply.
            reply = OrderedDict({
                u"status": u"SYN-ACK",
                u"syn": msg,
            })

            # Sign reply.
            reply = self.sign_contract(reply)

            # Save reply.
            self.send_msg(reply, msg[u"src_unl"])
            _log.debug("SYN")

        # Confirm accept and make connection if needed.
        if msg[u"status"] == u"SYN-ACK":
            # Valid syn-ack?
            if u"syn" not in msg:
                _log.debug("SYN-ACK: syn not in msg.")
                return

            # Is this a reply to our SYN?
            contract_id = self.contract_id(msg[u"syn"])
            if contract_id not in self.contracts:
                _log.debug("--------------")
                _log.debug(msg)
                _log.debug("--------------")
                _log.debug(self.contracts)
                _log.debug("--------------")
                _log.debug("SYN-ACK: contract not found.")
                return

            # Check syn is valid.
            if not self.is_valid_syn(msg[u"syn"]):
                _log.debug("SYN-ACK: invalid syn.")
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg[u"syn"]):
                _log.debug("SYN-ACK: sig is invalid.")
                return

            # Update handshake.
            contract = self.contracts[contract_id]
            self.handshake[contract_id] = {
                "state": u"ACK",
                "timestamp": time.time()
            }

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
            _log.debug("SYN-ACK")

        if msg[u"status"] == u"ACK":
            # Valid ack.
            if u"syn_ack" not in msg:
                _log.debug("ACK: syn_ack not in msg.")
                return
            if u"syn" not in msg[u"syn_ack"]:
                _log.debug("ACK: syn not in msg.")
                return

            # Is this a reply to our SYN-ACK?
            contract_id = self.contract_id(msg[u"syn_ack"][u"syn"])
            if contract_id not in self.contracts:
                _log.debug("ACK: contract not found.")
                return

            # Did I sign this?
            if not self.is_valid_contract_sig(msg[u"syn_ack"]):
                _log.debug("--------------")
                _log.debug(msg)
                _log.debug("--------------")
                _log.debug(self.contracts)
                _log.debug("--------------")
                _log.debug("ACK: sig is invalid.")
                return

            # Is the syn valid?
            if not self.is_valid_syn(msg[u"syn_ack"][u"syn"]):
                _log.debug("ACK: syn is invalid.")
                return

            # Update handshake.
            contract = self.contracts[contract_id]
            self.handshake[contract_id] = {
                "state": u"ACK",
                "timestamp": time.time()
            }

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

            _log.debug("ACK")

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

    def simple_data_request(self, data_id, node_unl, direction):
        file_size = 0
        if direction == u"send":
            action = u"upload"
        else:
            action = u"download"

        return self.data_request(action, data_id, file_size, node_unl)

    def data_request(self, action, data_id, file_size, node_unl):
        """
        Action = put (upload), get (download.)
        """
        _log.debug("In data request function")

        # Who is hosting this data?
        if action == "upload":
            # We store this data.
            direction = u"send"
            host_unl = self.net.unl.value
            assert(storage.manager.find(self.store_config, data_id) is not None)
        else:
            # They store the data.
            direction = u"receive"
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
            u"direction": direction,
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
        _log.debug("Sending data request")

        # Update handshake.
        self.handshake[contract_id] = {
            "state": "SYN",
            "timestamp": time.time()
        }

        # For async code.
        d = defer.Deferred()
        self.defers[contract_id] = d

        # Return defer for async code.
        return d

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
        _log.debug("Saving data chunk for " + str(data_id))
        _log.debug("of size + " + str(len(chunk)))
        assert(data_id in self.downloading)

        # Find temp file path.
        path = self.downloading[data_id]

        _log.debug(path)
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
        ),
        wif=alice_wallet.create_key(),
        store_config={"/home/laurence/Storj/Alice": None}  # FIXME temppath
    )



    # ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab
    # _log.debug(_log.debug(alice.move_file_to_storage("/home/laurence/Firefox_wallpaper.png")))

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
        store_config={"/home/laurence/Storj/Bob": None}  # FIXME use temppath
    )

    _log.debug(alice.net.unl.deconstruct())
    _log.debug(bob.net.unl.deconstruct())

    # alice.net.unl == bob.net.unl

    _log.debug(type(alice.net.unl))
    _log.debug(type(pyp2p.unl.UNL(value=bob.net.unl.value)))

    # exit()

    # Alice wants data from Bob.
    d = alice.data_request(
        "download",
        "ed980e5ef780d5b9ca1a6200a03302f2a91223044bc63dacc6d9f07eead663ab",
        0,
        bob.net.unl.value
    )

    def do_beep(ret):
        if ret != None:
            print("\a")

    d.addCallback(do_beep)

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
                _log.debug("Alice")
            else:
                _log.debug("Bob")
            process_transfers(client)

        time.sleep(0.002)
