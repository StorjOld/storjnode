from pyp2p.net import Net
from pyp2p.sock import Sock
from pyp2p.lib import get_lan_ip
from storjnode.network.latency import LatencyTests
from threading import Thread
import time
import unittest

alice_sock = None


class TestLatency(unittest.TestCase):
    def test_latency(self):
        global alice_sock

        # Create socks from different perspectives.
        net = Net(
            debug=1,
            net_type="direct",
            nat_type="preserving",
            node_type="passive",
            passive_port=0
        ).start()

        def success(con):
            global alice_sock
            alice_sock = con

        alice_sock = Net(
            debug=1,
            net_type="direct",
            nat_type="preserving",
            node_type="passive",
            passive_port=0
        ).start().unl.connect(net.unl.value, {"success": success})

        while not len(net.inbound) or alice_sock is None:
            net.synchronize()

        bob_sock = net.inbound[0]["con"]

        assert(alice_sock is not None)
        assert(bob_sock is not None)
        while alice_sock.nonce is None or bob_sock.nonce is None:
            net.synchronize()

        # Setup latency tests.
        alice_latencies = LatencyTests()
        alice_latencies.enable()
        alice_latency = alice_latencies.register(alice_sock, is_master=1)
        bob_latencies = LatencyTests()
        bob_latencies.enable()
        bob_latency = bob_latencies.register(bob_sock, is_master=0)

        def process_tests(latency_tests):
            # Simulate test logic process_transfers.
            while latency_tests.are_running():
                for con in list(latency_tests.tests):
                    latency_test = latency_tests.by_con(con)
                    is_finished = 0
                    while not is_finished:
                        net.synchronize()
                        if latency_test.is_active:
                            for msg in con:
                                # print(str(msg))
                                latency_test.process_msg(msg)
                        else:
                            is_finished = 1
                            # print("Latency test finished")

                        time.sleep(0.00001)

                # print("test still running")

        # With threading.
        Thread(target=process_tests, args=(alice_latencies,)).start()
        Thread(target=process_tests, args=(bob_latencies,)).start()

        while alice_latencies.are_running() or bob_latencies.are_running():
            time.sleep(1)

        # Without threading.
        """
        while alice_latencies.are_running() or bob_latencies.are_running():
            for latency_tests in [alice_latencies, bob_latencies]:
                for con in list(latency_tests.tests):
                    latency_test = latency_tests.by_con(con)
                    for reply in con:
                        if latency_tests == alice_latencies:
                            print("Alice")
                        else:
                            print("Bob")
                        print(reply)
                        latency_test.process_msg(reply)
        """

        # print(alice_latencies.by_con(alice_sock).latency)
        # print(bob_latencies.by_con(bob_sock).latency)

        # Cleanup
        alice_sock.close()
        bob_sock.close()
        net.stop()

if __name__ == "__main__":
    unittest.main()
