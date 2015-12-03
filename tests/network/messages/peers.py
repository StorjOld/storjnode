import os
import unittest
import umsgpack
import btctxstore
from storjnode.network.messages import base
from storjnode.network.messages import peers


class TestNetworkMessagesPeers(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.btctxstore.create_key()

    def test_create_read(self):
        # test create
        created = peers.create(
            self.btctxstore, self.wif, [os.urandom(20) for i in range(20)]
        )

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        # test read
        read = peers.read(self.btctxstore, repacked)
        self.assertIsNotNone(read)
        self.assertEqual(created, read)

    def test_invalid_message(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))
        repacked[0] = "invalidnodeid"

        self.assertIsNone(peers.read(self.btctxstore, repacked))

    def test_invalid_token(self):
        created = base.create(self.btctxstore, self.wif, None, None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(peers.read(self.btctxstore, repacked))

    def test_invalid_peer_type(self):
        created = base.create(self.btctxstore, self.wif, "peers", None)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(peers.read(self.btctxstore, repacked))

    def test_invalid_peer_len(self):
        created = base.create(
            self.btctxstore,
            self.wif,
            "peers",
            b"invalidlen"
        )

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(umsgpack.packb(created))

        self.assertIsNone(peers.read(self.btctxstore, repacked))


if __name__ == "__main__":
    unittest.main()
