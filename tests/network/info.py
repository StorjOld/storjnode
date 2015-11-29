import unittest
import umsgpack
import storjnode
import btctxstore


class TestInfo(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.btctxstore.create_key()
        self.address = self.btctxstore.get_address(self.wif)

    def test_create_read_request(self):
        created = storjnode.network.info.create_request(
            self.btctxstore, self.wif
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        read = storjnode.network.info.read_request(self.btctxstore, repacked)
        self.assertIsNotNone(read)
        self.assertEqual(created, read)

    @unittest.skip("broken")
    def test_create_read_response(self):
        request = storjnode.network.info.create_request(
            self.btctxstore, self.wif
        )
        created = storjnode.network.info.create_response(
            self.btctxstore, self.wif, request, 3, 2, 1, []
        )
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        read = storjnode.network.info.read_respones(
            self.btctxstore, self.address, repacked
        )
        self.assertIsNotNone(read)
        self.assertEqual(created, read)


if __name__ == "__main__":
    unittest.main()
