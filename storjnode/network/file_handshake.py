import storjnode
from collections import OrderedDict
import time
import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
import tempfile
import sys
import storjnode
import logging
import json
import storjnode.storage as storage
from storjnode.util import parse_node_id_from_unl
from storjnode.util import ordered_dict_to_list, list_to_ordered_dict
from ast import literal_eval

_log = storjnode.log.getLogger(__name__)

# If this is disabled then any node can transfer with any other node
# Without having a corresponding accept handler.
ENABLE_ACCEPT_HANDLERS = 1

# If connection reuse doesn't work out, set this to 0.
# Controls whether files can be queued for download over same connection.
# It would be ideal if this works.
ENABLE_QUEUED_TRANSFERS = 1


class RequestDenied(Exception):
    pass


# Validate the integrity of a SYN message.
def is_valid_syn(client, msg):
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
        _log.debug("Missing required key.")
        return -1

    # Check there aren't extra fields.
    if len(msg) != len(syn_schema):
        _log.debug("Invalid dictionary length.")
        return -2

    # Check data ID is valid.
    if not storjnode.storage.shard.valid_id(msg[u"data_id"]):
        _log.debug("Invalid data id.")
        return -3

    # Check SYN size.
    if len(str(msg)) > 5242880:  # 5 MB.
        _log.debug("SYN is too big")
        return -4

    # Check the UNLs are valid.
    unl_tuple = (u"host_unl", u"dest_unl", u"src_unl")
    for unl_key in unl_tuple:
        if not pyp2p.unl.is_valid_unl(msg[unl_key]):
            _log.debug("Invalid UNL for " + unl_key)
            _log.debug(msg[unl_key])
            return -6

    # Check file size.
    file_size_type = type(msg[u"file_size"])
    if sys.version_info >= (3, 0, 0):
        expr = file_size_type != int
    else:
        expr = file_size_type != int and file_size_type != long
    if expr:
        _log.debug("File size validation failed")
        _log.debug(type(msg[u"file_size"]))
        return -7

    # Are we the host?
    if client.get_direction(None, msg) == u"send":
        # Then check we have this file.
        path = storjnode.storage.manager.find(client.store_config,
                                              msg[u"data_id"])
        if path is None:
            _log.debug("Failed to find file we're uploading")
            return -8
    else:
        # Do we already have this file?
        path = storjnode.storage.manager.find(client.store_config,
                                              msg[u"data_id"])
        if path is not None:
            _log.debug("Attempting to download file we already have")
            return -9

        # Are we already trying to download this?
        if msg[u"data_id"] in client.downloading:
            _log.debug("We're already trying to download this")
            return -10

    return 1


# Associate TCP con with contract.
def success_wrapper(client, contract_id, host_unl):
    def success(con):
        with client.mutex:
            _log.debug("IN SUCCESS CALLBACK")
            _log.debug("Success() contract_id = " + str(contract_id))
            assert(host_unl is not None)
            assert(contract_id is not None)
            assert(client is not None)

            # Modify socket and change it get

            # Associate TCP con with contract.
            contract = client.contracts[contract_id]
            file_size = contract["file_size"]

            # Store con association.
            if con not in client.con_info:
                client.con_info[con] = {}

            # Associate contract with con.
            if contract_id not in client.con_info[con]:
                client.con_info[con][contract_id] = {
                    "contract_id": contract_id,
                    "remaining": 350,  # Tree fiddy.
                    "file_size": 0,  # Sent as part of protocol.
                    "file_size_buf": b""
                }

            # Record download state.
            data_id = contract["data_id"]
            if client.net.unl != pyp2p.unl.UNL(value=host_unl):
                _log.debug("Success: download")
                fp, client.downloading[data_id] = tempfile.mkstemp()
            else:
                # Set initial upload for this con.
                _log.debug("Success: upload")

            # Queue first transfer.
            their_unl = client.get_their_unl(contract)
            is_master = client.net.unl.is_master(their_unl)
            _log.debug("Is master = " + str(is_master))
            if con not in client.con_transfer:
                if is_master:
                    # A transfer to queue processing.
                    client.queue_next_transfer(con)
                else:
                    # A transfer to receive (unknown.)
                    client.con_transfer[con] = u""
            else:
                if client.con_transfer[con] == u"0" * 64:
                    if is_master:
                        client.queue_next_transfer(con)
                    else:
                        client.con_transfer[con] = u""

            # Return new connection.
            if con not in client.cons:
                client.cons.append(con)

    return success


