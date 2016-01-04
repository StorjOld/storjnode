# todo: finish this modle.
import storjnode
from collections import OrderedDict
import logging
import time
import tempfile
import pyp2p
from storjnode.network.bandwidth.constants import ONE_MB
from storjnode.network.bandwidth.test import BandwidthTest
from storjnode.network.bandwidth.do_requests import handle_requests_builder
from storjnode.network.bandwidth.do_responses import handle_responses_builder
from storjnode.network.file_transfer import FileTransfer
from storjnode.util import address_to_node_id
from storjnode.util import list_to_ordered_dict
from storjnode.util import ordered_dict_to_list
from storjnode.network.bandwidth.limit import BandwidthLimit
from storjnode.config import ConfigFile
from btctxstore import BtcTxStore
import unittest
import copy
from crochet import setup
setup()

_log = storjnode.log.getLogger(__name__)


class TestSubBandwidthResponses(unittest.TestCase):
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
            BandwidthLimit(),
            wif=cls.alice_wif,
            store_config={tempfile.mkdtemp(): None}
        )

        cls.alice_test = BandwidthTest(
            cls.alice_wif,
            cls.alice_transfer,
            cls.alice_dht,
            1
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
            BandwidthLimit(),
            wif=cls.bob_wif,
            store_config={tempfile.mkdtemp(): None}
        )

        cls.bob_test = BandwidthTest(
            cls.bob_wif,
            cls.bob_transfer,
            cls.bob_dht,
            1
        )

        def alice_hook_relay_message(node_id, req):
            _log.debug(str(req))
            cls.req = req

        def bob_hook_relay_message(node_id, req):
            _log.debug(str(req))

        cls.alice_test.api.repeat_relay_message = alice_hook_relay_message
        cls.bob_test.api.repeat_relay_message = bob_hook_relay_message
        cls.alice_test.start(cls.bob_transfer.net.unl.value)

    @classmethod
    def tearDownClass(cls):
        cls.alice_transfer.net.stop()
        cls.bob_transfer.net.stop()

    def test_handle_responses(self):
        handle_requests = handle_requests_builder(self.bob_test)
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req = ordered_dict_to_list(req)
        self.req = handle_requests(
            self.alice_dht,
            req
        )
        print(req)
        print("-----------")

        # Handle responses.
        handle_responses = handle_responses_builder(self.alice_test)

        # Test invalid message type.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req[u"type"] = "garbage"
        req = ordered_dict_to_list(req)
        res = handle_responses(
            self.bob_dht,
            req
        )
        self.assertTrue(res == -1)

        # Test transfer already active.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req = ordered_dict_to_list(req)
        self.alice_test.test_node_unl = True
        res = handle_responses(
            self.bob_dht,
            req
        )
        self.assertTrue(res == -2)
        self.alice_test.test_node_unl = None

        # Check our sig is valid.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req[u"request"][u"something"] = u"invalidate our sig"
        req = ordered_dict_to_list(req)
        res = handle_responses(
            self.bob_dht,
            req
        )
        self.assertTrue(res == -3)

        # Test node ides match.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req[u"request"][u"test_node_unl"] = u"nope"
        req = ordered_dict_to_list(req)
        res = handle_responses(
            self.bob_dht,
            req
        )
        self.assertTrue(res == -4)

        # Their sig does not match.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req[u"something"] = u"invalid"
        req = ordered_dict_to_list(req)
        res = handle_responses(
            self.bob_dht,
            req
        )
        self.assertTrue(res == -5)

        # This should pass.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        req = ordered_dict_to_list(req)
        res = handle_responses(
            self.bob_dht,
            req
        )
        self.assertTrue(res is None)

        """
        ----------------------
        Test accept handler.
        ----------------------
        """

        # Handler expired.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        accept_handler = self.alice_test.handlers["accept"].pop()
        self.assertTrue(accept_handler(
            "contract_id",
            self.bob_transfer.net.unl.value,
            req[u"request"][u"data_id"],
            ONE_MB
        ) == -1)
        self.alice_test.handlers["accept"].add(accept_handler)

        # Invalid data id.
        self.assertTrue(accept_handler(
            "contract_id",
            self.bob_transfer.net.unl.value,
            "test",
            ONE_MB
        ) == -2)

        # Invalid node id.
        self.assertTrue(accept_handler(
            "contract_id",
            self.alice_transfer.net.unl.value,
            req[u"request"][u"data_id"],
            ONE_MB
        ) == -3)

        # Invalid file size.
        self.alice_test.test_size = 0
        self.assertTrue(accept_handler(
            "contract_id",
            self.bob_transfer.net.unl.value,
            req[u"request"][u"data_id"],
            ONE_MB
        ) == -4)
        self.alice_test.test_size = 1

        # This should pass
        self.assertTrue(accept_handler(
            "contract_id",
            self.bob_transfer.net.unl.value,
            req[u"request"][u"data_id"],
            ONE_MB
        ) == 1)

        """
        ----------------------
        Test start handler.
        ----------------------
        """

        # Handler expired.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        start_handler = self.alice_test.handlers["start"].pop()
        self.assertTrue(start_handler(
            self.alice_transfer,
            None,
            "start_contract_id"
        ) == -1)
        self.alice_test.handlers["start"].add(start_handler)

        # This should pass.
        contract = {
            "host_unl": self.bob_transfer.net.unl.value,
            "dest_unl": self.alice_transfer.net.unl.value,
            "data_id": req["request"]["data_id"]
        }
        self.alice_transfer.contracts[req["request"]["data_id"]] = contract
        self.assertTrue(start_handler(
            self.alice_transfer,
            None,
            req["request"]["data_id"]
        ) == 1)

        # Invalid data id.
        contract = {
            "host_unl": self.bob_transfer.net.unl.value,
            "dest_unl": self.alice_transfer.net.unl.value,
            "data_id": "x"
        }
        self.alice_transfer.contracts[req["request"]["data_id"]] = contract
        self.assertTrue(start_handler(
            self.alice_transfer,
            None,
            req["request"]["data_id"]
        ) == -2)

        # Invalid dest unl for upload.
        contract = {
            "host_unl": self.bob_transfer.net.unl.value,
            "dest_unl": self.alice_transfer.net.unl.value,
            "data_id": req["request"]["data_id"]
        }
        self.alice_transfer.contracts[req["request"]["data_id"]] = contract

        def get_direction_wrapper(contract_id):
            return u"send"

        original_get_direction = self.alice_transfer.get_direction
        self.alice_transfer.get_direction = get_direction_wrapper

        self.assertTrue(start_handler(
            self.alice_transfer,
            None,
            req["request"]["data_id"]
        ) == -3)
        self.alice_transfer.get_direction = original_get_direction

        """
        ----------------------
        Test completion handler.
        ----------------------
        completion_handler(client, contract_id, con):
        """

        # Handler expired.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        complete_handler = self.alice_test.handlers["complete"].pop()
        contract_id = ""
        self.assertTrue(complete_handler(
            self.alice_transfer,
            contract_id,
            None
        ) == -1)
        self.alice_test.handlers["complete"].add(complete_handler)

        # Check data ID.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": "yyy"
        }
        self.alice_transfer.contracts[contract_id] = contract
        self.assertTrue(complete_handler(
            self.alice_transfer,
            contract_id,
            None
        ) == -2)

        # Upload: invalid src unl.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["request"]["data_id"],
            "dest_unl": self.alice_transfer.net.unl.value,
            "host_unl": self.alice_transfer.net.unl.value
        }
        self.alice_transfer.contracts[contract_id] = contract
        self.assertTrue(complete_handler(
            self.alice_transfer,
            contract_id,
            None
        ) == -3)

        # Upload: invalid src unl.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["request"]["data_id"],
            "src_unl": self.alice_transfer.net.unl.value,
            "dest_unl": self.alice_transfer.net.unl.value,
            "host_unl": self.alice_transfer.net.unl.value
        }
        self.alice_transfer.contracts[contract_id] = contract

        def get_direction_wrapper(contract_id):
            return u"receive"

        original_get_direction = self.alice_transfer.get_direction
        self.alice_transfer.get_direction = get_direction_wrapper

        self.assertTrue(complete_handler(
            self.alice_transfer,
            contract_id,
            None
        ) == -4)

        self.alice_transfer.get_direction = original_get_direction

        # Check bad results.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["request"]["data_id"],
            "src_unl": self.bob_transfer.net.unl.value,
            "dest_unl": self.alice_transfer.net.unl.value,
            "host_unl": self.alice_transfer.net.unl.value
        }
        self.alice_transfer.contracts[contract_id] = contract

        def get_direction_wrapper(contract_id):
            return u"receive"

        original_get_direction = self.alice_transfer.get_direction
        self.alice_transfer.get_direction = get_direction_wrapper

        self.assertTrue(complete_handler(
            self.alice_transfer,
            contract_id,
            None
        ) == -1)

        self.alice_transfer.get_direction = original_get_direction

        # Test schedule new transfer.
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["request"]["data_id"],
            "src_unl": self.bob_transfer.net.unl.value,
            "dest_unl": self.alice_transfer.net.unl.value,
            "host_unl": self.alice_transfer.net.unl.value
        }
        self.alice_transfer.contracts[contract_id] = contract

        def get_direction_wrapper(contract_id):
            return u"receive"

        original_get_direction = self.alice_transfer.get_direction
        self.alice_transfer.get_direction = get_direction_wrapper

        start_time = time.time()
        end_time = start_time + 10
        self.alice_test.results = {
            "upload": {
                "transferred": int(1000),
                "start_time": int(start_time),
                "end_time": int(end_time)
            },
            "download": {
                "transferred": int(1000),
                "start_time": int(start_time),
                "end_time": int(end_time)
            }
        }

        self.alice_test.test_size = 1000

        self.assertTrue(complete_handler(
            self.alice_transfer,
            contract_id,
            None
        ) == -5)

        self.alice_transfer.get_direction = original_get_direction
        self.alice_test.test_size = 1

        # This should work:
        req = list_to_ordered_dict(copy.deepcopy(self.req))
        contract_id = "test"
        contract = {
            "data_id": req["request"]["data_id"],
            "src_unl": self.bob_transfer.net.unl.value,
            "dest_unl": self.alice_transfer.net.unl.value,
            "host_unl": self.alice_transfer.net.unl.value
        }
        self.alice_transfer.contracts[contract_id] = contract

        def get_direction_wrapper(contract_id):
            return u"receive"

        original_get_direction = self.alice_transfer.get_direction
        self.alice_transfer.get_direction = get_direction_wrapper

        start_time = time.time()
        end_time = start_time + 60
        self.alice_test.results = {
            "upload": {
                "transferred": int(1000),
                "start_time": int(start_time),
                "end_time": int(end_time)
            },
            "download": {
                "transferred": int(1000),
                "start_time": int(start_time),
                "end_time": int(end_time)
            }
        }

        self.assertTrue(complete_handler(
            self.alice_transfer,
            contract_id,
            None
        ))

        self.alice_transfer.get_direction = original_get_direction


if __name__ == "__main__":
    unittest.main()
