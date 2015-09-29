import unittest
from storjnode.network import package


class TestNetworkPackageParse(unittest.TestCase):

    def test_parse_normal(self):
        ptype = package.PACKAGE_TYPE_DATA
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = (chr(0) * 7 + chr(3)).encode("ascii")
        pdata_size = (chr(0) + chr(4)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata)
        expected = {
            "type": ptype,
            "address": paddress,
            "unixtime": 3,
            "data": pdata,
            "signature": psig
        }
        self.assertEqual(expected, result)

    def test_ignores_package_to_small(self):
        result = package.parse(b"")
        self.assertEqual(None, result)

    def test_ignores_package_to_large(self):
        result = package.parse(b"X" * 8193)
        self.assertEqual(None, result)

    def test_ignores_incorrect_type(self):
        ptype = b"X"
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = (chr(0) * 7 + chr(3)).encode("ascii")
        pdata_size = (chr(0) + chr(4)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata)
        expected = None
        self.assertEqual(expected, result)

    def test_ignores_size_to_small(self):
        ptype = package.PACKAGE_TYPE_DATA
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = (chr(0) * 7 + chr(3)).encode("ascii")
        pdata_size = (chr(0) + chr(3)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata)
        expected = None
        self.assertEqual(expected, result)

    def test_ignores_size_to_large(self):
        ptype = package.PACKAGE_TYPE_DATA
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = (chr(0) * 7 + chr(3)).encode("ascii")
        pdata_size = (chr(0) + chr(5)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata)
        expected = None
        self.assertEqual(expected, result)


if __name__ == "__main__":
    unittest.main()
