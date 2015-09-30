import logging
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)


import unittest
from btctxstore import BtcTxStore
from storjnode.network import package
from pycoin.encoding import b2a_hashed_base58
from pycoin.encoding import a2b_hashed_base58




class TestNetworkPackageParse(unittest.TestCase):

    def setUp(self):
        self.btctxstore = BtcTxStore()
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)

    def test_parse_normal(self):
        package_bytes = package._create(package._TYPE_DATA, self.wif, 
                                        b"F483", self.btctxstore.testnet)
        self.assertTrue(package_bytes != None)

        parsed = package.parse(package_bytes, self.address, 2, 
                               self.btctxstore.testnet)
        self.assertTrue(parsed != None)

    def test_ignores_package_to_small(self):
        result = package.parse(b"", None, 2)
        self.assertEqual(None, result)

    def test_ignores_package_to_large(self):
        result = package.parse(b"X" * 8193, None, 2)
        self.assertEqual(None, result)

    def test_ignores_incorrect_type(self):
        ptype = b"X"
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = (chr(0) * 7 + chr(3)).encode("ascii")
        pdata_size = (chr(0) + chr(4)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata, paddress, 2)
        expected = None
        self.assertEqual(expected, result)

    def test_ignores_size_to_small(self):
        ptype = package._TYPE_DATA
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = (chr(0) * 7 + chr(3)).encode("ascii")
        pdata_size = (chr(0) + chr(3)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata, paddress, 2)
        expected = None
        self.assertEqual(expected, result)

    def test_ignores_size_to_large(self):
        ptype = package._TYPE_DATA
        paddress = b"addraddraddraddraddra"  # shitty btc addr
        punixtime = (chr(0) * 7 + chr(3)).encode("ascii")
        pdata_size = (chr(0) + chr(5)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata, paddress, 2)
        expected = None
        self.assertEqual(expected, result)


class TestNetworkPackageCreate(unittest.TestCase):

    def setUp(self):
        self.btctxstore = BtcTxStore()
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)

    def test_syn(self):
        synpackage = package.syn(self.wif, self.btctxstore.testnet)
        result = package.parse(synpackage, self.address, 2,
                               self.btctxstore.testnet)
        self.assertEqual(result, {"type": "SYN", "data": b""})

    def test_synack(self):
        synackpackage = package.synack(self.wif, self.btctxstore.testnet)
        result = package.parse(synackpackage, self.address, 2,
                               self.btctxstore.testnet)
        self.assertEqual(result, {"type": "SYNACK", "data": b""})

    def test_ack(self):
        ackpackage = package.ack(self.wif, self.btctxstore.testnet)
        result = package.parse(ackpackage, self.address, 2,
                               self.btctxstore.testnet)
        self.assertEqual(result, {"type": "ACK", "data": b""})

    def test_data(self):
        datapackage = package.data(self.wif, b"F483", self.btctxstore.testnet)
        result = package.parse(datapackage, self.address, 2,
                               self.btctxstore.testnet)
        self.assertEqual(result, {"type": "DATA", "data": b"F483"})

    def test_max_data_accepted(self):
        data_bytes = b"X" * package.MAX_DATA_SIZE
        datapackage = package.data(self.wif, data_bytes,
                                   self.btctxstore.testnet)
        result = package.parse(datapackage, self.address, 2,
                               self.btctxstore.testnet)
        self.assertEqual(result, {"type": "DATA", "data": data_bytes})

    def test_checks_max_data_exceeded(self):
        def callback():
            data_bytes = b"X" * (package.MAX_DATA_SIZE + 1)
            package.data(self.wif, data_bytes, self.btctxstore.testnet)
        self.assertRaises(package.MaxPackageDataExceeded, callback)


if __name__ == "__main__":
    unittest.main()
