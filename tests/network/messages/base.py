import unittest
import umsgpack
import btctxstore
from storjnode.network.messages import base


class TestNetworkMessagesBase(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.btctxstore.create_key()

    def test_create_read(self):

        # test create
        created = base.create(self.btctxstore, self.wif, "token", "body")

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        # test read
        read = base.read(self.btctxstore, repacked)
        self.assertIsNotNone(read)
        self.assertEqual(created, read)

    def test_read_invalid_message_type(self):
        self.assertIsNone(base.read(self.btctxstore, None))

    def test_read_invalid_message_len(self):
        self.assertIsNone(base.read(self.btctxstore, []))

    def test_read_invalid_nodeid_type(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        repacked[0] = None

        self.assertIsNone(base.read(self.btctxstore, repacked))

    def test_read_invalid_nodeid_len(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        repacked[0] = "invalidnodeidlen"

        self.assertIsNone(base.read(self.btctxstore, repacked))

    def test_read_invalid_version_type(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        repacked[1] = None

        self.assertIsNone(base.read(self.btctxstore, repacked))

    def test_read_invalid_version_value(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        repacked[1] = -1

        self.assertIsNone(base.read(self.btctxstore, repacked))

    def test_read_invalid_signature_type(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        repacked[4] = None

        self.assertIsNone(base.read(self.btctxstore, repacked))

    def test_read_invalid_signature_value(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        repacked[4] = "invalidsignaturelen"

        self.assertIsNone(base.read(self.btctxstore, repacked))

    def test_read_invalid_signature(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        repacked[4] = "x" * 65

        self.assertIsNone(base.read(self.btctxstore, repacked))


if __name__ == "__main__":
    unittest.main()
