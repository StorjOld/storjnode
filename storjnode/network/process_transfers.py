"""
This module handles getting data off of the sockets and making
sense of it all. The protocol is actually quite simple:

* Every SYN message defines a new data request.
* The data request hashes to produce a contract ID.
* At any given time there is only one data request active on a single
  connection between nodes uploading and downloading data between each other.
* To transfer multiple files between the same nodes, the same connection is
  used and the transfers are queued.
  This is what the con_transfer[con] = contract_id structure is for.
* The protocol looks like this:
    Send: contract_id (64 bytes) file_size (10 bytes) file_data.
* The person sending the contract ID depends on whoever has the greatest UNL
  when converted to an int -- this person is known as the master.
* The person sending the file_size is always the person who has the file.
* At the end of a transfer, the next data request is processed (send or recv
  contract_id) and the process continues.
"""

import logging
import struct
import time
import os
from twisted.internet import defer
import storjnode.storage as storage
from storjnode.network.file_handshake import protocol
import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
from pyp2p.dht_msg import DHT
import re
import sys
import storjnode


logging.VERBOSE = 5
logging.addLevelName(logging.VERBOSE, "VERBOSE")
logging.Logger.verbose = lambda inst, msg, *args, **kwargs:\
    inst.log(logging.VERBOSE, msg, *args, **kwargs)
logging.verbose = lambda msg, *args, **kwargs:\
    logging.log(logging.VERBOSE, msg, *args, **kwargs)

_log = storjnode.log.getLogger(__name__)


class TransferError(Exception):
    pass


def cleanup_cons(client):
    # Record old connections (dead connections.)
    old_cons = []
    for con in list(client.con_info):
        if not con.connected:
            # Broken connections.
            for contract_id in list(client.con_info[con]):
                if contract_id in client.defers:
                    e = TransferError("Connection died.")
                    client.defers[contract_id].errback(e)

            # Cleanup old structures.
            client.cleanup_transfers(con, contract_id)

            # Record old connection.
            old_cons.append(con)

    # Remove old connections.
    with client.mutex:
        for con in old_cons:
            client.cons.remove(con)


def expire_handshakes(client):
    # Deletes handshakes that don't have a response
    # after N seconds.
    for contract_id in list(client.contracts):
        if contract_id in client.handshake:
            handshake = client.handshake[contract_id]
            elapsed = time.time() - handshake["timestamp"]
            if elapsed >= 350:  # Tree fiddy. 'bout 6 mins.
                if contract_id in client.defers:
                    e = Exception("Handshake timed out.")
                    client.defers[contract_id].errback(e)
                    del client.defers[contract_id]


def do_upload(client, con, contract, con_info):
    _log.verbose("Upload")

    # Send file size.
    if not con_info["file_size"]:
        # Get file size.
        path = storage.manager.find(
            client.store_config,
            contract["data_id"]
        )
        if path is None:
            _log.debug("Error: we don't have this file!")
            con.close()
            return 0

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
    if bytes_sent:
        con_info["remaining"] -= bytes_sent

    _log.verbose("Remaining = ")
    _log.verbose(con_info["remaining"])

    # Everything uploaded.
    if not con_info["remaining"]:
        return 1

    return 0


def do_download(client, con, contract, con_info):
    _log.verbose("download")

    # Get file size.
    if not con_info["file_size"]:
        file_size_buf = con_info["file_size_buf"]
        if len(file_size_buf) < 20:
            remaining = 20 - len(file_size_buf)
            partial = con.recv(remaining)
            if not len(partial):
                return -1

            file_size_buf += partial
            if len(file_size_buf) == 20:
                if re.match(b"[0-9]+", file_size_buf) is None:
                    _log.debug("Invalid file size.")
                    con.close()
                    return -2

                file_size, = struct.unpack("<20s", file_size_buf)
                file_size = int(file_size_buf.rstrip(b"\0"))
                con_info["file_size"] = file_size
                con_info["remaining"] = file_size
            else:
                return -3

    # Download.
    data = con.recv(
        con_info["remaining"],
        encoding="ascii"
    )

    if len(data):
        con_info["remaining"] -= len(data)
        client.save_data_chunk(contract["data_id"], data)

    _log.verbose("Remaining = ")
    _log.verbose(con_info["remaining"])

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
                _log.debug("Error: downloaded file doesn't hash right! \a")
                os.remove(temp_path)
                return -4

            # Move shard to storage.
            storage.manager.add(
                client.store_config,
                shard
            )

        # Remove that we're downloading this.
        del client.downloading[data_id]

        # Ready for a new transfer (if there are any.)
        return 1

    return -5


