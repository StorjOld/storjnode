"""
NETWORK BINARY PACKAGE FORMAT
1  byte    package type
20 bytes   sender btcaddress
8  bytes   unix timestamp
2  bytes   data size
x  bytes   data bytes
65 bytes   signature
"""

import logging
import btctxstore
from btctxstore.common import num_to_bytes
from btctxstore.common import num_from_bytes


log = logging.getLogger(__name__)


PACKAGE_TYPES = [b'0', b'1', b'2', b'3']
PACKAGE_TYPE_SYN = PACKAGE_TYPES[0]
PACKAGE_TYPE_SYNACK = PACKAGE_TYPES[1]
PACKAGE_TYPE_ACK = PACKAGE_TYPES[2]
PACKAGE_TYPE_DATA = PACKAGE_TYPES[3]

PACKAGE_BYTES_TYPE = 1
PACKAGE_BYTES_BTCADDRESS = 20  # FIXME is this true?
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


def _address_bytes_from_wif(address):
    pass  # TODO implement


def _address_bytes_to_address(address_bytes):
    pass  # TODO implement


def _unixtimestamp_as_bytes():
    unixtime = 0  # FIXME actually get unixtime
    return num_to_bytes(PACKAGE_BYTES_UNIXTIME, unixtime)


def _sign(signing_wif, data, testnet=False):
    key = btctxstore.deserialize.key(testnet, signing_wif)
    return btctxstore.control.sign_data(testnet, data, key)


def make(package_type, signing_wif, data_bytes=b"", testnet=False):
    package = package_type
    package += _address_bytes_from_wif(signing_wif)
    package += _unixtimestamp_as_bytes()
    package += num_to_bytes(PACKAGE_BYTES_DATASIZE, len(data_bytes))
    package += data_bytes
    package += _sign(signing_wif, package, testnet=testnet)
    return package


def parse(package):

    # check size
    if len(package) < PACKAGE_MIN_SIZE:
        return None
    if len(package) > PACKAGE_MAX_SIZE:
        return None
    package_stack = package[:]  # copy it

    # parse type
    package_type = package_stack[:PACKAGE_BYTES_TYPE]
    package_stack = package_stack[PACKAGE_BYTES_TYPE:]  # pop type
    if package_type not in PACKAGE_TYPES:
        return None

    # parse address
    address_bytes = package_stack[:PACKAGE_BYTES_BTCADDRESS]
    package_stack = package_stack[PACKAGE_BYTES_BTCADDRESS:]  # pop address
    # FIXME validate address and check if its equal to the connection address
    address = _address_bytes_to_address(address_bytes)

    # get timestamp
    unixtime_bytes = package_stack[:PACKAGE_BYTES_UNIXTIME]
    package_stack = package_stack[PACKAGE_BYTES_UNIXTIME:]  # pop unixtime
    unixtime = num_from_bytes(PACKAGE_BYTES_UNIXTIME, unixtime_bytes)

    # get data size
    data_size_bytes = package_stack[:PACKAGE_BYTES_DATASIZE]
    package_stack = package_stack[PACKAGE_BYTES_DATASIZE:]  # pop data size
    data_size = num_from_bytes(PACKAGE_BYTES_DATASIZE, data_size_bytes)
    if len(package_stack) != (data_size + PACKAGE_BYTES_SIGNATURE):
        return None

    # get data and signature
    data_bytes = package_stack[:data_size]
    signature = package_stack[PACKAGE_BYTES_DATASIZE:]  # pop data

    return {
        "type": package_type,
        "address": address,
        "unixtime": unixtime,
        "data": data_bytes,
        "signature": signature
    }
