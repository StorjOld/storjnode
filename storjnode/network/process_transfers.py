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
import copy
from twisted.internet import defer
import storjnode.storage as storage
from pyp2p.lib import parse_exception
from storjnode.util import safe_log_var
from storjnode.network.file_handshake import protocol
import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
from pyp2p.dht_msg import DHT
from pyp2p.lib import request_priority_execution
from pyp2p.lib import release_priority_execution
from threading import Thread
import re
import sys
import storjnode


_log = storjnode.log.getLogger(__name__)
HANDSHAKE_TIMEOUT = 3600  # 300
CON_TIMEOUT = 3600  # 600
BLOCKING_TIMEOUT = 60


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
            _log.debug("CON DEAD, cleaning up cons")
            client.cleanup_transfers(con, contract_id)

            # Record old connection.
            old_cons.append(con)

    # Remove old connections.
    for con in old_cons:
        client.cons.remove(con)


def expire_handshakes(client, timestamp):
    # Deletes handshakes that don't have a response
    # after N seconds.
    for contract_id in list(client.contracts):
        if contract_id in client.handshake:
            handshake = client.handshake[contract_id]
            elapsed = timestamp - handshake["timestamp"]
            if elapsed >= HANDSHAKE_TIMEOUT:
                if contract_id in client.defers:
                    _log.debug("Expiring handshake")
                    e = Exception("Handshake timed out.")
                    client.defers[contract_id].errback(e)
                    del client.defers[contract_id]


def do_upload(client, con, contract, con_info, contract_id, timestamp):
    _log.debug("Upload")

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
        con_info["file_size"] = copy.copy(file_size)
        con_info["remaining"] = copy.copy(file_size)

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

        # Open new stream.
        client.file_stream.open(client.uploading[contract["data_id"]])

    # Transfer done.
    if not con_info["remaining"]:
        return 1
    _log.debug("Remaining = " + str(con_info["remaining"]))

    # Any streamed data ready to upload?
    data_id = client.uploading[contract["data_id"]]
    if not client.file_stream.can_read(data_id):
        _log.debug("Nothing ready to stream [upload]")
        pass

    while con_info["remaining"]:
        # Calculate chunk size.
        chunk_size = 65536
        if con_info["remaining"] < chunk_size:
            chunk_size = con_info["remaining"]

        # Request bandwidth for transfer.
        allocation = client.bandwidth.request(
            "upstream",
            contract_id,
            chunk_size
        )
        if not allocation:
            if client.bandwidth.is_over_monthly_limit("upstream"):
                interrupt_bandwidth_test(client, contract["data_id"])
                con.close()
            return 0

        # Get next chunk from file.
        position = con_info["file_size"] - con_info["remaining"]
        assert(position != con_info["file_size"])

        data_chunk = client.get_data_chunk(
            contract["data_id"],
            position,
            allocation
        )
        assert(data_chunk != b"")

        # Check data chunk.
        if data_chunk is None:
            interrupt_transfer(client, contract_id, con)
            return 0

        # Upload chunk binary to socket.
        bytes_sent = con.send(data_chunk, encoding="ascii")
        if bytes_sent:
            con_info["remaining"] -= bytes_sent
            con_info["last_update"] = timestamp
            con.alive = timestamp
            client.bandwidth.update(
                "upstream",
                bytes_sent,
                contract_id
            )

    path = client.uploading[contract["data_id"]]
    complete_transfer(client, contract_id, con)
    del client.threads_running[con]


def interrupt_bandwidth_test(client, data_id):
    if client.api is not None:
        bt = client.api.bandwidth_test
        if data_id == bt.data_id:
            if bt.active_test is not None:
                bt.active_test.errback(Exception("Error: bt interrupt"))

            client.api.bandwidth_test.reset_state()