def process_syn(client, msg, enable_accept_handlers=ENABLE_ACCEPT_HANDLERS):
    # Check syn is valid.
    if is_valid_syn(client, msg) != 1:
        _log.debug("SYN: invalid syn.")
        return -1

    # Check our UNL is correct.
    if msg[u"dest_unl"] != client.net.unl.value:
        _log.debug("They got our UNL wrong.")
        return -3

    # Check their sig is valid.
    contract_id = client.contract_id(msg).decode("utf-8")
    src_node_id = parse_node_id_from_unl(msg[u"src_unl"])
    if not client.is_valid_contract_sig(msg, src_node_id):
        _log.debug(msg)
        _log.debug("Their signature was incorrect.")
        return -4

    # Should we accept this?
    expired_handlers = set()
    accept_this = 0
    for handler in client.handlers[u"accept"]:
        ret = handler(
            contract_id,
            msg[u"src_unl"],
            msg[u"data_id"],
            msg[u"file_size"]
        )

        if ret == -1:
            accept_this = 1
            expired_handlers.add(handler)
            break

        if ret == 1:
            accept_this = 1
            break

    # Their handshake will timeout.
    if not accept_this and enable_accept_handlers:
        _log.debug("Rejected data request")

        # Build reject reply.
        reply = OrderedDict([
            (u"status", u"RST"),
            (u"contract_id", contract_id),
            (u"src_unl", client.net.unl.value)
        ])
        # Sign reply.
        reply = client.sign_contract(reply)

        # Send reply to source.
        reply = json.dumps(reply, ensure_ascii=True)
        client.net.dht_node.relay_message(
            src_node_id,
            reply
        )

        # Quit.
        return -2

    # Remove expired accept handler.
    for handler in expired_handlers:
        client.handlers[u"accept"].remove(handler)

    # Check handshake state.
    if contract_id in client.handshake:
        return -5

    # Save contract.
    client.save_contract(msg)
    client.handshake[contract_id] = {
        u"state": u"SYN-ACK",
        u"timestamp": time.time()
    }

    # Create reply.
    reply = OrderedDict([
        (u"status", u"SYN-ACK"),
        (u"syn", msg),
    ])

    # Sign reply.
    reply = client.sign_contract(reply)

    # Save reply.
    client.send_msg(reply, msg[u"src_unl"])
    _log.debug("SYN")

    # Success.
    return reply


def process_syn_ack(client, msg):
    # Valid syn-ack?
    if u"syn" not in msg:
        _log.debug("SYN-ACK: syn not in msg.")
        return -1

    # Check length is correct.
    if len(msg) != 3:
        _log.debug("incorrect length")
        return -2

    # Is this a reply to our SYN?
    contract_id = client.contract_id(msg[u"syn"])
    if contract_id not in client.contracts:
        _log.debug("--------------")
        _log.debug(contract_id)
        _log.debug("--------------")
        _log.debug(msg)
        _log.debug("--------------")
        _log.debug(client.contracts)
        _log.debug("--------------")
        _log.debug("SYN-ACK: contract not found.")
        return -3

    # Check syn is valid.
    if is_valid_syn(client, msg[u"syn"]) != 1:
        _log.debug("SYN-ACK: invalid syn.")
        return -4

    # Did I sign this?
    if not client.is_valid_contract_sig(msg[u"syn"]):
        _log.debug("SYN-ACK: our sig is invalid.")
        return -5

    # Check their sig is valid.
    contract = client.contracts[contract_id]
    their_node_id = parse_node_id_from_unl(contract["dest_unl"])
    if not client.is_valid_contract_sig(msg, their_node_id):
        _log.debug(msg)
        _log.debug("Their signature was incorrect.")
        return -6

    # Check handshake state is valid.
    if contract_id not in client.handshake:
        _log.debug("contract id not in handshake")
        return -7
    if client.handshake[contract_id][u"state"] != u"SYN":
        _log.debug("state = " + str(client.handshake[contract_id][u"state"]))
        _log.debug("handshake state invalid")
        return -8

    # Update handshake.
    client.handshake[contract_id] = {
        u"state": u"ACK",
        u"timestamp": time.time()
    }

    # Create reply contract.
    reply = OrderedDict([
        (u"status", u"ACK"),
        (u"syn_ack", msg)
    ])

    # Sign reply.
    reply = client.sign_contract(reply)

    # Are we already connected?
    is_reliable_con = 0
    con = client.net.con_by_unl(contract["dest_unl"], client.cons)
    if con is not None:
        # Otherwise the con could be torn down soon.
        elapsed = time.time() - con.alive
        _log.debug("Alive duration: " + str(elapsed))
        if elapsed <= 40:
            is_reliable_con = 1
            success_wrapper(
                client,
                contract_id,
                contract["host_unl"]
            )(con)
    else:
        _log.debug("con is not reliable.")

    # Disable queued transfers.
    if not ENABLE_QUEUED_TRANSFERS:
        is_reliable_con = 0

    # Try make TCP con.
    if not is_reliable_con:
        client.net.unl.connect(
            contract["dest_unl"],
            {
                "success": success_wrapper(
                    client,
                    contract_id,
                    contract["host_unl"]
                )
            },
            force_master=0,
            nonce=contract_id
        )

    # Send reply.
    client.send_msg(reply, msg[u"syn"][u"dest_unl"])
    _log.debug("SYN-ACK")

    return reply


