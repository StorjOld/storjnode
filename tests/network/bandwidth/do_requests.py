
import storjnode
from collections import OrderedDict
import logging
import time
import tempfile
import pyp2p
from storjnode.network.bandwidth.constants import ONE_MB
from storjnode.network.bandwidth.test import BandwidthTest
from storjnode.network.bandwidth.do_requests import *
from storjnode.network.file_transfer import FileTransfer
from storjnode.util import address_to_node_id
from storjnode.util import list_to_ordered_dict
from storjnode.util import ordered_dict_to_list
from btctxstore import BtcTxStore
import unittest
import copy
from crochet import setup
setup()

_log = storjnode.log.getLogger(__name__)


class TestSubBandwidthRequests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alice_wallet = BtcTxStore(testnet=False, dryrun=True)
        cls.alice_wif = cls.alice_wallet.create_key()
        cls.alice_node_id = address_to_node_id(
            cls.alice_wallet.get_address(cls.alice_wif)
        )
        cls.alice_dht = pyp2p.dht_msg.DHT(
            node_id=cls.alice_node_id,
            networking=0
        )
        cls.alice_transfer = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=0,
                debug=1,
                wan_ip="8.8.8.8",
                dht_node=cls.alice_dht,
            ),
            wif=cls.alice_wif,
            store_config={tempfile.mkdtemp(): None}
        )

        cls.alice_test = BandwidthTest(
            cls.alice_wif,
            cls.alice_transfer,
            cls.alice_dht,
            0
        )

        # Bob sample node.
        cls.bob_wallet = BtcTxStore(testnet=False, dryrun=True)
        cls.bob_wif = cls.bob_wallet.create_key()
        cls.bob_node_id = address_to_node_id(
            cls.bob_wallet.get_address(cls.bob_wif)
        )
        cls.bob_dht = pyp2p.dht_msg.DHT(
            node_id=cls.bob_node_id,
            networking=0
        )
        cls.bob_transfer = FileTransfer(
            pyp2p.net.Net(
                net_type="direct",
                node_type="passive",
                nat_type="preserving",
                passive_port=0,
                debug=1,
                wan_ip="8.8.8.8",
                dht_node=cls.bob_dht
            ),
            wif=cls.bob_wif,
            store_config={tempfile.mkdtemp(): None}
        )

        cls.bob_test = BandwidthTest(
            cls.bob_wif,
            cls.bob_transfer,
            cls.bob_dht,
            0
        )

        def alice_hook_relay_message(node_id, req):
            _log.debug(str(req))
            cls.req = req

        def bob_hook_relay_message(node_id, req):
            _log.debug(str(req))

        cls.alice_test.api.relay_message = alice_hook_relay_message
        cls.bob_test.api.relay_message = bob_hook_relay_message
        cls.alice_test.start(cls.bob_transfer.net.unl.value)

    @classmethod
    def tearDownClass(cls):
        cls.alice_transfer.net.stop()
        cls.bob_transfer.net.stop()

    def test_handle_requests(self):
        handle_requests = handle_requests_builder(self.bob_test)

        # Invalid message type.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req[u"type"] = "garbage"
        req = ordered_dict_to_list(req)
        self.assertTrue(handle_requests(
            self.alice_dht,
            self.alice_node_id,
            req
        ) == -1)

        # Already active.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req = ordered_dict_to_list(req)
        self.bob_test.test_node_unl = True
        self.assertTrue(handle_requests(
            self.alice_dht,
            self.alice_node_id,
            req
        ) == -2)
        self.bob_test.test_node_unl = None

        # Incorrect node id.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req["test_node_unl"] = 1
        req = ordered_dict_to_list(req)
        self.assertTrue(handle_requests(
            self.alice_dht,
            self.alice_node_id,
            req
        ) == -3)

        # Invalid sig.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req["something"] = 1
        req = ordered_dict_to_list(req)
        self.assertTrue(handle_requests(
            self.alice_dht,
            self.alice_node_id,
            req
        ) == -4)

        # Sending to us
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req["requester"] = self.bob_transfer.net.unl.value
        req = ordered_dict_to_list(req)
        self.assertTrue(handle_requests(
            self.alice_dht,
            self.alice_node_id,
            req
        ) == -5)

        # Success.
        req = copy.deepcopy(self.req)
        self.assertTrue(type(handle_requests(
            self.alice_dht,
            self.alice_node_id,
            req
        )) == list)

        """
        ----------------------
        Test accept handler.
        ----------------------
        """

        # Handler expired.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        accept_handler = self.bob_test.handlers["accept"].pop()
        self.assertTrue(accept_handler(
            "contract_id",
            self.alice_transfer.net.unl.value,
            req["data_id"],
            ONE_MB
        ) == -1)
        self.bob_test.handlers["accept"].add(accept_handler)

        # Invalid data id.
        self.assertTrue(accept_handler(
            "contract_id",
            self.alice_transfer.net.unl.value,
            "test",
            ONE_MB
        ) == -2)

        # Invalid data id.
        self.assertTrue(accept_handler(
            "contract_id",
            self.bob_transfer.net.unl.value,
            req["data_id"],
            ONE_MB
        ) == -3)

        # Invalid data id.
        self.bob_test.test_size = 0
        self.assertTrue(accept_handler(
            "contract_id",
            self.alice_transfer.net.unl.value,
            req["data_id"],
            ONE_MB
        ) == -4)
        self.bob_test.test_size = 1

        # Invalid data id.
        self.assertTrue(accept_handler(
            "contract_id",
            self.alice_transfer.net.unl.value,
            req["data_id"],
            ONE_MB
        ) == 1)

        """
        ----------------------
        Test start handler.
        ----------------------
        """

        # Handler expired.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        start_handler = self.bob_test.handlers["start"].pop()
        self.assertTrue(start_handler(
            self.bob_transfer,
            None,
            "start_contract_id"
        ) == -1)
        self.bob_test.handlers["start"].add(start_handler)

        # This should pass.
        contract = {
            "host_unl": self.bob_transfer.net.unl.value,
            "data_id": req["data_id"]
        }
        self.bob_transfer.contracts[req["data_id"]] = contract
        self.assertTrue(start_handler(
            self.bob_transfer,
            None,
            req["data_id"]
        ) == 1)

        # Invalid data id.
        contract = {
            "host_unl": self.bob_transfer.net.unl.value,
            "data_id": "x"
        }
        self.bob_transfer.contracts[req["data_id"]] = contract
        self.assertTrue(start_handler(
            self.bob_transfer,
            None,
            req["data_id"]
        ) == -2)

        """
        ----------------------
        Test completion handler.
        ----------------------
        completion_handler(client, contract_id, con):
        """

        # Handler expired.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        complete_handler = self.bob_test.handlers["complete"].pop()
        contract_id = ""
        self.assertTrue(complete_handler(
            self.bob_transfer,
            contract_id,
            None
        ) == -1)
        self.bob_test.handlers["complete"].add(complete_handler)

        # Invalid data id.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": "yyy"
        }
        self.bob_transfer.contracts[contract_id] = contract
        self.assertTrue(complete_handler(
            self.bob_transfer,
            contract_id,
            None
        ) == -2)

        # Upload: invalid src unl.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["data_id"],
            "dest_unl": self.bob_transfer.net.unl.value,
            "host_unl": self.bob_transfer.net.unl.value
        }
        self.bob_transfer.contracts[contract_id] = contract
        self.assertTrue(complete_handler(
            self.bob_transfer,
            contract_id,
            None
        ) == -3)

        # Download: invalid src unl.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["data_id"],
            "dest_unl": self.bob_transfer.net.unl.value,
            "host_unl": self.alice_transfer.net.unl.value,
            "src_unl": self.bob_transfer.net.unl.value
        }
        self.bob_transfer.contracts[contract_id] = contract
        self.assertTrue(complete_handler(
            self.bob_transfer,
            contract_id,
            None
        ) == -4)

        # Upload: bad results
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["data_id"],
            "dest_unl": self.alice_transfer.net.unl.value,
            "host_unl": self.bob_transfer.net.unl.value
        }
        self.bob_transfer.contracts[contract_id] = contract
        self.assertTrue(complete_handler(
            self.bob_transfer,
            contract_id,
            None
        ) == 1)

        # Test errback.
        # d = self.bob_transfer.defers[contract_id]
        # d.errback("test")


if __name__ == "__main__":
    unittest.main()
