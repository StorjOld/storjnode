import os
import filecmp
import shutil
import unittest
import tempfile
import storjnode


SHARD_PATH = storjnode.util.full_path(
    os.path.join(os.path.dirname(__file__), "test.shard")
)


class MockShard(object):

    def __init__(self, size=0, data=b""):
        self._size = size
        self._data = data

    def seek(self, *args, **kwargs):
        pass

    def read(self, *args, **kwargs):
        return self._data

    def tell(self, *args, **kwargs):
        return self._size


class TestManager(unittest.TestCase):

    def setUp(self):
        assert(os.path.isfile(SHARD_PATH))
        self.base_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.base_dir)

    def test_setup(self):
        alpha_path = os.path.join(self.base_dir, "alpha")
        beta_path = os.path.join(self.base_dir, "beta")
        gamma_path = os.path.join(self.base_dir, "gamma")
        store_config = {
            alpha_path: {"limit": 2**24, "use_folder_tree": True},  # 16M
            beta_path: {"limit": 2**64},  # 16777216T
            gamma_path: None,
        }
        normalized = storjnode.storage.manager.setup(store_config)

        # check directories created
        for path in normalized.keys():
            self.assertTrue(os.path.isdir(path))

        # preserves valid limit
        self.assertEqual(normalized[alpha_path]["limit"], 2**24)

        # preserves valid use_folder_tree
        self.assertEqual(normalized[alpha_path]["use_folder_tree"], True)

        # reajusts limit if gt free space
        self.assertTrue(0 < normalized[beta_path]["limit"] < 2**64)

        # returns normalized paths
        self.assertEqual(normalized[gamma_path]["limit"], 0)
        self.assertEqual(normalized[gamma_path]["use_folder_tree"], False)

    def test_add(self):
        with open(SHARD_PATH, "rb") as shard:

            # test success
            store_path = os.path.join(self.base_dir, "delta")
            store_config = {store_path: None}
            save_path = storjnode.storage.manager.add(store_config, shard)
            self.assertTrue(os.path.isfile(save_path))
            self.assertTrue(save_path.startswith(store_path))
            self.assertTrue(filecmp.cmp(SHARD_PATH, save_path))

            # checks for existing file and skip if already added
            store_path_b = storjnode.storage.manager.add(store_config, shard)
            self.assertEqual(save_path, store_path_b)

            # check limit reached
            def callback():
                store_path = os.path.join(self.base_dir, "epsilon")
                store_config = {store_path: {"limit": 1}}
                storjnode.storage.manager.add(store_config, shard)
            self.assertRaises(MemoryError, callback)

            # check not enough disc space
            def callback():
                mock_shard = MockShard(size=2**64)  # 16777216T
                store_path = os.path.join(self.base_dir, "zeta")
                storjnode.storage.manager.add({store_path: None}, mock_shard)
            self.assertRaises(MemoryError, callback)

            # check use_folder_tree
            store_path = os.path.join(self.base_dir, "iota")
            store_config = {store_path: {"use_folder_tree": True}}
            save_path = storjnode.storage.manager.add(store_config, shard)
            relative_path = save_path[len(store_path)+1:]
            self.assertEqual(len(relative_path.split(os.path.sep)), 23)

    def test_remove(self):
        with open(SHARD_PATH, "rb") as shard:
            store_path = os.path.join(self.base_dir, "eta")
            save_path = storjnode.storage.manager.add(
                {store_path: None}, shard
            )
            self.assertTrue(os.path.isfile(save_path))  # shard added
            shard_id = storjnode.storage.shard.get_id(shard)
            storjnode.storage.manager.remove({store_path: None}, shard_id)
            self.assertFalse(os.path.isfile(save_path))  # shard removed

    def test_get(self):

        # test success
        store_config = {os.path.join(self.base_dir, "theta"): None}
        with open(SHARD_PATH, "rb") as shard:
            storjnode.storage.manager.add(store_config, shard)
            id = storjnode.storage.shard.get_id(shard)
            with storjnode.storage.manager.open(store_config, id) as retreived:
                shard.seek(0)
                self.assertEqual(shard.read(), retreived.read())

        # test failure
        def callback():
            storjnode.storage.manager.open(store_config, "deadbeef" * 8)
        self.assertRaises(KeyError, callback)


if __name__ == "__main__":
    unittest.main()