def get_contract_id(client, con, contract_id):
    # Get contract ID piece.
    remaining = 64 - len(contract_id)
    _log.debug("Blocking = " + str(con.blocking))
    partial = con.recv(remaining)
    _log.debug("Contract id chunk = " + partial)
    _log.debug("Connected = " + str(con.connected))
    if not len(partial):
        _log.debug("Did not receive contract id")
        return 0

    # Update contract ID buffer.
    client.con_transfer[con] += partial
    contract_id = client.con_transfer[con]
    _log.debug("Skipping contract id.")

    # Check if we have the full ID now.
    if len(contract_id) == 64:
        return 1
    else:
        return 0


def complete_transfer(client, contract_id, con):
    with client.mutex:
        # Determine who is master.
        contract = client.contracts[contract_id]
        their_unl = client.get_their_unl(contract)
        is_master = client.net.unl.is_master(their_unl)
        _log.debug("Is master = " + str(is_master))

        # Return async success.
        if contract_id in client.defers:
            # Call any callbacks registered with this defer.
            client.defers[contract_id].callback(client.success_value)
            del client.defers[contract_id]

        # Call the completion handlers.
        # todo: remove handler
        old_handlers = set()
        for handler in client.handlers["complete"]:
            ret = handler(
                client,
                contract_id,
                con
            )

            if ret == -1:
                old_handlers.add(handler)

        # Remove old handlers.
        for handler in old_handlers:
            client.handlers["complete"].remove(handler)

        # Queue next transfer.
        if is_master:
            # Set next contract ID and send to client.
            client.queue_next_transfer(con)
        else:
            # Readying to receive a new contract ID.
            client.con_transfer[con] = u""


def process_dht_messages(client):
    try:
        # Get new messages and run message handlers.
        if isinstance(client.net.dht_node, DHT):
            client.net.dht_node.get_messages()

        processed = []
        for msg in client.net.dht_messages:
            _log.debug("Processing: " + str(msg["message"]))
            if protocol(client, msg["message"]):
                processed.append(msg)

        for msg in processed:
            client.net.dht_messages.remove(msg)
    except Exception as e:
        _log.debug("In process DHT message")
        _log.debug(e)
        pass


def process_transfers(client):
    # Process DHT messages.
    process_dht_messages(client)

    # Process and accept connections.
    client.net.synchronize()

    # Raise appropriate async callbacks for errors.
    cleanup_cons(client)

    # Expired handshakes and call any errbacks for errors.
    expire_handshakes(client)

    # Process connections.
    for con in client.cons:
        # Socket has hung ungracefully.
        duration = time.time() - con.alive
        if duration >= 60.0:
            _log.debug("Ungraceful socket close")
            con.close()
            continue

        # Wait until there's new transfers to process.
        if not client.is_queued(con):
            continue

        # Get active contract ID (if we're not master.)
        contract_id = client.con_transfer[con]
        if len(contract_id) < 64:
            _log.debug("Contract id =")
            _log.debug(contract_id)
            if not get_contract_id(client, con, contract_id):
                continue
            else:
                # Check contract ID is associated with right con.
                contract_id = client.con_transfer[con]
                if contract_id not in client.con_info[con]:
                    _log.debug("Client sent wrong contract ID!")
                    con.close()
                    continue

        # Check contract id.
        if contract_id not in client.contracts:
            _log.debug("Contract ID not found")
            con.close()
            continue

        # Reached end of transfer queue.
        if contract_id == u"0" * 64:
            continue

        # Anything left to do?
        con_info = client.con_info[con][contract_id]
        if not con_info["remaining"]:
            continue

        # Execute start callbacks.
        if not con_info["file_size"]:
            _log.debug("In con, and starting new transfer =")
            old_handlers = set()
            for handler in client.handlers["start"]:
                # Test start handler.
                ret = handler(client, con, contract_id)

                # Handler was associated with this transfer.
                if ret == -1:
                    old_handlers.add(handler)

            # Remove old start handlers.
            for handler in old_handlers:
                client.handlers["start"].remove(handler)

        # Transfer data.
        contract = client.contracts[contract_id]
        if client.get_direction(contract_id) == u"send":
            transfer_complete = do_upload(client, con, contract, con_info)
        else:
            transfer_complete = do_download(client, con, contract, con_info)

        # Run any callbacks and schedule next transfer.
        if transfer_complete == 1:
            _log.debug("Transfer completed")
            complete_transfer(client, contract_id, con)

    # Only reschedule the Looping call when this is done.
    d = defer.Deferred()
    d.callback(None)
    return d
