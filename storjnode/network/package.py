"""
NETWORK BINARY PACKAGE FORMAT
1  byte    package type
21 bytes   sending node btcaddress
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


_log = logging.getLogger(__name__)


_TYPES = [b'0', b'1', b'2', b'3']
_TYPE_NAMES = {
    b'0': "SYN",
    b'1': "SYNACK",
    b'2': "ACK",
    b'3': "DATA"
}
_TYPE_SYN = _TYPES[0]
_TYPE_SYNACK = _TYPES[1]
_TYPE_ACK = _TYPES[2]
_TYPE_DATA = _TYPES[3]

_BYTES_TYPE = 1
_BYTES_BTCADDRESS = 21
_BYTES_UNIXTIME = 8
_BYTES_DATASIZE = 2
_BYTES_SIGNATURE = 65

_MAX_SIZE = 8192
METADATA_SIZE = (_BYTES_TYPE + _BYTES_BTCADDRESS + _BYTES_UNIXTIME +
                 _BYTES_DATASIZE + _BYTES_SIGNATURE)
MAX_DATA_SIZE = _MAX_SIZE - METADATA_SIZE
_MIN_SIZE = (_BYTES_TYPE + _BYTES_BTCADDRESS + _BYTES_UNIXTIME +
             _BYTES_DATASIZE + _BYTES_SIGNATURE)


class MaxPackageDataExceeded(Exception):
    pass


def _create(package_type, wif, data=b"", testnet=False):
    assert(isinstance(data, bytes))
    if len(data) > MAX_DATA_SIZE:
        msg = "{0} > {1}".format(len(data), MAX_DATA_SIZE)
        raise MaxPackageDataExceeded(msg)
    key = btctxstore.deserialize.key(testnet, wif)
    package = package_type
    package += a2b_hashed_base58(key.address())
    package += num_to_bytes(_BYTES_UNIXTIME, int(time.time()))
    package += num_to_bytes(_BYTES_DATASIZE, len(data))
    package += data
    package += btctxstore.control.sign_data(testnet, package, key)
    return package


def syn(wif, testnet=False):
    return _create(_TYPE_SYN, wif, testnet=testnet)


def synack(wif, testnet=False):
    return _create(_TYPE_SYNACK, wif, testnet=testnet)


def ack(wif, testnet=False):
    return _create(_TYPE_ACK, wif, testnet=testnet)


def data(wif, data, testnet=False):
    return _create(_TYPE_DATA, wif, data=data, testnet=testnet)


def parse(package_bytes, expire_time, testnet=False):
    assert(isinstance(package_bytes, bytes))

    # check size
    if len(package_bytes) < _MIN_SIZE:
        _log.warning("Invalid package: Package to small!")
        return None
    if len(package_bytes) > _MAX_SIZE:
        _log.warning("Invalid package: Package to large!")
        return None
    stack = package_bytes[:]  # copy and use like a stack

    # parse type
    package_type = stack[:_BYTES_TYPE]
    stack = stack[_BYTES_TYPE:]  # pop type
    if package_type not in _TYPES:
        _log.warning("Invalid package: Bad type!")
        return None

    # parse address
    address_bytes = stack[:_BYTES_BTCADDRESS]
    stack = stack[_BYTES_BTCADDRESS:]  # pop address
    address = b2a_hashed_base58(address_bytes)
    if not btctxstore.BtcTxStore(testnet=testnet).validate_address(address):
        logmsg = "Invalid package: Invalid node address {0}!"
        _log.warning(logmsg.format(address))
        return None

    # get timestamp
    unixtime_bytes = stack[:_BYTES_UNIXTIME]
    stack = stack[_BYTES_UNIXTIME:]  # pop unixtime
    package_unixtime = num_from_bytes(_BYTES_UNIXTIME, unixtime_bytes)
    current_unixtime = int(time.time())
    time_delta = current_unixtime - package_unixtime
    if abs(time_delta) > expire_time:
        logmsg = "Invalid package: Stale package abs({0}) > {1}!"
        _log.warning(logmsg.format(time_delta, expire_time))
        return None

    # get data size
    data_size_bytes = stack[:_BYTES_DATASIZE]
    stack = stack[_BYTES_DATASIZE:]  # pop data size
    data_size = num_from_bytes(_BYTES_DATASIZE, data_size_bytes)
    expected_data_size = len(stack) - _BYTES_SIGNATURE
    if data_size != expected_data_size:
        logmsg = "Invalid package: Invalid data size! Got {0} expected {1}"
        _log.warning(logmsg.format(data_size, expected_data_size))
        return None
    if data_size > 0 and package_type != _TYPE_DATA:
        logmsg = "Invalid package: Got {0}bytes of data for non data package!"
        _log.warning(logmsg.format(data_size))
        return None

    # get data
    data = stack[:data_size]
    stack = stack[data_size:]  # pop data

    # verify signature
    sig = package_bytes[-_BYTES_SIGNATURE:]  # signature data
    signed = package_bytes[:-_BYTES_SIGNATURE]  # signed data
    assert(sig == stack)  # only signature should be left on the stack
    if not btctxstore.control.verify_signature(testnet, address, sig, signed):
        _log.warning("Invalid package: Bad signature!")
        return None

    return {"type": _TYPE_NAMES[package_type], "data": data, "node": address}
