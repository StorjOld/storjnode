"""
Description: traditional bandwidth limiting algorithms are based on
using averages as a correction mechanism. This approach is good for
keeping bandwidth usage within a certain ball-park range, but when
it comes to maintaining a persistent transfer rate on the host:
sudden performance issues can cause the average transfer rate to
drop thereby opening up a potential window of opportunity where the
algorithm will attempt to send or receive massive bursts of traffic
until the average transfer rate averages to the specified limit.

The algorithm for this module avoids this problem by using absolute
limits to divides time into an infinite series of 1 second slots.
Every new second a cake is baked and then split into slices based on the
number of active transfers. Each transfer receives a slice of cake,
representing a portion of the bandwidth available for that period.
Slices may be eaten in full or in part. If a slice is eaten in part:
the rejected portion of cake becomes available for consumption to other
transfers, meaning that transfers always get the chance of eating at least
some of their reserved slice of cake for every 1 second period. If the
transfer fails to eat, their slice is also reduced by a percentage
representing the current amount of progress towards the new second.
Monthly limits are also enforced by keeping a running total for all
bandwidth usage for that the month.

This approach avoids giving the appearance of idle connections, avoids
bursting, and avoids having slow links asking for bandwidth that they then
cannot consume. Another optimisation which isn't discussed is the idle
bandwidth problem. Farmers are going to be running our software on a lot
of home connections and presumably they will still want to be able to
use their Internet connection without active transfers completely
saturating their connection. LEDBAT seems to solve this problem well
but we're using TCP for now. A possible solution for TCP is to monitor
outside bandwidth usage from other nodes on the LAN by using UPnP
to query their router and comparing the relationship between absolute
bandwidth, outside activity, and file transfer usage to determine
whether file transfers are comparatively saturating their total
available bandwidth. This is an optimisation which may be implemented
in the future.
"""

import time
import datetime
import calendar
import os
import json
from storjnode.util import byte_count
from storjnode.common import STORJ_HOME

MONTHLY_USAGE_PATH = os.path.join(STORJ_HOME, "monthly_usage")


