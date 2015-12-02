import unittest
import umsgpack
import storjnode
import btctxstore
from storjnode.network.messages import info


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


if __name__ == "__main__":
    unittest.main()