def do_download(client, con, contract, con_info, contract_id, timestamp):
    _log.debug("download")

    # Get file size.
    if not con_info["file_size"]:
        file_size_buf = con_info["file_size_buf"]
        if len(file_size_buf) < 20:
            while len(file_size_buf) != 20:
                remaining = 20 - len(file_size_buf)
                partial = con.recv(remaining, encoding="ascii")
                if not len(partial):
                    continue

                file_size_buf += partial
                time.sleep(0.0001)

            if len(file_size_buf) == 20:
                if re.match(b"[0-9]+", file_size_buf) is None:
                    _log.debug("Invalid file size.")
                    con.close()
                    return -2

                file_size, = struct.unpack("<20s", file_size_buf)
                file_size = int(file_size_buf.rstrip(b"\0"))
                con_info["file_size"] = copy.copy(file_size)
                con_info["remaining"] = copy.copy(file_size)
                con.alive = timestamp
                client.file_stream.open(
                    client.downloading[contract["data_id"]]
                )
            else:
                return -3

    # Transfer done.
    if not con_info["remaining"]:
        return 1
    _log.debug("Remaining = " + str(con_info["remaining"]))

    while con_info["remaining"]:
        # Any streamed data ready to upload?
        data_id = client.downloading[contract["data_id"]]
        if not client.file_stream.can_write(data_id):
            time.sleep(0.001)
            continue

        # Calculate chunk size.
        chunk_size = 65536
        if con_info["remaining"] < chunk_size:
            chunk_size = con_info["remaining"]

        # Request bandwidth for transfer.
        allocation = client.bandwidth.request(
            "downstream",
            contract_id,
            chunk_size
        )
        if not allocation:
            if client.bandwidth.is_over_monthly_limit("downstream"):
                interrupt_bandwidth_test(client, contract["data_id"])
                con.close()
            return -6

        # Download.
        data = con.recv(
            allocation,
            encoding="ascii"
        )

        bytes_recv = len(data)
        if bytes_recv:
            con_info["remaining"] -= len(data)
            con_info["last_update"] = timestamp
            client.save_data_chunk(contract["data_id"], data)
            client.bandwidth.update(
                "downstream",
                bytes_recv,
                contract_id
            )

    # When done downloading close con.
    if not con_info["remaining"]:
        # Wait for any outstanding data to be written to file.
        data_id = contract["data_id"]
        temp_path = client.downloading[data_id]
        while client.file_stream.is_writing_data(temp_path):
            time.sleep(0.0001)

        # Check download.
        with open(temp_path, "rb+") as shard:
            # Delete file if it doesn't hash right!
            found_hash = storage.shard.get_id(shard)
            if found_hash != data_id:
                _log.debug(found_hash)
                _log.debug(data_id)
                _log.debug("Error: downloaded file doesn't hash right! \a")
                interrupt_transfer(client, contract_id, con)
                return -4
            else:
                # Move shard to storage.
                try:
                    storage.manager.add(
                        client.store_config,
                        shard
                    )
                except MemoryError:
                    interrupt_transfer(client, contract_id, con)
                    return -6

        # Remove that we're downloading this.
        del client.downloading[data_id]

        # Ready for a new transfer (if there are any.)
        complete_transfer(client, contract_id, con)
        del client.threads_running[con]
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


def interrupt_transfer(client, contract_id, con):
    # Return async failure.
    _log.debug("got interrupt transfer")
    if contract_id in client.defers:
        client.defers[contract_id].errback(Exception("Transfer interupted"))

    # Cleanup bandwidth tests (if active.)
    contract = client.contracts[contract_id]
    interrupt_bandwidth_test(client, contract["data_id"])

    # Find who is master.
    their_unl = client.get_their_unl(contract)
    is_master = client.net.unl.is_master(their_unl)

    # Queue next transfer.
    if is_master:
        # Set next contract ID and send to client.
        client.queue_next_transfer(con)
        _log.debug("End queuing next transfer")
    else:
        # Readying to receive a new contract ID.
        client.con_transfer[con] = u""

    # Cleanup transfer details.
    client.cleanup_transfers(None, contract_id)

    # Release con lock.
    del client.threads_running[con]


def complete_transfer(client, contract_id, con):
    _log.debug("in complete transfer")
    _log.debug(str(client))
    _log.debug(str(con))
    _log.debug(str(contract_id))

    # Leave bandwidth slice table.
    _log.debug(str(client.bandwidth.transfers))
    _log.debug(str(contract_id))
    client.bandwidth.remove_transfer(contract_id)
    _log.debug("Removed bandwidth reservation")

    # Determine who is master.
    contract = client.contracts[contract_id]
    their_unl = client.get_their_unl(contract)
    is_master = client.net.unl.is_master(their_unl)
    _log.debug("Is master = " + str(is_master))

    # Return async success.
    if contract_id in client.defers:
        # Call any callbacks registered with this defer.
        _log.debug("Complete transfer: removing defer" + str(client))
        client.defers[contract_id].callback(client.success_value)
        del client.defers[contract_id]
    else:
        _log.debug(str(client))
        _log.debug("Contract id not in client defers!")

    # Call the completion handlers.
    # todo: remove handler
    _log.debug("Past that point")
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
        if handler in client.handlers["complete"]:
            client.handlers["complete"].remove(handler)

    # Queue next transfer.
    if is_master:
        # Set next contract ID and send to client.
        client.queue_next_transfer(con)
        _log.debug("End queuing next transfer")
    else:
        # Readying to receive a new contract ID.
        client.con_transfer[con] = u""

    _log.debug("Finished complete")


