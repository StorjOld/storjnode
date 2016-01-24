import unittest
import time
from storjnode.storage.dht import Storage


class TestStorage(unittest.TestCase):

    def test_dict(self):
        store = Storage()
        store["foo"] = "bar"
        self.assertEqual(store["foo"], "bar")

    def test_ttl(self):
        store = Storage(ttl=2)
        store["foo"] = "bar"
        self.assertEqual(store["foo"], "bar")
        time.sleep(3)
        self.assertEqual(store.get("foo"), None)

    def test_entry_limit(self):
        store = Storage(entry_limit=2)
        store["foo"] = "foo"
        store["bar"] = "bar"
        store["baz"] = "baz"
        self.assertEqual(store.get("foo"), None)
        self.assertEqual(store.get("bar"), "bar")
        self.assertEqual(store.get("baz"), "baz")

    def test_max_entry_size(self):
        store = Storage(max_entry_size=512)
        store["under_limit"] = 511 * "x"
        store["at_limit"] = 512 * "x"
        store["over_limit"] = 513 * "x"


if __name__ == "__main__":
    unittest.main()