class BandwidthLimit:
    def __init__(self, config):

        # Config file object for loading limits.
        self.config = config

        # Record bandwidth stats for active transfers.
        # Used to limit bandwidth usage for farmers.
        self.info = {}
        self.valid_bw_types = ["upstream", "downstream"]
        self.valid_time_frames = ["sec", "month"]
        for time_frame in self.valid_time_frames:
            self.info[time_frame] = {}
            for bw_type in self.valid_bw_types:
                self.info[time_frame][bw_type] = {
                    "used": 0,  # Bytes per time_frame.
                    "limit": 0   # Bytes per time_frame.
                }

        # List of active transfers (contract IDs.)
        self.transfers = set()

        # Every second a new cake is baked.
        # Each bandwidth type has a separate cake.
        self.cake = {}
        for bw_type in self.valid_bw_types:
            self.cake[bw_type] = {
                "no": -1,
                "slices": {}
            }

        # Unix timestamp of next month.
        self.next_month = 0

        # What % of sec limit is (initially) reserved for file transfers.
        # The remaining % is for small protocol headers + other.
        # Todo: add bandwidth limits to all other networking stuff
        # Todo: then when that's done decrease this slightly
        # Todo: based on how much bandwidth they have
        self.cake_scale = 1

        # Calculate future time for next month.
        self.next_month = self.calculate_next_month()

        # Load bandwidth limits.
        self.load()

    def is_over_monthly_limit(self, bw_type):
        monthly_used = self.info["month"][bw_type]["used"]
        monthly_limit = self.info["month"][bw_type]["limit"]
        if monthly_used >= monthly_limit:
            return True

        return False

    def clear_monthly_usage(self):
        if os.path.isfile(MONTHLY_USAGE_PATH):
            os.remove(MONTHLY_USAGE_PATH)

    def save_monthly_usage(self):
        # Create Storj home directory if needed.
        if not os.path.exists(STORJ_HOME):
            os.makedirs(STORJ_HOME)

        # Save monthly usage. Create file if needed.
        with open(MONTHLY_USAGE_PATH, "w") as fp:
            as_dict = {
                "next_month": self.next_month,
                "usage": {
                    "upstream": self.info["month"]["upstream"]["used"],
                    "downstream": self.info["month"]["downstream"]["used"]
                }
            }

            as_json = json.dumps(as_dict)
            fp.write(as_json)

    def load_monthly_usage(self):
        if not os.path.isfile(MONTHLY_USAGE_PATH):
            return

        # Get file contents.
        content = ""
        with open(MONTHLY_USAGE_PATH, "r") as fp:
            content = fp.read()

        # Convert contents to JSON + validate.
        as_dict = None
        try:
            temp = json.loads(content)
            temp["next_month"] = int(temp["next_month"])
            temp["usage"]["upstream"] = int(temp["usage"]["upstream"])
            temp["usage"]["downstream"] = int(temp["usage"]["downstream"])
            as_dict = temp
        except (KeyError, ValueError):
            pass

        # Validation successful. Load it.
        if as_dict is not None:
            self.next_month = as_dict["next_month"]
            self.info["month"]["downstream"]["used"] = \
                as_dict["usage"]["downstream"]
            self.info["month"]["upstream"]["used"] = \
                as_dict["usage"]["upstream"]

    def get_fresh_second(self):
        while 1:
            t = time.time()
            t = (t - int(t))
            if t < 0.001:
                break

    def calculate_next_month(self):
        # Find current time.
        now = datetime.datetime.utcnow()

        # Find next month.
        year = now.year
        month = now.month
        if month == 12:
            year += 1
            month = 1
        next_month = datetime.datetime(year, month, 1)

        # Convert to unix timestamp.
        return calendar.timegm(next_month.timetuple())

    def wild_card_func(self, func, args, time_frame, bw_type):
        called = 0
        if time_frame is None:
            called = 1
            self.wild_card_func(func, args, "sec", bw_type)
            self.wild_card_func(func, args, "month", bw_type)

        if bw_type is None:
            called = 1
            self.wild_card_func(func, args, time_frame, "upstream")
            self.wild_card_func(func, args, time_frame, "downstream")

        processed_args = []
        for arg in args:
            if arg == "time_frame":
                processed_args.append(time_frame)
            elif arg == "bw_type":
                processed_args.append(bw_type)
            else:
                processed_args.append(arg)

        if not called:
            processed_args.append(1)
            func(*processed_args)

        return called

    def reset_usage(self, bw_type=None, time_frame=None, skip=0):
        """
        Resets usage for bandwidth period.

        :return:
        """

        if not skip:
            if self.wild_card_func(
                self.reset_usage,
                ["bw_type", "time_frame"],
                time_frame,
                bw_type
            ):
                return

        self.info[time_frame][bw_type]["used"] = 0

    def register_transfer(self, contract_id):
        """
        Cake slices are allocated between active transfers. This function
        specifies the number of active transfers by making a list of
        contract IDs.

        Call when a transfer is starting.

        :param contract_id:
        :return: Nothing.
        """
        self.transfers.add(contract_id)

    def remove_transfer(self, contract_id):
        """
        Removes a transfer from the active transfer list (thereby allowing
        bigger slices to be allocated to remaining transfers.)

        Call when a transfer finishes.

        :param contract_id:
        :return: Nothing.
        """
        if contract_id in self.transfers:
            self.transfers.remove(contract_id)

    def load(self):
        assert(self.config is not None)
        for time_frame in self.valid_time_frames:
            for bw_type in self.valid_bw_types:
                bwl = self.config["network"]["bandwidth_limits"]
                bwl = byte_count(bwl[time_frame][bw_type])
                self.info[time_frame][bw_type]["limit"] = bwl

        # Load monthly usage from file.
        self.load_monthly_usage()

    def update(self, bw_type, increment, contract_id=None):
        """
        This function updates the amount transferred so that averages
        can be calculated and its called after new data is sent +
        received.

        :param bw_type: Bandwidth type.
        :param increment: Amount transferred.
        :return: None.
        """

        # No change to record.
        if not increment:
            return

        # Get bandwidth details.
        sec = self.info["sec"][bw_type]
        month = self.info["month"][bw_type]

        # Update cake slices.
        cake = self.cake[bw_type]
        if contract_id is not None:
            if contract_id in cake["slices"]:
                # Free reserved resources.
                cake_slice = cake["slices"][contract_id]
                reserved = cake_slice["size"] - cake_slice["stale"]
                sec["used"] -= reserved

                # Delete cake slice.
                del cake["slices"][contract_id]

        # Increase bandwidth usage.
        sec["used"] += increment
        month["used"] += increment

        # Save monthly usage to file.
        self.save_monthly_usage()

    def limit(self, amount, time_frame=None, bw_type=None, skip=0):
        """
        Set a fixed limit for a certain bandwidth resource. Limits
        may be applied to per second intervals or monthly. Monthly
        takes priority over seconds. Bandwidth can be further divided
        based on upstream or downstream for bw_type.

        :param amount: Value in bytes to use for bandwidth limit.
        :param time_frame: sec (per second) or month (per month.)
        :param bw_type: downstream (recv), upstream (send)
        :return: Nothing
        """
        if time_frame is not None:
            assert(time_frame in self.valid_time_frames)
        if bw_type is not None:
            assert(bw_type in self.valid_bw_types)

        if not skip:
            if self.wild_card_func(
                self.limit,
                [amount, "time_frame", "bw_type"],
                time_frame,
                bw_type
            ):
                return

        # Limit bandwidth amount.
        self.info[time_frame][bw_type]["limit"] = amount

    def request(self, bw_type, contract_id=None, ceiling=None):
        """
        Requests to use some of the bandwidth resources. Returns up to
        the number of bytes which are currently free relative to the call.
        May return zero if no bandwidth is available.

        :param bw_type: Upstream or downstream.
        :param contract_id: Contract ID associated with file transfer.
        :param ceiling: Don't return anything larger than this.
        :return: number of bytes available for current second interval.
        """

        # Get bandwidth details.
        sec = self.info["sec"][bw_type]
        month = self.info["month"][bw_type]

        # Monthly period has expired.
        if self.next_month:
            if time.time() >= self.next_month:
                self.next_month = self.calculate_next_month()
                month["used"] = 0
                self.save_monthly_usage()

        # Check monthly limit.
        if month["limit"]:
            remaining = month["limit"] - month["used"]
            if not remaining:
                return 0

        # There's no sec limit.
        if not sec["limit"]:
            if ceiling is not None:
                return ceiling
            else:
                return 8192

        # What cake is this?
        cake = self.cake[bw_type]
        cake_no = int(time.time())

        # Bake a new cake if we need to.
        if cake["no"] != cake_no:
            # Calculate cake size.
            # n% of bandwidth reserved for control messages / misc.
            cake_size = int(sec["limit"] * self.cake_scale)
            if not cake_size:
                return 0

            # Slice the cake.
            cake_slices = {}
            transfer_no = len(self.transfers)
            sec["used"] = 0  # Rest used.
            for transfer in self.transfers:
                size = int(cake_size / transfer_no)
                if size < 1:
                    size = 0

                cake_slice = {
                    "size": size,
                    "stale": 0,
                    "requested": 0
                }

                cake_slices[transfer] = cake_slice
                sec["used"] += size

            # Allocate remaining pieces.
            if transfer_no:
                remainder = int(cake_size % transfer_no)
                if remainder:
                    cake_slices[list(cake_slices)[0]]["size"] += remainder
                    sec["used"] += remainder

            # Build new cake.
            cake = self.cake[bw_type] = {
                "no": cake_no,
                "slices": cake_slices
            }

            # No bandwidth left.
            if transfer_no and self.cake_scale == 100:
                if contract_id is None:
                    return 0

        # Reduce cake slice size over time.
        progress = time.time() - cake_no
        if progress < 1:
            for transfer in list(cake["slices"]):
                # Find slice.
                cake_slice = cake["slices"][transfer]
                if not cake_slice["requested"]:
                    continue

                # Undo old resource reallocation.
                if cake_slice["stale"]:
                    sec["used"] += cake_slice["stale"]

                # Increase amount of cake that's stale.
                cake_slice["stale"] = int(
                    cake_slice["size"] * progress
                )

                # Redo new resource reallocation.
                sec["used"] -= cake_slice["stale"]

        # Calculate remaining bandwidth.
        allowance = sec["limit"] - sec["used"]
        if allowance < 0:
            return 0

        # Return bandwidth reservation.
        if contract_id is not None:
            if contract_id in cake["slices"]:
                cake_slice = cake["slices"][contract_id]
                allowance = cake_slice["size"] - cake_slice["stale"]
                cake_slice["requested"] = 1

        # Set a ceiling for returned bandwidth.
        if ceiling is not None:
            if allowance > ceiling:
                allowance = ceiling

        # Return bandwidth.
        return allowance


if __name__ == "__main__":
    pass
