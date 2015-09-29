import unittest
from storjnode.network import package


class TestNetworkPackageParse(unittest.TestCase):

    def test_parse_normal(self):
        ptype = package.PACKAGE_TYPE_DATA
        paddress = b"addraddraddraddraddr"  # shitty btc addr
        punixtime = (chr(0) * 8).encode("ascii")
        pdata_size = (chr(0) + chr(4)).encode("ascii")
        pdata = b"F483"
        psig = b"X" * 65
        packagedata = ptype + paddress + punixtime + pdata_size + pdata + psig
        result = package.parse(packagedata)
        expected = {
            "type": ptype,
            "address": paddress,
            "unixtime": 0,
            "data": pdata,
            "signature": psig
        }
        self.assertEqual(expected, result)


if __name__ == "__main__":
    unittest.main()
