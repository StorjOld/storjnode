import logging
from collections import OrderedDict
import json
import time
import pyp2p.unl
import pyp2p.net
import pyp2p.dht_msg
import tempfile
import sys
import storjnode.storage as storage

_log = logging.getLogger(__name__)

ENABLE_ACCEPT_HANDLERS = 0

class RequestDenied(Exception):
    pass

# Validate the integrity of a SYN message.
def is_valid_syn(client, msg):
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
    if client.net.unl == pyp2p.unl.UNL(value=msg[u"host_unl"]):
        # Then check we have this file.
        path = storage.manager.find(client.store_config, msg[u"data_id"])
        if path is None:
            _log.debug("Failed to find file we're uploading")
            return 0
    else:
        # Do we already have this file?
        path = storage.manager.find(client.store_config, msg[u"data_id"])
        if path is not None:
            _log.debug("Attempting to download file we already have")
            return 0

        # Are we already trying to download this?
        if msg[u"data_id"] in client.downloading:
            _log.debug("We're already trying to download this")
            return 0

    return 1

# Associate TCP con with contract.
def success_wrapper(client, contract_id, host_unl):
    def success(con):
        with client.mutex:
            _log.debug("IN SUCCESS CALLBACK")
            _log.debug("Success() contract_id = " + str(contract_id))

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
                    "remaining": 350, # Tree fiddy.
                    "file_size": file_size,
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

            #Return new connection.
            client.cons.append(con)

    return success

def process_syn(client, msg):
    # Check syn is valid.
    if not is_valid_syn(client, msg):
        _log.debug("SYN: invalid syn.")
        return

    # Should we accept this?
    contract_id = client.contract_id(msg).decode("utf-8")
    src_node_id = client.get_node_id_from_unl(msg[u"src_unl"])
    if ENABLE_ACCEPT_HANDLERS:
        accept_this = 0
        for handler in client.handlers[u"accept"]:
            accept_this = handler(
                src_node_id,
                msg[u"data_id"],
                msg[u"direction"]
            )

            if accept_this:
                break

        # Their handshake will timeout.
        if not accept_this:
            _log.debug("Rejected data request")

            # Build reject reply.
            reply = OrderedDict({
                u"status": u"RST",
                u"contract_id": contract_id,
                u"src_unl": client.net.unl.value
            })
            # Sign reply.
            reply = client.sign_contract(reply)

            # Send reply to source.
            reply = json.dumps(reply, ensure_ascii=True)
            client.net.dht_node.relay_message(
                src_node_id,
                reply
            )

            # Quit.
            return

    # Check our UNL is correct.
    if msg[u"dest_unl"] != client.net.unl.value:
        _log.debug("They got our UNL wrong.")
        return

    # Check their sig is valid.
    if not client.is_valid_contract_sig(msg, src_node_id):
        _log.debug("Their signature was incorrect.")
        return

    # Check handshake state.
    if contract_id in client.handshake:
        return

    # Save contract.
    client.save_contract(msg)
    client.handshake[contract_id] = {
        u"state": u"SYN-ACK",
        u"timestamp": time.time()
    }

    # Create reply.
    reply = OrderedDict({
        u"status": u"SYN-ACK",
        u"syn": msg,
    })

    # Sign reply.
    reply = client.sign_contract(reply)

    # Save reply.
    client.send_msg(reply, msg[u"src_unl"])
    _log.debug("SYN")

