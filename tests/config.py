import os
import copy
import unittest
import tempfile
import storjnode
import btctxstore


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()

    def test_roundtrip_unencrypted(self):
        path = tempfile.mktemp()
        saved_data = storjnode.config.create(self.btctxstore, path)
        loaded_data = storjnode.config.get(self.btctxstore, path)
        self.assertEqual(saved_data, loaded_data)
        os.remove(path)

    def test_save_overwrites(self):
        path = tempfile.mktemp()

        # create config
        created_data = storjnode.config.create(self.btctxstore, path)

        # update config
        updated_data = copy.deepcopy(created_data)
        updated_data["payout_address"] = "1A8WqiJDh3tGVeEefbMN5BVDYxx2XSoWgG"
        storjnode.config.save(self.btctxstore, path, updated_data)

        # confirm overwriten
        loaded_data = storjnode.config.get(self.btctxstore, path)
        self.assertEqual(updated_data, loaded_data)
        os.remove(path)

    def test_password_validation(self):
        pass  # TODO implement

    def test_validation(self):
        wallet = self.btctxstore.create_wallet()
        key = self.btctxstore.get_key(wallet)
        address = self.btctxstore.get_address(key)

        # must be a dict
        def callback():
            storjnode.config.validate(self.btctxstore, None)
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # must have the correct version
        def callback():
            storjnode.config.validate(self.btctxstore, {
                "payout_address": address,
                "wallet": wallet,
            })
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # must have a valid payout address
        def callback():
            storjnode.config.validate(self.btctxstore, {
                "version": storjnode.config.__version__,
                "wallet": wallet,
            })
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # must have a valid wallet
        def callback():
            storjnode.config.validate(self.btctxstore, {
                "version": storjnode.config.__version__,
                "payout_address": address,
            })
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # valid config
        self.assertTrue(storjnode.config.validate(self.btctxstore, {
            "version": storjnode.config.__version__,
            "payout_address": address,
            "wallet": wallet,
        }))

    def test_migrate(self):
        path = tempfile.mktemp()

        # initial unmigrated 2.0.0 config
        cfg = {
            "version": "2.0.0",
            "master_secret": "test_master_secret",
            "payout_address": "1A8WqiJDh3tGVeEefbMN5BVDYxx2XSoWgG",
        }

        # test its invalid with current build
        def callback():
            storjnode.config.validate(self.btctxstore, cfg)
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # migrate
        cfg = storjnode.config.migrate(self.btctxstore, path, cfg)

        # test its now valid
        self.assertTrue(storjnode.config.validate(self.btctxstore, cfg))


if __name__ == '__main__':
    unittest.main()
