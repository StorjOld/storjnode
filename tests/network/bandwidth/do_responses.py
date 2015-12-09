# todo: finish this modle.
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

    def test_handle_responses(self):
        handle_requests = handle_requests_builder(self.bob_test)
        res = handle_requests(
            self.alice_dht,
            self.alice_node_id,
            self.req
        )
        print(res)
        pass

if __name__ == "__main__":
    unittest.main()
