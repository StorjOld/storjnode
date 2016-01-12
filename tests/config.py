import os
import json
import copy
import unittest
import tempfile
import storjnode
from jsonschema.exceptions import ValidationError


class TestConfig(unittest.TestCase):

    def test_roundtrip_unencrypted(self):
        path = tempfile.mktemp()
        try:
            cfg = storjnode.config.create()
            saved_data = storjnode.config.save(path, cfg)
            loaded_cfg = storjnode.config.read(path)
            self.assertEqual(saved_data, loaded_cfg)
        finally:
            os.remove(path)

    def test_save_overwrites(self):
        path = tempfile.mktemp()
        try:

            # create config
            cfg = storjnode.config.create()
            created_data = storjnode.config.save(path, cfg)

            # update config
            updated_cfg = copy.deepcopy(created_data)
            address = "1A8WqiJDh3tGVeEefbMN5BVDYxx2XSoWgG"
            updated_cfg["cold_storage"].append(address)
            storjnode.config.save(path, updated_cfg)

            # confirm overwriten
            loaded_cfg = storjnode.config.read(path)
            self.assertEqual(updated_cfg, loaded_cfg)
        finally:
            os.remove(path)

    def test_password_validation(self):
        pass  # TODO implement

    def test_validation(self):

        # default config must validate
        cfg = storjnode.config.create()
        storjnode.config.validate(cfg)

        # check bootstrap nodes
        bootstrap_nodes = storjnode.network.node.DEFAULT_BOOTSTRAP_NODES
        cfg["network"]["bootstrap_nodes"] = bootstrap_nodes
        storjnode.config.validate(cfg)

        # TODO tests for every property and type

    def test_create_always_valid(self):
        cfg = storjnode.config.create()
        self.assertTrue(storjnode.config.validate(cfg))

    def test_get_loads_config(self):
        path = tempfile.mktemp()
        try:
            cfg = storjnode.config.create()
            created_cfg = storjnode.config.save(path, cfg)
            loaded_cfg = storjnode.config.get(path)
            self.assertEqual(created_cfg, loaded_cfg)
        finally:
            os.remove(path)

    def test_get_creates_default_config(self):
        path = tempfile.mktemp()
        try:
            created_cfg = storjnode.config.get(path)
            loaded_cfg = storjnode.config.read(path)
            self.assertEqual(created_cfg, loaded_cfg)
        finally:
            os.remove(path)

    def test_get_migrates_if_needed(self):
        path = tempfile.mktemp()
        try:
            # save unmigrated config
            with open(path, 'w') as fp:
                fp.write(json.dumps(storjnode.config.UNMIGRATED_CONFIG))

            # loaded config is migrated and valid
            loaded = storjnode.config.get(path)
            self.assertTrue(storjnode.config.validate(loaded))

            # check if it was saved
            saved = storjnode.config.read(path)
            self.assertEqual(loaded, saved)
        finally:
            os.remove(path)

    def test_migrate(self):

        # test its invalid with current build
        def callback():
            storjnode.config.validate(storjnode.config.UNMIGRATED_CONFIG)
        self.assertRaises(ValidationError, callback)

        # migrate
        cfg = storjnode.config.migrate(storjnode.config.UNMIGRATED_CONFIG)

        # test its now valid
        self.assertTrue(storjnode.config.validate(cfg))


if __name__ == '__main__':
    unittest.main()