def process_ack(client, msg):
    """
    Notes: if we've already signed the SYN-ack  then this means the checks for
    their SYN have already been done and can be skipped.
    """

    # Valid ack.
    if u"syn_ack" not in msg:
        _log.debug("ACK: syn_ack not in msg.")
        return -1

    # Check length.
    if len(msg) != 3:
        _log.debug("ACK: invalid msg length.")
        return -2

    # Is this a reply to our SYN-ACK?
    contract_id = client.contract_id(msg[u"syn_ack"][u"syn"])
    if contract_id not in client.contracts:
        _log.debug("ACK: contract not found.")
        return -3

    # Did I sign this?
    if not client.is_valid_contract_sig(msg[u"syn_ack"]):
        _log.debug("--------------")
        _log.debug(msg)
        _log.debug("--------------")
        _log.debug(client.contracts)
        _log.debug("--------------")
        _log.debug("ACK: sig is invalid.")
        return -4

    # Check handshake state is valid.
    if contract_id not in client.handshake:
        _log.debug("Contract id not found in handshake.")
        return -5
    if client.handshake[contract_id][u"state"] != u"SYN-ACK":
        _log.debug("Invalid state for handshake.")
        return -6

    # Update handshake.
    contract = client.contracts[contract_id]
    client.handshake[contract_id] = {
        u"state": u"ACK",
        u"timestamp": time.time()
    }

    # Are we already connected?
    is_reliable_con = 0
    con = client.net.con_by_unl(contract["src_unl"], client.cons)
    if con is not None:
        # Otherwise the con could be torn down soon.
        elapsed = time.time() - con.alive
        _log.debug("Alive duration: " + str(elapsed))
        if elapsed <= 40:
            is_reliable_con = 1
            success_wrapper(
                client,
                contract_id,
                contract["host_unl"]
            )(con)
    else:
        _log.debug("con is not reliable")

    # Disable queued transfers.
    if not ENABLE_QUEUED_TRANSFERS:
        is_reliable_con = 0

    # Try make TCP con.
    if not is_reliable_con:
        client.net.unl.connect(
            contract["src_unl"],
            {
                "success": success_wrapper(
                    client,
                    contract_id,
                    contract["host_unl"]
                )
            },
            force_master=0,
            nonce=contract_id
        )

    _log.debug("ACK")

    # Success.
    return 1


def process_rst(client, msg):
    # Sanity checks.
    if u"contract_id" not in msg:
        _log.debug("RST: Contract id not in msg")
        return -1

    if u"src_unl" not in msg:
        _log.debug("RST: Src unl not in msg")
        return -2

    contract_id = msg[u"contract_id"]
    if contract_id not in client.contracts:
        _log.debug("RST: Contract not found")
        _log.debug("-------------")
        _log.debug(client.contracts)
        _log.debug("-------------")
        _log.debug(str(msg))
        return -3

    # Check UNLs match for this contract.
    contract = client.contracts[contract_id]
    expected_unl = contract["dest_unl"]
    found_unl = msg[u"src_unl"]
    if expected_unl != found_unl:
        _log.debug("RST: UNLs dont match")
        return -4

    # Check sig matches the UNL.
    node_id = parse_node_id_from_unl(found_unl)
    if not client.is_valid_contract_sig(msg, node_id):
        _log.debug("RST: sig doesn't match")
        return -5

    # Raise rejection callback and return!
    _log.debug("Rejection request received!")
    if contract_id in client.defers:
        _log.debug("RST: firing errback")
        e = RequestDenied("Request was rejected!")
        client.defers[contract_id].errback(e)
        del client.defers[contract_id]

    return 1


def protocol(client, msg):
    try:
        assert(type(msg) != str)
        _log.debug(msg)
        msg = list_to_ordered_dict(msg)
    except (ValueError, TypeError) as e:
        _log.debug(e)
        _log.debug("Protocol: unable to serialize as OrderedDict")
        return -1

    msg_handlers = {
        u"SYN": process_syn,
        u"SYN-ACK": process_syn_ack,
        u"ACK": process_ack,
        u"RST": process_rst
    }

    # Sanity checking.
    if u"status" not in msg:
        _log.debug("Protocol: no status in msg")
        return -2

    # Message too large.
    if len(str(msg)) >= 5242880:  # 5MB.
        _log.debug("Protocol: msg too big")
        return -3

    # Process msg.
    status = msg[u"status"]
    if status in msg_handlers:
        msg_handlers[status](client, msg)
        return 1
    else:
        print("MSG HANDLER NOT FOUND")

    return -4