def process_dht_messages(client):
    processed = []
    try:
        # Get new messages and run message handlers.
        if isinstance(client.net.dht_node, DHT):
            client.net.dht_node.get_messages()

        for msg in client.net.dht_messages:
            processed.append(msg)
            protocol(client, msg["message"])
    except Exception as e:
        _log.debug(str(parse_exception(e)))
        _log.debug("exception in process DHT message")
        _log.debug(e)
    finally:
        for msg in processed:
            client.net.dht_messages.remove(msg)


def process_con_callbacks(client):
    # Process con success callbacks from UNL.connect.
    while not client.con_callback_queue.empty():
        start_transfers = 1
        if client.latency_tests.enabled:
            start_transfers = 0

        client.con_callback_queue.get()(start_transfers)


def process_latency_tests(client, timestamp):
    # Process latency tests.
    if client.latency_tests.enabled:
        did_latency_tests = False
        future = timestamp + 10
        while client.latency_tests.are_running() and timestamp < future:
            for con in list(client.latency_tests.tests):
                latency_test = client.latency_tests.by_con(con)
                is_finished = 0
                while not is_finished:
                    process_con_callbacks(client)
                    client.net.synchronize()
                    if latency_test.is_active:
                        for msg in con:
                            _log.debug(str(msg))
                            latency_test.process_msg(msg)
                    else:
                        # Todo: test while.
                        while not latency_test.contracts.empty():
                            _log.debug("Latency test finished")
                            contract = latency_test.contracts.get()
                            client.schedule_transfers(contract, con)

                        client.latency_tests.finished[con] = latency_test
                        del client.latency_tests.tests[con]
                        is_finished = 1


def do_upkeep(client, timestamp):
    # Raise appropriate async callbacks for errors.
    cleanup_cons(client)

    # Expired handshakes and call any errbacks for errors.
    expire_handshakes(client, timestamp)

    # Handle bandwidth test timeouts.
    if client.api is not None:
        # May not be initialised yet.
        if hasattr(client.api, "bandwidth_test"):
            client.api.bandwidth_test.handle_timeout()


def process_transfers(client, timestamp=time.time()):
    # Process latency tests.
    process_latency_tests(client, timestamp)

    # Process connections.
    for con in client.cons:
        if con in client.threads_running:
            continue

        # Con not ready.
        if con.nonce is None:
            # This should never happen but sanity check anyway.
            continue

        # Socket has hung ungracefully.
        duration = timestamp - con.alive
        if duration >= CON_TIMEOUT:
            _log.debug(duration)
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
                _log.debug("Can't get contract id")
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
            _log.debug(contract_id)
            _log.debug("Contract ID not found")
            continue

        # Reached end of transfer queue.
        if contract_id == u"0" * 64:
            _log.debug("end of transfer queue")
            continue

        # Anything left to do?
        con_info = client.con_info[con][contract_id]
        if not con_info["remaining"]:
            _log.debug("remaining is none")
            continue

        # Execute start callbacks.
        if con_info["last_update"] is None:
            # Fire start handlers.
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
                if handler in client.handlers["start"]:
                    client.handlers["start"].remove(handler)

            # Initialise update time.
            con_info["last_update"] = timestamp

        # Has the other side run into some error?
        elapsed = timestamp - con_info["last_update"]
        if elapsed >= BLOCKING_TIMEOUT:
            _log.debug("Detected infinite blocking in transfer loop")
            interrupt_transfer(client, contract_id, con)
            continue

        # Transfer data.
        contract = client.contracts[contract_id]
        remaining = con_info["remaining"]
        if client.get_direction(contract_id) == u"send":
            args = (
                client,
                con,
                contract,
                con_info,
                contract_id,
                timestamp
            )
            t = Thread(target=do_upload, args=args)
            t.setDaemon(True)
            t.start()
            client.threads_running[con] = t
        else:
            args = (
                client,
                con,
                contract,
                con_info,
                contract_id,
                timestamp
            )
            t = Thread(target=do_download, args=args)
            t.setDaemon(True)
            t.start()
            client.threads_running[con] = t

    # Process connection callbacks.
    process_con_callbacks(client)