def process_syn_ack(client, msg):
    # Valid syn-ack?
    if u"syn" not in msg:
        _log.debug("SYN-ACK: syn not in msg.")
        return

    # Is this a reply to our SYN?
    contract_id = client.contract_id(msg[u"syn"])
    if contract_id not in client.contracts:
        _log.debug("--------------")
        _log.debug(msg)
        _log.debug("--------------")
        _log.debug(client.contracts)
        _log.debug("--------------")
        _log.debug("SYN-ACK: contract not found.")
        return

    # Check syn is valid.
    if not is_valid_syn(client, msg[u"syn"]):
        _log.debug("SYN-ACK: invalid syn.")
        return

    # Did I sign this?
    if not client.is_valid_contract_sig(msg[u"syn"]):
        _log.debug("SYN-ACK: sig is invalid.")
        return

    # Check their sig is valid.
    contract = client.contracts[contract_id]
    their_node_id = client.get_node_id_from_unl(contract["dest_unl"])
    if not client.is_valid_contract_sig(msg, their_node_id):
        _log.debug("Their signature was incorrect.")
        return

    # Check handshake state is valid.
    if contract_id not in client.handshake:
        return
    if client.handshake[contract_id][u"state"] != u"SYN":
        return

    # Update handshake.
    client.handshake[contract_id] = {
        u"state": u"ACK",
        u"timestamp": time.time()
    }

    # Create reply contract.
    reply = OrderedDict({
        u"status": u"ACK",
        u"syn_ack": msg
    })

    # Sign reply.
    reply = client.sign_contract(reply)

    # Try make TCP con.
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

def process_ack(client, msg):
    # Valid ack.
    if u"syn_ack" not in msg:
        _log.debug("ACK: syn_ack not in msg.")
        return
    if u"syn" not in msg[u"syn_ack"]:
        _log.debug("ACK: syn not in msg.")
        return

    # Is this a reply to our SYN-ACK?
    contract_id = client.contract_id(msg[u"syn_ack"][u"syn"])
    if contract_id not in client.contracts:
        _log.debug("ACK: contract not found.")
        return

    # Did I sign this?
    if not client.is_valid_contract_sig(msg[u"syn_ack"]):
        _log.debug("--------------")
        _log.debug(msg)
        _log.debug("--------------")
        _log.debug(client.contracts)
        _log.debug("--------------")
        _log.debug("ACK: sig is invalid.")
        return

    # Check their sig is valid.
    contract = client.contracts[contract_id]
    their_node_id = client.get_node_id_from_unl(contract["src_unl"])
    if not client.is_valid_contract_sig(msg, their_node_id):
        _log.debug("Their signature was incorrect.")
        return

    # Is the syn valid?
    if not is_valid_syn(client, msg[u"syn_ack"][u"syn"]):
        _log.debug("ACK: syn is invalid.")
        return

    # Check handshake state is valid.
    if contract_id not in client.handshake:
        return
    if client.handshake[contract_id][u"state"] != u"SYN-ACK":
        return

    # Update handshake.
    contract = client.contracts[contract_id]
    client.handshake[contract_id] = {
        u"state": u"ACK",
        u"timestamp": time.time()
    }

    # Try make TCP con.
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

def process_rst(client, msg):
    # Sanity checks.
    if u"contract_id" not in msg:
        _log.debug("RST: Contract id not in msg")
        return

    if u"src_unl" not in msg:
        _log.debug("RST: Src unl not in msg")
        return

    contract_id = msg[u"contract_id"]
    if contract_id not in client.contracts:
        _log.debug("RST: Contract not found")
        _log.debug("-------------")
        _log.debug(client.contracts)
        _log.debug("-------------")
        _log.debug(str(msg))
        return

    # Check UNLs match for this contract.
    contract = client.contracts[contract_id]
    expected_unl = contract["dest_unl"]
    found_unl = msg[u"src_unl"]
    if expected_unl != found_unl:
        _log.debug("RST: UNLs dont match")
        return

    # Check sig matches the UNL.
    node_id = client.get_node_id_from_unl(found_unl)
    if not client.is_valid_contract_sig(msg, node_id):
        _log.debug("RST: sig doesn't match")
        return

    # Raise rejection callback and return!
    _log.debug("Rejection request received!")
    if contract_id in client.defers:
        _log.debug("RST: firing errback")
        e = RequestDenied("Request was rejected!")
        client.defers[contract_id].errback(e)
        del client.defers[contract_id]

def protocol(client, msg):
    msg = json.loads(msg, object_pairs_hook=OrderedDict)
    msg_handlers = {
        u"SYN": process_syn,
        u"SYN-ACK": process_syn_ack,
        u"ACK": process_ack,
        u"RST": process_rst
    }

    # Sanity checking.
    if u"status" not in msg:
        return 0

    # Process msg.
    status = msg[u"status"]
    if status in msg_handlers:
        msg_handlers[status](client, msg)
        return 1

    return 0



