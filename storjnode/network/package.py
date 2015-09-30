"""
NETWORK BINARY PACKAGE FORMAT
1  byte    package type
21 bytes   sender btcaddress
8  bytes   unix timestamp
2  bytes   data size
x  bytes   data bytes
65 bytes   signature
"""

import time
import logging
import btctxstore
from pycoin.encoding import b2a_hashed_base58
from pycoin.encoding import a2b_hashed_base58
from btctxstore.common import num_to_bytes
from btctxstore.common import num_from_bytes


log = logging.getLogger(__name__)


PACKAGE_TYPES = [b'0', b'1', b'2', b'3']
PACKAGE_TYPE_NAMES = ["SYN", "SYNACK", "ACK", "DATA"]
PACKAGE_TYPE_SYN = PACKAGE_TYPES[0]
PACKAGE_TYPE_SYNACK = PACKAGE_TYPES[1]
PACKAGE_TYPE_ACK = PACKAGE_TYPES[2]
PACKAGE_TYPE_DATA = PACKAGE_TYPES[3]

PACKAGE_BYTES_TYPE = 1
PACKAGE_BYTES_BTCADDRESS = 21
PACKAGE_BYTES_UNIXTIME = 8
PACKAGE_BYTES_DATASIZE = 2
PACKAGE_BYTES_SIGNATURE = 65

PACKAGE_MAX_SIZE = 8192  # FIXME is this true?
PACKAGE_MAX_DATA_SIZE = (PACKAGE_MAX_SIZE - PACKAGE_BYTES_TYPE
                         - PACKAGE_BYTES_BTCADDRESS - PACKAGE_BYTES_UNIXTIME
                         - PACKAGE_BYTES_DATASIZE - PACKAGE_BYTES_SIGNATURE)
PACKAGE_MIN_SIZE = (PACKAGE_BYTES_TYPE + PACKAGE_BYTES_BTCADDRESS
                    + PACKAGE_BYTES_UNIXTIME + PACKAGE_BYTES_DATASIZE
                    + PACKAGE_BYTES_SIGNATURE)


def make(package_type, signing_wif, data_bytes=b"", testnet=False):
    key = btctxstore.deserialize.key(testnet, signing_wif)
    package = package_type
    package += a2b_hashed_base58(key.address())
    package += num_to_bytes(PACKAGE_BYTES_UNIXTIME, int(time.time()))
    package += num_to_bytes(PACKAGE_BYTES_DATASIZE, len(data_bytes))
    package += data_bytes
    package += btctxstore.control.sign_data(testnet, package, key)
    return package


def parse(package_bytes, dcc_address, expire_time, testnet=False):

    # check size
    if len(package_bytes) < PACKAGE_MIN_SIZE:
        log.warning("Invalid package: Package to small!")
        return None
    if len(package_bytes) > PACKAGE_MAX_SIZE:
        log.warning("Invalid package: Package to large!")
        return None
    stack = package_bytes[:]  # copy and use like a stack

    # parse type
    package_type = stack[:PACKAGE_BYTES_TYPE]
    stack = stack[PACKAGE_BYTES_TYPE:]  # pop type
    if package_type not in PACKAGE_TYPES:
        log.warning("Invalid package: Invalid package type!")
        return None

    # parse address
    address_bytes = stack[:PACKAGE_BYTES_BTCADDRESS]
    stack = stack[PACKAGE_BYTES_BTCADDRESS:]  # pop address
    address = b2a_hashed_base58(address_bytes)
    if address != dcc_address:
        logmsg = "Invalid package: Package address {0} != dcc address {1}!"
        log.warning(logmsg.format(address, dcc_address))
        return None

    # get timestamp
    unixtime_bytes = stack[:PACKAGE_BYTES_UNIXTIME]
    stack = stack[PACKAGE_BYTES_UNIXTIME:]  # pop unixtime
    package_unixtime = num_from_bytes(PACKAGE_BYTES_UNIXTIME, unixtime_bytes)
    current_unixtime = int(time.time())
    time_delta = current_unixtime - package_unixtime
    if abs(time_delta) > expire_time:
        logmsg = "Invalid package: Stale package abs({0}) > {1}!"
        log.warning(logmsg.format(time_delta, expire_time))
        return None

    # get data size
    data_size_bytes = stack[:PACKAGE_BYTES_DATASIZE]
    stack = stack[PACKAGE_BYTES_DATASIZE:]  # pop data size
    data_size = num_from_bytes(PACKAGE_BYTES_DATASIZE, data_size_bytes)
    if len(stack) != (data_size + PACKAGE_BYTES_SIGNATURE):
        log.warning("Invalid package: Invalid data size {0}!".format(data_size))
        return None
    if data_size > 0 and package_type != PACKAGE_TYPE_DATA:
        logmsg = "Invalid package: {0}bytes data for non data package!"
        log.warning(logmsg.format(data_size))
        return None

    # get data
    data_bytes = stack[:data_size]
    stack = stack[data_size:]  # pop data

    # verify signature
    sig = package_bytes[-PACKAGE_BYTES_SIGNATURE:] # signature data
    signed = package_bytes[:-PACKAGE_BYTES_SIGNATURE]  # signed data
    assert(sig == stack)  # only signature should be left on the stack
    if not btctxstore.control.verify_signature(testnet, address, sig, signed):
        log.warning("Invalid package: bad signature!")
        return None

    return {
        "type": package_type,
        "address": address,
        "unixtime": package_unixtime,
        "data": data_bytes,
        "signature": sig
    }

