import time
from threading import Thread
import logging
import storjnode

_log = storjnode.log.getLogger(__name__)
ENABLE_REPEAT = True


class RepeatRelay:
    def __init__(self, node):
        self.node = node
        self.relaying = []
        self.thread_running = True
        self.t = Thread(target=self.rebroadcast_loop)
        self.t.start()

    def stop(self):
        self.thread_running = False

    def rebroadcast_loop(self):
        while self.thread_running:
            self.rebroadcast()
            time.sleep(1)

    def rebroadcast(self):
        # Rebroadcast after these thresholds.
        intervals = [
            1000, 500, 250, 120, 60, 30,
            10
        ]

        # Process messages.
        expired = []
        for relay_info in self.relaying:
            # Not rebroadcasting.
            if not relay_info["rebroadcast"]:
                continue

            # Is it time to rebroadcast this?
            elapsed = time.time() - relay_info["timestamp"]
            for interval in intervals:
                if elapsed >= interval:
                    # Already broadcast.
                    if relay_info["interval"] == interval:
                        break

                    # Broadcast.
                    # _log.debug(str(relay_info))
                    self.node.relay_message(
                        relay_info["node_id"],
                        relay_info["msg"]
                    )
                    relay_info["interval"] = interval

                    # Expire.
                    if interval == 120:
                        expired.append(relay_info)

                    break

        for relay_info in expired:
            self.relaying.remove(relay_info)

    def relay(self, node_id, msg, rebroadcast=True):
        relay_info = {
            "msg": msg,
            "node_id": node_id,
            "timestamp": time.time(),
            "interval": 0,
            "rebroadcast": ENABLE_REPEAT
        }

        self.relaying.append(relay_info)
        self.node.relay_message(node_id, msg)

        return None
