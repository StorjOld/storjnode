import os
import shutil
import unittest
import tempfile
import storjnode


class TestManager(unittest.TestCase):

    def setUp(self):
        self.base_dir = tempfile.mkdtemp()
        self.alpha_path = os.path.join(self.base_dir, "alpha")
        self.beta_path = os.path.join(self.base_dir, "beta")
        self.gamma_path = os.path.join(self.base_dir, "gamma")
        self.store_paths = {
            self.alpha_path: {"limit": 2**24},  # 16M
            self.beta_path: {"limit": 2**48},  # 256T
            self.gamma_path: None,
        }

    def tearDown(self):
        shutil.rmtree(self.base_dir)

    def test_setup(self):
        normalized = storjnode.storage.manager.setup(self.store_paths)

        # check directories created
        for path in normalized.keys():
            self.assertTrue(os.path.isdir(path))

        # preserves valid limit
        self.assertEqual(normalized[self.alpha_path]["limit"], 2**24)

        # reajusts limit if gt free space
        self.assertTrue(0 < normalized[self.beta_path]["limit"] < 2**64)

        # returns normalized paths
        self.assertEqual(normalized[self.gamma_path]["limit"], 0)
        self.assertEqual(normalized[self.gamma_path]["use_folder_tree"], False)


if __name__ == "__main__":
    unittest.main()
