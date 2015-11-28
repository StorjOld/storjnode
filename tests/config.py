import os
import json
import copy
import unittest
import tempfile
import storjnode
import btctxstore


# initial unmigrated 2.0.0 config
UNMIGRATED_CONFIG = {
    "version": "2.0.0",
    "master_secret": "test_master_secret",
    "payout_address": "1A8WqiJDh3tGVeEefbMN5BVDYxx2XSoWgG",
}


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()

    def test_roundtrip_unencrypted(self):
        path = tempfile.mktemp()
        try:
            cfg = storjnode.config.create(self.btctxstore)
            saved_data = storjnode.config.save(self.btctxstore, path, cfg)
            loaded_cfg = storjnode.config.read(path)
            self.assertEqual(saved_data, loaded_cfg)
        finally:
            os.remove(path)

    def test_save_overwrites(self):
        path = tempfile.mktemp()
        try:

            # create config
            cfg = storjnode.config.create(self.btctxstore)
            created_data = storjnode.config.save(self.btctxstore, path, cfg)

            # update config
            updated_cfg = copy.deepcopy(created_data)
            address = "1A8WqiJDh3tGVeEefbMN5BVDYxx2XSoWgG"
            updated_cfg["payout_address"] = address
            storjnode.config.save(self.btctxstore, path, updated_cfg)

            # confirm overwriten
            loaded_cfg = storjnode.config.read(path)
            self.assertEqual(updated_cfg, loaded_cfg)
        finally:
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
                "version": storjnode.config.VERSION,
                "wallet": wallet,
            })
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # must have a valid wallet
        def callback():
            storjnode.config.validate(self.btctxstore, {
                "version": storjnode.config.VERSION,
                "payout_address": address,
            })
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # valid config
        self.assertTrue(storjnode.config.validate(self.btctxstore, {
            "version": storjnode.config.VERSION,
            "payout_address": address,
            "wallet": wallet,
        }))

    def test_create_always_valid(self):
        cfg = storjnode.config.create(self.btctxstore)
        self.assertTrue(storjnode.config.validate(self.btctxstore, cfg))

    def test_get_loads_config(self):
        path = tempfile.mktemp()
        try:
            cfg = storjnode.config.create(self.btctxstore)
            created_cfg = storjnode.config.save(self.btctxstore, path, cfg)
            loaded_cfg = storjnode.config.get(self.btctxstore, path)
            self.assertEqual(created_cfg, loaded_cfg)
        finally:
            os.remove(path)

    def test_get_creates_default_config(self):
        path = tempfile.mktemp()
        try:
            created_cfg = storjnode.config.get(self.btctxstore, path)
            loaded_cfg = storjnode.config.read(path)
            self.assertEqual(created_cfg, loaded_cfg)
        finally:
            os.remove(path)

    def test_get_migrates_if_needed(self):
        path = tempfile.mktemp()
        try:
            # save unmigrated config
            with open(path, 'w') as fp:
                fp.write(json.dumps(UNMIGRATED_CONFIG))

            # loaded config is migrated and valid
            loaded = storjnode.config.get(self.btctxstore, path)
            self.assertTrue(storjnode.config.validate(self.btctxstore, loaded))

            # check if it was saved
            saved = storjnode.config.read(path)
            self.assertEqual(loaded, saved)
        finally:
            os.remove(path)

    def test_migrate(self):

        # test its invalid with current build
        def callback():
            storjnode.config.validate(self.btctxstore, UNMIGRATED_CONFIG)
        self.assertRaises(storjnode.config.InvalidConfig, callback)

        # migrate
        cfg = storjnode.config.migrate(self.btctxstore, UNMIGRATED_CONFIG)

        # test its now valid
        self.assertTrue(storjnode.config.validate(self.btctxstore, cfg))


if __name__ == '__main__':
    unittest.main()
