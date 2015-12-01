import unittest
import umsgpack
import storjnode
import btctxstore
from collections import OrderedDict


class TestNetworkMessage(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        self.wif = self.btctxstore.create_key()

    def test_signing(self):
        # Check sig using our wif to get the address.
        msg = OrderedDict({"type": "test"})
        signed_msg = storjnode.network.message.sign(msg, self.wif)
        self.assertTrue(storjnode.network.message.verify_signature(
            signed_msg, self.wif
        ))

        # Check sig using node ID to get the address.
        address = self.btctxstore.get_address(self.wif)
        node_id = storjnode.util.address_to_node_id(address)
        self.assertTrue(storjnode.network.message.verify_signature(
            signed_msg, self.wif, node_id
        ))

    def test_creat_validate(self):

        # test create
        created = storjnode.network.message.create(
            self.btctxstore, self.wif, "testbody"
        )

        # check package data < min package size
        packed = umsgpack.packb(created)
        self.assertLessEqual(len(packed), storjnode.common.MAX_PACKAGE_DATA)

        # repack to eliminate namedtuples and simulate io
        repacked = umsgpack.unpackb(packed)

        # test read
        read = storjnode.network.message.read(self.btctxstore, repacked)
        self.assertIsNotNone(read)
        self.assertEqual(created, read)


if __name__ == "__main__":
    unittest.main()