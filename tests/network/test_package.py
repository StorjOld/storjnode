import time
import unittest
from btctxstore import BtcTxStore
from storjnode.network import package
from pycoin.encoding import a2b_hashed_base58
from btctxstore.common import num_to_bytes


class TestPackage(unittest.TestCase):

    def setUp(self):
        self.btctxstore = BtcTxStore()
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)

    def test_parse_normal(self):
        package_bytes = package._create(package._TYPE_DATA, self.wif,
                                        b"F483", self.btctxstore.testnet)
        self.assertTrue(package_bytes is not None)
        parsed = package.parse(package_bytes, 10, self.btctxstore.testnet)
        self.assertEqual(parsed, {
            "type": "DATA", "data": b"F483", "node": self.address
        })

    def test_ignores_nondata_package_with_data(self):
        package_bytes = package._create(package._TYPE_DATA, self.wif,
                                        b"F483", self.btctxstore.testnet)
        self.assertTrue(package_bytes is not None)
        hacked_bytes = b'0' + package_bytes[1:]  # hack type
        parsed = package.parse(hacked_bytes, 10, self.btctxstore.testnet)
        self.assertEqual(parsed, None)

    def test_ignores_invalid_address(self):
        package_bytes = package._create(package._TYPE_DATA, self.wif,
                                        b"F483", self.btctxstore.testnet)
        self.assertTrue(package_bytes is not None)
        hacked_bytes = b'0X' + package_bytes[2:]  # hack type
        parsed = package.parse(hacked_bytes, 10, self.btctxstore.testnet)
        self.assertEqual(parsed, None)

    def test_ignores_stale_package(self):
        package_bytes = package._create(package._TYPE_DATA, self.wif,
                                        b"F483", self.btctxstore.testnet)
        self.assertTrue(package_bytes is not None)
        time.sleep(2)
        parsed = package.parse(package_bytes, 1, self.btctxstore.testnet)
        self.assertEqual(parsed, None)

    def test_ignores_package_to_small(self):
        result = package.parse(b"", 2)
        self.assertEqual(None, result)

    def test_ignores_package_to_large(self):
        result = package.parse(b"X" * 8193, 10)
        self.assertEqual(None, result)

    def test_ignores_incorrect_type(self):
        ptype = b"X"
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = num_to_bytes(package._BYTES_UNIXTIME, int(time.time()))
        pdata_size = (chr(0) + chr(4)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata, 10)
        expected = None
        self.assertEqual(expected, result)

    def test_ignores_size_to_small(self):
        ptype = package._TYPE_DATA
        paddress = a2b_hashed_base58(self.address)
        punixtime = num_to_bytes(package._BYTES_UNIXTIME, int(time.time()))
        pdata_size = (chr(0) + chr(3)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata, 10)
        expected = None
        self.assertEqual(expected, result)

    def test_ignores_size_to_large(self):
        ptype = package._TYPE_DATA
        paddress = a2b_hashed_base58(self.address)
        punixtime = num_to_bytes(package._BYTES_UNIXTIME, int(time.time()))
        pdata_size = (chr(0) + chr(5)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata, 10)
        expected = None
        self.assertEqual(expected, result)

    def test_ignores_bad_signature(self):
        ptype = package._TYPE_DATA
        paddress = a2b_hashed_base58(self.address)
        punixtime = num_to_bytes(package._BYTES_UNIXTIME, int(time.time()))
        pdata_size = (chr(0) + chr(4)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata, 10)
        expected = None
        self.assertEqual(expected, result)


class TestNetworkPackageCreate(unittest.TestCase):

    def setUp(self):
        self.btctxstore = BtcTxStore()
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)

    def test_syn(self):
        synpackage = package.syn(self.wif, self.btctxstore.testnet)
        result = package.parse(synpackage, 10, self.btctxstore.testnet)
        self.assertEqual(result, {
            "type": "SYN", "data": b"", "node": self.address
        })

    def test_synack(self):
        synackpackage = package.synack(self.wif, self.btctxstore.testnet)
        result = package.parse(synackpackage, 10, self.btctxstore.testnet)
        self.assertEqual(result, {
            "type": "SYNACK", "data": b"", "node": self.address
        })

    def test_ack(self):
        ackpackage = package.ack(self.wif, self.btctxstore.testnet)
        result = package.parse(ackpackage, 10, self.btctxstore.testnet)
        self.assertEqual(result, {
            "type": "ACK", "data": b"", "node": self.address
        })

    def test_data(self):
        datapackage = package.data(self.wif, b"F483", self.btctxstore.testnet)
        result = package.parse(datapackage, 10, self.btctxstore.testnet)
        self.assertEqual(result, {
            "type": "DATA", "data": b"F483", "node": self.address
        })

    def test_max_data_accepted(self):
        data_bytes = b"X" * package.MAX_DATA_SIZE
        datapackage = package.data(self.wif, data_bytes,
                                   self.btctxstore.testnet)
        result = package.parse(datapackage, 10, self.btctxstore.testnet)
        self.assertEqual(result, {
            "type": "DATA", "data": data_bytes, "node": self.address
        })

    def test_checks_max_data_exceeded(self):
        def callback():
            data_bytes = b"X" * (package.MAX_DATA_SIZE + 1)
            package.data(self.wif, data_bytes, self.btctxstore.testnet)
        self.assertRaises(package.MaxPackageDataExceeded, callback)


if __name__ == "__main__":
    unittest.main()
