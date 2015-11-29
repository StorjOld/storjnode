import unittest
import storjnode
try:
    from Queue import Queue  # py2
except ImportError:
    from queue import Queue  # py3


class TestValidIP(unittest.TestCase):

    def test_ipv4(self):
        ip = "127.0.0.1"
        self.assertTrue(storjnode.util.valid_ip(ip))

    def test_ipv6_full(self):
        ip = "FE80:0000:0000:0000:0202:B3FF:FE1E:8329"
        self.assertTrue(storjnode.util.valid_ip(ip))

    def test_ipv6_collapsed(self):
        ip = "2001:db8::1"
        self.assertTrue(storjnode.util.valid_ip(ip))

    def test_no_localhost(self):
        ip = "localhost"
        self.assertFalse(storjnode.util.valid_ip(ip))

    def test_no_domain(self):
        ip = "test.net"
        self.assertFalse(storjnode.util.valid_ip(ip))


class TestValidIPv4(unittest.TestCase):

    def test_ipv4(self):
        ip = "127.0.0.1"
        self.assertTrue(storjnode.util.valid_ipv4(ip))

    def test_ipv6_full(self):
        ip = "FE80:0000:0000:0000:0202:B3FF:FE1E:8329"
        self.assertFalse(storjnode.util.valid_ipv4(ip))

    def test_ipv6_collapsed(self):
        ip = "2001:db8::1"
        self.assertFalse(storjnode.util.valid_ipv4(ip))

    def test_no_localhost(self):
        ip = "localhost"
        self.assertFalse(storjnode.util.valid_ipv4(ip))

    def test_no_domain(self):
        ip = "test.net"
        self.assertFalse(storjnode.util.valid_ipv4(ip))


class TestValidIPv6(unittest.TestCase):

    def test_ipv4(self):
        ip = "127.0.0.1"
        self.assertFalse(storjnode.util.valid_ipv6(ip))

    def test_ipv6_full(self):
        ip = "FE80:0000:0000:0000:0202:B3FF:FE1E:8329"
        self.assertTrue(storjnode.util.valid_ipv6(ip))

    def test_ipv6_collapsed(self):
        ip = "2001:db8::1"
        self.assertTrue(storjnode.util.valid_ipv6(ip))

    def test_no_localhost(self):
        ip = "localhost"
        self.assertFalse(storjnode.util.valid_ipv6(ip))

    def test_no_domain(self):
        ip = "test.net"
        self.assertFalse(storjnode.util.valid_ipv6(ip))


class TestChunks(unittest.TestCase):

    def test_chunks(self):
        result = storjnode.util.chunks([1, 2, 3, 4, 5, 6, 7, 8, 9], 2)
        expected = [[1, 2], [3, 4], [5, 6], [7, 8], [9]]
        self.assertEqual(result, expected)


class TestBaskets(unittest.TestCase):

    def test_baskets(self):
        result = storjnode.util.baskets([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 3)
        expected = [[1, 4, 7, 10], [2, 5, 8], [3, 6, 9]]
        self.assertEqual(result, expected)


class TestEmptyQueue(unittest.TestCase):

    def test_empty_queue(self):
        q = Queue()
        q.put(1)
        q.put(2)
        l = storjnode.util.empty_queue(q)
        self.assertEqual(l, [1, 2])  # emptied in correct order
        self.assertTrue(q.empty())  # queue now empty


class TestEnsurePathExists(unittest.TestCase):

    def test_creates_for_nonexisting(path):
        pass  # TODO test

    def test_uses_existing(path):
        pass  # TODO test

    def test_error_if_file(path):
        pass  # TODO test

    def test_error_if_not_readable(path):
        pass  # TODO test

    def test_error_if_not_writable(path):
        pass  # TODO test

    def test_error_if_not_searchable(path):
        pass  # TODO test


if __name__ == "__main__":
    unittest.main()
