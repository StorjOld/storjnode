import unittest
import storjnode
import time
from storjnode.network.bandwidth.limit import BandwidthLimit
from storjnode.config import ConfigFile

_log = storjnode.log.getLogger(__name__)
timed_out = 0


def patch_time(value):
    def return_value():
        return value

    time.time = return_value


class TestLimit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bandwidth = BandwidthLimit()

    def tearDown(self):
        # Reset bandwidth limits.
        self.bandwidth.limit(0)

        # Reset usage states.
        self.bandwidth.reset_usage()

        # Reset cake no.
        self.bandwidth.cake["upstream"]["no"] = -1
        self.bandwidth.cake["downstream"]["no"] = -1

        # Reset transfers.
        self.bandwidth.transfers = set()

        # Reset next month timestamp.
        self.bandwidth.next_month = 0

        # Reset scale factor.
        self.bandwidth.cake_scale = 0.95

    def test_limit(self):
        self.bandwidth.limit(1025, "sec", "upstream")
        self.assertTrue(
            self.bandwidth.info["sec"]["upstream"]["limit"] == 1025
        )

    def test_slice_remainder(self):
        limit = 1025
        cake_size = int(limit * 0.95)

        self.bandwidth.limit(1025, "sec", "upstream")
        self.bandwidth.register_transfer("slice_1")
        self.bandwidth.register_transfer("slice_2")
        allowance = self.bandwidth.request("upstream", "slice_1")
        expected = int(cake_size / 2) + int(cake_size % 2)
        self.assertTrue(allowance == expected)

        allowance = self.bandwidth.request("upstream", "slice_2")
        expected = int(cake_size / 2)
        self.assertTrue(allowance == expected)

    def test_monthly_limit(self):
        self.bandwidth.limit(2000, "month", "upstream")
        self.bandwidth.update("upstream", 2000)
        self.assertTrue(self.bandwidth.request("upstream") == 0)

    def test_bandwidth_overflow(self):
        self.bandwidth.limit(2000, "sec", "upstream")
        self.bandwidth.request("upstream")
        self.bandwidth.update("upstream", 4000)
        self.assertTrue(self.bandwidth.request("upstream") == 0)

    def test_monthly_time_works(self):
        self.bandwidth.info["month"]["upstream"]["limit"] = 100
        self.bandwidth.info["month"]["upstream"]["used"] = 100
        self.bandwidth.next_month = time.time() - 100
        self.assertTrue(self.bandwidth.request("upstream") != 0)

    def test_use_non_reserved_non_transfer(self):
        self.bandwidth.register_transfer("slice_1")
        self.bandwidth.limit(2000, "sec", "upstream")

        # Bake cake.
        self.bandwidth.request("upstream")

        # Set overflow.
        self.bandwidth.update("upstream", 4000)

        self.assertTrue(self.bandwidth.request("upstream", "slice_1") == 0)

        self.bandwidth.update("upstream", 100, "slice_1")
        self.assertTrue(self.bandwidth.request("upstream", "slice_1") == 0)

    def test_decay(self):
        # Bake cake.
        self.bandwidth.limit(2000, "sec", "upstream")
        self.bandwidth.register_transfer("t1")
        self.bandwidth.request("upstream", "t1")

        # Test decay.
        time.sleep(0.2)
        self.assertTrue(self.bandwidth.request("upstream", "t1") != 2000)

        # Check reallocation.
        cake_slice = self.bandwidth.cake["upstream"]["slices"]["t1"]
        chunk = 100
        remaining = cake_slice["size"] - cake_slice["stale"]
        expected = chunk
        used = self.bandwidth.info["sec"]["upstream"]["used"]
        self.assertTrue(used == remaining)
        self.bandwidth.update("upstream", chunk, "t1")
        ret = "t1" not in self.bandwidth.cake["upstream"]["slices"]
        self.assertTrue(ret)
        used = self.bandwidth.info["sec"]["upstream"]["used"]
        self.assertTrue(expected == used)

    def test_gradual_decay(self):
        # Wait for new second.
        self.bandwidth.get_fresh_second()

        # Bake cake.
        self.bandwidth.limit(2000, "sec", "upstream")
        self.bandwidth.register_transfer("t1")
        a = self.bandwidth.request("upstream", "t1")

        # Gradual decay.
        time.sleep(0.2)
        b = self.bandwidth.request("upstream", "t1")
        self.assertTrue(a != b)

        # Gradual decay.
        time.sleep(0.2)
        c = self.bandwidth.request("upstream", "t1")
        self.assertTrue(b != c)

    def test_ceiling(self):
        self.bandwidth.limit(1025, "sec", "upstream")
        self.bandwidth.register_transfer("slice_1")
        self.bandwidth.register_transfer("slice_2")
        allowance = self.bandwidth.request("upstream", "slice_1", 100)
        self.assertTrue(allowance == 100)

    def test_non_transfer_bandwidth(self):
        self.bandwidth.limit(1025, "sec", "upstream")
        self.bandwidth.register_transfer("slice_1")
        self.assertTrue(self.bandwidth.request("upstream") == 52)

    def test_reallocation(self):
        self.bandwidth.limit(1025, "sec", "upstream")
        self.bandwidth.register_transfer("slice_1")
        self.bandwidth.request("upstream", "slice_1")
        self.bandwidth.update("upstream", 100, "slice_1")
        expected = 100
        used = self.bandwidth.info["sec"]["upstream"]["used"]
        self.assertTrue(expected == used)

    def test_save_load_limits(self):
        config_file = ConfigFile()
        bl = BandwidthLimit(config_file)
        bw_limit = bl.info["sec"]["upstream"]["limit"] + 1
        bl.limit(
            bw_limit,
            "sec",
            "upstream"
        )
        assert(bl.info["sec"]["upstream"]["limit"] == bw_limit)
        bl.info["sec"]["upstream"]["limit"] = 0
        bl.load()
        assert(bl.info["sec"]["upstream"]["limit"] == bw_limit)

if __name__ == "__main__":
    unittest.main()
