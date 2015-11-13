import os
import filecmp
import tempfile
import unittest
import storjnode


SHARD_PATH = storjnode.util.full_path(
    os.path.join(os.path.dirname(__file__), "test.shard")
)


class TestShard(unittest.TestCase):

    def setUp(self):
        assert(os.path.isfile(SHARD_PATH))
        self.shard = open(SHARD_PATH, "rb")

    def tearDown(self):
        self.shard.close()

    def test_valid_id(self):

        # test success
        h = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        self.assertTrue(storjnode.storage.shard.valid_id(h))

        # test to short
        h = "c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        self.assertFalse(storjnode.storage.shard.valid_id(h))

        # test to long
        h = "a2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        self.assertFalse(storjnode.storage.shard.valid_id(h))

        # non hex char
        h = "g2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        self.assertFalse(storjnode.storage.shard.valid_id(h))

    def test_get_size(self):
        size = storjnode.storage.shard.get_size(self.shard)
        self.assertEqual(size, 1024)  # 1K

    def test_get_id(self):
        # expected hash h obtained from sha256sum (GNU coreutils 8.21)
        h = "61f21f335c9ef06cac682c0b4de8a8786883e15adea8546bf8ff1dff000189d3"
        result = storjnode.storage.shard.get_id(self.shard)
        self.assertEqual(result, h)

    def test_get_hash_normal(self):
        # expected hash h obtained from sha256sum (GNU coreutils 8.21)
        h = "61f21f335c9ef06cac682c0b4de8a8786883e15adea8546bf8ff1dff000189d3"
        result = storjnode.storage.shard.get_hash(self.shard)
        self.assertEqual(result, h)

    def test_get_hash_salted(self):
        # expected hash h obtained from sha256sum (GNU coreutils 8.21)
        h = "24847a228d9cd64c2aa511d49f084c0e3ca607bc92f238e25d785261d9e3842e"
        result = storjnode.storage.shard.get_hash(self.shard, salt=b"salt")
        self.assertEqual(result, h)

    def test_save(self):
        save_path = tempfile.mktemp()
        storjnode.storage.shard.save(self.shard, save_path)
        filecmp.cmp(SHARD_PATH, save_path)
        os.remove(save_path)


if __name__ == "__main__":
    unittest.main()
