import unittest
import storjnode


class TestShard(unittest.TestCase):

    def setUp(self):
        # TODO create file
        path = "TODO path"
        self.shard = open(path, "rb")

    def tearDown(self):
        self.shard.close()
        # TODO delete file

    def test_get_size(self):
        size = storjnode.storage.shard.get_size(self.shard)
        self.assertEqual(size, 1024 * 1024)

    def test_get_id(self):
        expected = "TODO get expected id"
        shard_id = storjnode.storage.shard.get_id(self.shard)
        self.assertEqual(shard_id, expected)

    def test_get_hash_normal(self):
        expected = "TODO get expected hash"
        shard_hash = storjnode.storage.shard.get_hash(self.shard)
        self.assertEqual(shard_hash, expected)

    def test_get_hash_salted(self):
        expected = "TODO get expected hash"
        shard_hash = storjnode.storage.shard.get_hash(self.shard, salt=b"salt")
        self.assertEqual(shard_hash, expected)

    def test_save(self):
        pass  # TODO implement


if __name__ == "__main__":
    unittest.main()
