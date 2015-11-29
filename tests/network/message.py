import unittest
import storjnode
import btctxstore
from collections import OrderedDict


class TestSigning(unittest.TestCase):

    def test_signing(self):
        # Check sig using our wif to get the address.
        api = btctxstore.BtcTxStore(testnet=False, dryrun=True)
        wif = api.get_key(api.create_wallet())
        msg = OrderedDict({"type": "test"})
        signed_msg = storjnode.network.message.sign(msg, wif)
        assert(storjnode.network.message.verify_signature(signed_msg, wif))

        # Check sig using node ID to get the address.
        address = api.get_address(wif)
        node_id = storjnode.util.address_to_node_id(address)
        assert(storjnode.network.message.verify_signature(signed_msg, wif,
                                                          node_id))


if __name__ == "__main__":
    unittest.main()
