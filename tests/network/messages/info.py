import unittest
import umsgpack
import storjnode
import btctxstore
from storjnode.network.messages import info
from storjnode.network.messages import base


class TestInfo(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)
        self.nodeid = storjnode.util.address_to_node_id(self.address)

    def test_create_read(self):

        # test create
        capacity = {"total": 1024 ** 6, "used": 1024 ** 6, "free": 0}
        transport = ["127.0.0.1", 1337]
        created = info.create(self.btctxstore, self.wif,
                              capacity, transport, True)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        # test read
        read = info.read(self.btctxstore, repacked)
        self.assertIsNotNone(read)
        self.assertEqual(created, read)

    def test_invalid_token(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_info_type(self):
        created = base.create(self.btctxstore, self.wif, "info", None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_info_len(self):
        created = base.create(self.btctxstore, self.wif, "info", [])

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_version_type(self):
        _info = [None, None, None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_version_value(self):
        _info = ["invalidversion", None, None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_storage_type(self):
        _info = ["0.0.0", None, None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_storage_len(self):
        _info = ["0.0.0", [], None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_storage_value_types(self):
        _info = ["0.0.0", [None, 0, 0], None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_storage_values(self):
        _info = ["0.0.0", [-1, 0, 0], None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_storage_used_gt_total(self):
        _info = ["0.0.0", [1, 2, 0], None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_storage_impossable(self):
        _info = ["0.0.0", [2, 1, 0], None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_network_type(self):
        _info = ["0.0.0", [2, 1, 1], None]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_network_len(self):
        _info = ["0.0.0", [2, 1, 1], []]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_network_is_public_type(self):
        _info = ["0.0.0", [2, 1, 1], [None, None]]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_network_transport_type(self):
        _info = ["0.0.0", [2, 1, 1], [None, True]]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_network_transport_len(self):
        _info = ["0.0.0", [2, 1, 1], [[], True]]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_network_ip(self):
        _info = ["0.0.0", [2, 1, 1], [["invalid", None], True]]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))

    def test_invalid_network_port(self):
        _info = ["0.0.0", [2, 1, 1], [["127.0.0.1", None], True]]
        created = base.create(self.btctxstore, self.wif, "info", _info)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(info.read(self.btctxstore, repacked))


if __name__ == "__main__":
    unittest.main()
