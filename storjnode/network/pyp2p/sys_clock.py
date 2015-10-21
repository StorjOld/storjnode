"""
Given an NTP accurate time, this module computes an
approximation of how far off the system clock is
from the NTP time (clock skew.) The algorithm was
taken from gtk-gnutella.

https://github.com/gtk-gnutella/gtk-gnutella/
blob/devel/src/core/clock.c 
"""

from .lib import *
import numpy
import time
from decimal import Decimal

class SysClock:
    def __init__(self, clock_skew=Decimal("0")):
        self.enough_data = 30
        self.min_data = 15
        self.max_sdev = 60
        self.clean_steps = 3
        self.data_points = []
        self.clock_skew = clock_skew
        if not self.clock_skew:
            self.collect_data_points()
            self.clock_skew = self.calculate_clock_skew()

    def time(self):
        return Decimal(time.time()) - self.clock_skew

    def collect_data_points(self):
        while len(self.data_points) < self.enough_data + 10:
            clock_skew = Decimal(time.time()) - Decimal(get_ntp())
            self.data_points.append(clock_skew)

    def statx_n(self, data_points):
        return len(data_points)

    def statx_avg(self, data_points):
        total = Decimal("0")
        n = self.statx_n(data_points)
        for i in range(0, n):
            total += data_points[i]

        return total / Decimal(n)

    def statx_sdev(self, data_points):
        return numpy.std(data_points)

    def calculate_clock_skew(self):
        """
        Computer average and standard deviation
        using all the data points.
        """
        n = self.statx_n(self.data_points)

        """
        Required to be able to compute the standard
        deviation.
        """
        if n < 1:
            return Decimal("0")

        avg = self.statx_avg(self.data_points)
        sdev = self.statx_sdev(self.data_points)

        """
        Incrementally remove aberration points.
        """
        for k in range(0, self.clean_steps):
            """
            Remove aberration points: keep only
            the sigma range around the average.
            """
            min_val = avg - sdev
            max_val = avg + sdev

            cleaned_data_points = []
            for i in range(0, n):
                v = self.data_points[i]
                if v < min_val or v > max_val:
                    continue
                cleaned_data_points.append(v)

            self.data_points = cleaned_data_points[:]

            """
            Recompute the new average using the
            "sound" points we kept.
            """
            n = self.statx_n(self.data_points)

            """
            Not enough data to compute standard
            deviation.
            """
            if n < 2:
                break

            avg = self.statx_avg(self.data_points)
            sdev = self.statx_sdev(self.data_points)

            if sdev <= self.max_sdev or n < self.min_data:
                break

        """
        If standard deviation is too large still, we
        cannot update our clock. Collect more points.

        If we don't have a minimum amount of data,
        don't attempt the update yet, continue collecting.
        """
        if sdev > self.max_sdev or n < self.min_data:
            return Decimal("0")

        return avg
        
if __name__ == "__main__":
    sys_clock = SysClock(clock_skew=Decimal("-29.9615900039672851562500"))

