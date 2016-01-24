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

        under_limit = 508 * "x"  # - 3 byte msgpack overhead
        at_limit = 509 * "x"  # - 3 byte msgpack overhead
        over_limit = 510 * "x"  # - 3 byte msgpack overhead
        store = Storage(max_entry_size=512)
        store["under_limit"] = under_limit
        store["at_limit"] = at_limit
        store["over_limit"] = over_limit
        self.assertEqual(store.get("under_limit"), under_limit)
        self.assertEqual(store.get("at_limit"), at_limit)
        self.assertEqual(store.get("over_limit"), None)


if __name__ == "__main__":
    unittest.main()
