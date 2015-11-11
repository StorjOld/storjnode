import os
import filecmp
import shutil
import unittest
import tempfile
import storjnode


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
        self.test_shard_path = os.path.join("tests", "test.shard")
        self.base_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.base_dir)

    def test_setup(self):
        alpha_path = os.path.join(self.base_dir, "alpha")
        beta_path = os.path.join(self.base_dir, "beta")
        gamma_path = os.path.join(self.base_dir, "gamma")
        store_paths = {
            alpha_path: {"limit": 2**24, "use_folder_tree": True},  # 16M
            beta_path: {"limit": 2**64},  # 16777216T
            gamma_path: None,
        }
        normalized = storjnode.storage.manager.setup(store_paths)

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
        with open(self.test_shard_path, "rb") as shard:

            # test success
            store_path = os.path.join(self.base_dir, "delta")
            save_path = storjnode.storage.manager.add({store_path: None}, shard)
            self.assertTrue(os.path.isfile(save_path))
            self.assertTrue(save_path.startswith(store_path))
            self.assertTrue(filecmp.cmp(self.test_shard_path, save_path))

            # check limit reached
            def callback():
                store_path = os.path.join(self.base_dir, "epsilon")
                store_paths = {store_path: {"limit": 1}}
                storjnode.storage.manager.add(store_paths, shard)
            self.assertRaises(MemoryError, callback)

            # check not enough disc space
            def callback():
                mock_shard = MockShard(size=2**64)  # 16777216T
                store_path = os.path.join(self.base_dir, "zeta")
                storjnode.storage.manager.add({store_path: None}, mock_shard)
            self.assertRaises(MemoryError, callback)

    def test_remove(self):
        with open(self.test_shard_path, "rb") as shard:
            store_path = os.path.join(self.base_dir, "eta")
            save_path = storjnode.storage.manager.add({store_path: None}, shard)
            self.assertTrue(os.path.isfile(save_path))  # shard added
            shard_id = storjnode.storage.shard.get_id(shard)
            storjnode.storage.manager.remove({store_path: None}, shard_id)
            self.assertFalse(os.path.isfile(save_path))  # shard removed

    def test_get(self):

        # test success
        store_paths = {os.path.join(self.base_dir, "theta"): None}
        with open(self.test_shard_path, "rb") as shard:
            storjnode.storage.manager.add(store_paths, shard)
            shard_id = storjnode.storage.shard.get_id(shard)
            retreived = storjnode.storage.manager.get(store_paths, shard_id)
            try:
                shard.seek(0)
                self.assertEqual(shard.read(), retreived.read())
            finally:
                retreived.close()

        # test failure
        def callback():
            shard_id = "deadbeef" * 8
            storjnode.storage.manager.get(store_paths, shard_id)
        self.assertRaises(KeyError, callback)


if __name__ == "__main__":
    unittest.main()
