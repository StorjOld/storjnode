import signal
import tempfile
import time
import unittest
import storjnode
import btctxstore
from pyp2p.lib import parse_exception
from storjnode.network.server import WALK_TIMEOUT
from storjnode.network.file_transfer import enable_unl_requests
from collections import OrderedDict
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


_log = storjnode.log.getLogger(__name__)

PROFILE = False
PORT = storjnode.util.get_unused_port()
STORAGE_DIR = tempfile.mkdtemp()

print("Storage dir: " + str(STORAGE_DIR))

swarm = []

# Show bandwidth.
still_running = 1


def _test_config(storage_path, bootstrap_nodes):
    config = storjnode.config.create()
    config["network"]["refresh_neighbours_interval"] = 0
    config["network"]["bootstrap_nodes"] = bootstrap_nodes
    config["storage"] = {
        storage_path: {"limit": "5G", "use_folder_tree": False}
    }
    storjnode.config.validate(config)
    return config


class TestBandwidthTestWithDHT(unittest.TestCase):
    @unittest.skip("Already tested in node.py")
    def test_bandwidth_test_with_dht(self):
        bootstrap_nodes = [["127.0.0.1", PORT + x] for x in range(3)]
        for i in range(3):
            wallet = btctxstore.BtcTxStore().create_wallet()
            storage_path = "{0}/peer_{1}".format(STORAGE_DIR, i)
            config = _test_config(storage_path, bootstrap_nodes)
            node = storjnode.network.Node(
                wallet,
                port=(PORT + i),
                config=config,
                nat_type="preserving",
                node_type="passive",
                disable_data_transfer=False,
                max_messages=1024
            )
            _log.info(node._data_transfer.net.passive_port)
            _log.info(node._data_transfer.net.unl.value)
            ONE_MB = node.bandwidth_test.ONE_MB = 1024 * 1024
            node.bandwidth_test.__init__(
                node.get_key(),
                node._data_transfer,
                node,
                1,
                ONE_MB
            )
            node.bandwidth_test.test_timeout = 1000000
            node.bandwidth_test.increasing_tests = 1
            node.bandwidth_test.increases = OrderedDict([
                [1 * ONE_MB, 4 * ONE_MB],
                [4 * ONE_MB, 6 * ONE_MB],
                [6 * ONE_MB, 6 * ONE_MB]
            ])

            assert(node._data_transfer is not None)
            # node.repeat_relay.thread_running = False
            storjnode.network.messages.info.enable(node, {})
            storjnode.network.messages.peers.enable(node)
            enable_unl_requests(node)
            node.bandwidth_test.enable()
            node.latency_tests.enable()
            swarm.append(node)

        def show_bandwidth(results):
            print(results)
            global test_success
            global still_running
            print("IN SUCCESS CALLBACK!?@#!@#?!@?#")
            print(swarm[0].bandwidth_test.max_increase)
            test_success = 1
            # still_running = 0
            # return
            try:
                _log.debug(results)
                """
                print(swarm[0].bandwidth_test.test_size)
                print(swarm[0].bandwidth_test.active_test)
                print(swarm[0].bandwidth_test.results)
                print(swarm[0].bandwidth_test.test_node_unl)
                print(swarm[0].bandwidth_test.start_time)
                print(swarm[0].bandwidth_test.data_id)
                print(swarm[0].bandwidth_test.handlers)
                """

                print("starting next bandwiwdth test!")

                def success_callback_2(results):
                    global still_running
                    still_running = 0
                    print("IN FINAL SYUCCESS CALLBACK!?!")
                    print(results)

                d = swarm[0].test_bandwidth(swarm[1].get_id())
                d.addCallback(success_callback_2)
            except Exception as e:
                print(parse_exception(e))
                exit()

        swarm[0].relay_message(swarm[1].get_id(), "Test message")
        d = swarm[0].test_bandwidth(swarm[1].get_id())
        d.addCallback(show_bandwidth)

        def rejection_results(ret):
            print("Bandwidth rejection received")
            print("\a")
            print(ret)

        # d = swarm[2].test_bandwidth(swarm[1].get_id())
        # assert(swarm[2].bandwidth_test.test_node_unl is not None)
        # d.addErrback(rejection_results)

        while still_running:
            time.sleep(0.1)

        print("Still running done")

        for node in swarm:
            node.stop()

if __name__ == "__main__":
    unittest.main()
