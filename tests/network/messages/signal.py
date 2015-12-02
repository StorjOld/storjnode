import unittest
import umsgpack
import storjnode
import btctxstore
from storjnode.network.messages import base
from storjnode.network.messages import signal


class TestNetworkMessagesSignal(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)
        self.nodeid = storjnode.util.address_to_node_id(self.address)

    def test_create_read(self):

        # test create
        created = signal.create(self.btctxstore, self.wif, "test")

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        # test read
        read = signal.read(self.btctxstore, repacked, "test")
        self.assertIsNotNone(read)
        self.assertEqual(created, read)

    def test_invalid_message(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        repacked[0] = "invalidnodeid"

        self.assertIsNone(signal.read(self.btctxstore, self.nodeid, repacked))

    def test_invalid_token(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        repacked[2] = "invalidtoken"

        self.assertIsNone(signal.read(self.btctxstore, self.nodeid, repacked))

    def test_invalid_name(self):
        created = signal.create(self.btctxstore, self.wif, "test")

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(signal.read(self.btctxstore, repacked, "wrongname"))


if __name__ == "__main__":
    unittest.main()
