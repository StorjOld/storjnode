import unittest
import storjnode
import time
from storjnode.network.bandwidth.limit import BandwidthLimit

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

    def test_limit(self):
        self.bandwidth.limit(1025, "sec", "upstream")
        self.assertTrue(
            self.bandwidth.info["sec"]["upstream"]["limit"] == 1025
        )

    def test_slice_remainder(self):
        self.bandwidth.limit(1025, "sec", "upstream")
        self.bandwidth.register_transfer("slice_1")
        self.bandwidth.register_transfer("slice_2")
        allowance = self.bandwidth.request("upstream", "slice_1")
        self.assertTrue(allowance == 513)
        allowance = self.bandwidth.request("upstream", "slice_2")
        self.assertTrue(allowance == 512)
        map(self.bandwidth.remove_transfer, ["slice_1", "slice_2"])
        assert(not len(self.bandwidth.transfers))

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
        self.assertTrue(self.bandwidth.request("upstream", "t1") != 200)

    def test_ceiling(self):
        self.bandwidth.limit(1025, "sec", "upstream")
        self.bandwidth.register_transfer("slice_1")
        self.bandwidth.register_transfer("slice_2")
        allowance = self.bandwidth.request("upstream", "slice_1", 100)
        self.assertTrue(allowance == 100)


if __name__ == "__main__":
    unittest.main()
