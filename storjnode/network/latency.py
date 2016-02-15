from __future__ import unicode_literals
from uuid import uuid4
import hashlib
import time
import Queue


class LatencyTest:
    def __init__(self, factory, con, is_master):
        self.factory = factory
        self.con = con
        self.is_master = is_master
        self.probes = {}
        self.pending = {
            "recv": ["THEIR_PING"] * self.factory.probe_no,
            "sent": [],
            "sent_total": 0
        }
        self.is_active = False
        self.latency = 0
        self.con_ready = False
        self.contracts = Queue.Queue()
        self.start()

    def new_probe(self):
        probe_id = str(uuid4())
        probe_id = hashlib.sha256(probe_id).hexdigest()
        self.probes[probe_id] = {
            "status": "PING",
            "start_time": time.time(),
            "stop_time": None
        }

        return probe_id

    def schedule_probe(self):
        probe_id = self.new_probe()
        msg = "PING %s" % probe_id
        ret = self.con.send_line(msg)
        self.pending["sent"].append(probe_id)
        self.pending["sent_total"] += 1

    def start(self):
        if self.is_master:
            self.con_ready = True
            self.schedule_probe()
        self.is_active = True

    def stop(self):
        self.is_active = False

    def process_msg(self, msg):
        # Sanity check.
        components = msg.split(" ")
        if len(components) != 2:
            return

        # Parse message.
        cmd, probe_id = components

        # Process latency requests.
        if cmd == "PING":
            reply = "PONG %s" % probe_id
            ret = self.con.send_line(reply)
            self.pending["recv"].remove("THEIR_PING")

        # Process latency responses.
        if cmd == "PONG":
            if probe_id in self.probes:
                probe = self.probes[probe_id]
                if probe["status"] == "PING":
                    probe["status"] = "PONG"
                    probe["stop_time"] = time.time()
                    self.pending["sent"].remove(probe_id)
                    if self.pending["sent_total"] < self.factory.probe_no:
                        self.schedule_probe()

        # Start tests for our side.
        if not len(self.pending["recv"]):
            if not self.con_ready:
                self.con_ready = True
                self.schedule_probe()

        # Process results.
        empty = not len(self.pending["sent"] + self.pending["recv"])
        if empty and self.pending["sent_total"] == self.factory.probe_no:
            self.process_results()

    def process_results(self):
        latencies = []
        for probe_id in list(self.probes):
            probe = self.probes[probe_id]
            latency = probe["stop_time"] - probe["start_time"]
            latencies.append(latency)

        latencies = sorted(latencies, key=int)
        self.latency = latencies[int(self.factory.probe_no / 2)]
        self.stop()

    def queue_contract(self, contract):
        self.contracts.put(contract)


class LatencyTests:
    def __init__(self):
        self.probe_no = 10
        self.tests = {}
        self.finished = {}
        self.enabled = False

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def register(self, con, is_master, contract=None):
        if not self.enabled:
            raise Exception("Latency tests not enabled.")

        if con not in self.tests:
            self.tests[con] = LatencyTest(self, con, is_master)
            if contract is not None:
                self.tests[con].queue_contract(contract)

        return self.by_con(con)

    def by_con(self, con):
        if con in self.tests:
            return self.tests[con]

        if con in self.finished:
            return self.finished[con]

        return None

    def are_running(self):
        for con in list(self.tests):
            test = self.tests[con]
            if test.is_active:
                return True

        return False
