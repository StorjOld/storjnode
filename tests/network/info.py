import unittest
import binascii
import umsgpack
import storjnode
import btctxstore


class TestInfo(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)
        self.nodeid = storjnode.util.address_to_node_id(self.address)

    def test_create_read_request(self):

        # test create
        created = storjnode.network.info.create_request(
            self.btctxstore, self.wif
        )

        # check package data < min package size
        packed = umsgpack.packb(created)
        self.assertLessEqual(len(packed), storjnode.common.MAX_PACKAGE_DATA)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(packed)

        # test read
        read = storjnode.network.info.read_request(self.btctxstore, repacked)
        self.assertIsNotNone(read)
        self.assertEqual(created, read)

    def test_create_read_response(self):
        request = storjnode.network.info.create_request(
            self.btctxstore, self.wif
        )

        # test create

        peers = [binascii.unhexlify("deadbeef" * 5)] * 20
        created = storjnode.network.info.create_response(
            self.btctxstore, self.wif, request, 3, 2, 1, peers
        )

        # check package data < min package size
        packed = umsgpack.packb(created)
        self.assertLessEqual(len(packed), storjnode.common.MAX_PACKAGE_DATA)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        # test read
        read = storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        )
        self.assertIsNotNone(read)
        self.assertEqual(created, read)


if __name__ == "__main__":
    unittest.main()
