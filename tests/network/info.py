import os
import unittest
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
        # test create
        peers = [os.urandom(20) for i in range(20)]
        created = storjnode.network.info.create_response(
            self.btctxstore, self.wif, 3, 2, peers
        )

        # check package data < min package size
        packed = umsgpack.packb(created)
        self.assertLessEqual(len(packed), storjnode.common.MAX_PACKAGE_DATA)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(packed)

        # test read
        read = storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        )
        self.assertIsNotNone(read)
        self.assertEqual(created, read)

    def test_invalid_info_message(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, None
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        repacked[0] = "invalidnodeid"

        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_body_type(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, "invalidbodytype"
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_body_len(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, []
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_capacity_type(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, ["0.0.0", "total", "used", b""]
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_capacity_value(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, ["0.0.0", -1, -1, b""]
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_capacity_impossable(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, ["0.0.0", 1, 2, b""]
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_peer_type(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, ["0.0.0", 2, 1, u""]
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_peer_len(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, ["0.0.0", 2, 1, b"invalid"]
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

    def test_invalid_info_version_type(self):
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, [1, 2, 1, b"invalid"]
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        self.assertIsNone(storjnode.network.info.read_respones(
            self.btctxstore, self.nodeid, repacked
        ))

if __name__ == "__main__":
    unittest.main()
