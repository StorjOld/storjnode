"""
Run with python2.7 break_relaying.py --quiet

Like I've maintained for the past few months: the relay code is broken and this module proves that the current algorithm is unreliable. The biggest problem with the current algorithm is that its based on forming a perfect chain of nodes to create a route: node A -> node B -> node C and any breaks in the chain mean that there is no possible message route from the source to the destination. Unfortunately, the routes don't change much during the entire life time of the node (so long as there isn't massive churn in the node tables), meaning that even refreshes over time are unlikely to help the problem (this is the reason why the code was so flaky and also why no amount of time for refreshes did improved reliability in production.)

The current algorithm assumes perfect organization for the routing tables across nodes which is made impossible by differences in join time, differences in refresh interval, randomness of node IDs, chosen bootstrapping nodes (and their particular tables at any given time) and plain-bad luck. (Then add UDP to that mix and yeah ... there is no way this is reliable enough to be useful.)

The reason why we never caught this in the unit tests was our setup was too synthetic: we assumed
    * Fixed bootstrap nodes with
    * Fixed routing tables with
    * Fixed refresh intervals over the exact same time period
    * Small network sizes
    * And bootstrap nodes that contained the entire network

In production these assumptions are completely unrealistic and the result is the current algorithm doesn't work for anything in the real world.

To fix this: I would suggest some kind of n hop algorithm that sends the message out to the closest node if it can - or if it cant - send the message out to every other node in the table. Each person who receives the message increases the hop no such that the message is no longer routed when it reaches a certain threshold. The problem is - organization of the node tables is still unlikely to make this 100% reliable. If we run out of time lets just make it broadcast-based with a TTL. At least repeat_relay would be 100% reliable over a time-frame so TGC will run. It's not like TGC scalability is a huge concern.

Btw, if you doubt any of this run the program yourself. If the results still don't convince you -- try use relay_messages over WAN in your own software on the assumption that a route can be established. It won't work reliably.
"""

import heapq
import operator
import os
# import sys
import json
import cProfile
from pstats import Stats
import signal
import threading
import math
import tempfile
import time
import shutil
import copy
import binascii
import random
import unittest
import btctxstore
import storjnode
import sys
from storjkademlia.node import Node as KademliaNode
from storjkademlia.protocol import KademliaProtocol
from storjkademlia.routing import RoutingTable
from storjkademlia.routing import TableTraverser
from storjnode.network.server import QUERY_TIMEOUT, WALK_TIMEOUT
from storjnode.network.file_transfer import enable_unl_requests
import storjnode.network.process_transfers
from pyp2p.lib import get_lan_ip
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


def _findNearest(self, node, k=None, exclude=None):
    # print("In find_nearest")
    # print(exclude)
    k = k or self.ksize
    nodes = []
    for neighbor in TableTraverser(self, node):
        # print(neighbor.long_id)
        if exclude is None or not neighbor.sameHomeAs(exclude):
            heapq.heappush(nodes, (node.distanceTo(neighbor), neighbor))
        if len(nodes) == k:
            break

    return list(map(operator.itemgetter(1), heapq.nsmallest(k, nodes)))

# Patch bug in upstream router.
RoutingTable.findNeighbors = _findNearest

# Globals.
PROFILE = False
PORT = storjnode.util.get_unused_port()
STORAGE_DIR = tempfile.mkdtemp()
PASSIVE_BIND = get_lan_ip()
WAN_IP = PASSIVE_BIND

# Enum errors.
TOO_MANY_HOPS = 1
NO_NEIGHBOURS = 2
NEIGHBOURS_TOO_FAR = 3
UNKNOWN_ERROR = 4

# Results for hops.
HOP_RESULT = {
    TOO_MANY_HOPS: {
        "description": "Too many hops: hop no < default_hop_limit=64",
        "status": "disabled",
    },
    NO_NEIGHBOURS: {
        "description": "No neighbours: no nodes closer to destination" + "(nothing in routing table)",
        "status": " "
    },
    NEIGHBOURS_TOO_FAR: {
        "description": "Neighbours are too far away: our node ID is closer than any of our neighbours",
        "status": " "
    },
    UNKNOWN_ERROR: {
        "description": "Unknown error: err back result: not checked",
        "status": "disabled"
    }
}

def _test_config(storage_path, bootstrap_nodes):
    config = storjnode.config.create()
    config["network"]["refresh_neighbours_interval"] = 0
    config["network"]["bootstrap_nodes"] = bootstrap_nodes
    config["storage"] = {
        storage_path: {"limit": "5G", "use_folder_tree": False}
    }
    storjnode.config.validate(config)
    return config

class BreakRelays():
    def __init__(self, n_sleep=0, do_refresh=False, use_static_bootstrap=False, use_random_bootstrap_nodes=True, use_random_refresh_neighbours=True, net_size=40):
        # Characteristics.
        self.n_sleep = n_sleep
        self.do_refresh = do_refresh
        self.use_static_bootstrap = use_static_bootstrap
        self.use_random_bootstrap_nodes = use_random_bootstrap_nodes
        self.use_random_refresh_neighbours = use_random_refresh_neighbours
        self.net_size = net_size
        self.nodes = self.initialise_network(self.net_size)

        # Used for node lookups.
        self.alphabet = []
        for i in range(0, self.net_size):
            alphabet = "ABCDEFGHIJKLNMOPQRSTUVWXYZ"
            letter = alphabet[((i + 1) % len(alphabet)) - 1]
            number = int(math.ceil(len(alphabet) / (i + 1)))
            if not number:
                number = 1
            id = "%s%d" % (letter, number)
            self.alphabet.append(id)

    def node_to_letter(self, node):
        for i in range(0, self.net_size):
            if self.nodes[i] == node:
                return self.alphabet[i]

        raise Exception("No neat alphabet mapping for node object.")

    def get_knodes_from_node(self, node):
        kbuckets = node.server.protocol.router.buckets
        nodes = set()
        for kbucket in kbuckets:
            kbucket_nodes = kbucket.getNodes()
            for node in kbucket_nodes:
                nodes.add(node)

        return nodes

    def get_node_by_knode(self, knode):
        for i in range(0, self.net_size):
            if self.nodes[i].server.node.id == knode.id:
                return self.nodes[i]

        raise Exception("Unable to find node by knode")

    def letter_to_node(self, letter):
        for i in range(0, len(self.alphabet)):
            if letter == self.alphabet[i]:
                return self.nodes[i]

        raise Exception("Can't find node from letter")

    def random_bootstrapping_nodes(self, ports):
        bootstrap_nodes = []
        bootstrap_node_no = random.randrange(0, self.net_size)
        for i in range(0, bootstrap_node_no):
            node_index = random.randrange(0, self.net_size)
            node = ["127.0.0.1", ports[node_index]]
            if node not in bootstrap_nodes:
                bootstrap_nodes.append(node)

        return list(bootstrap_nodes)

    def generate_unused_ports(self, net_size):
        ports = []
        for i in range(0, net_size):
            port = storjnode.util.get_unused_port()
            ports.append(port)

        return ports

    def initialise_network(self, net_size):
        # Generate node ports.
        ports = self.generate_unused_ports(net_size)

        # Standard bootstrapping nodes.
        determinate_bootstrap_nodes = [
            ["127.0.0.1", ports[i]] for i in range(self.net_size)
        ]

        nodes = []
        api = btctxstore.BtcTxStore(testnet=False)
        for i in range(0, net_size):
            # Create node.
            storage_path = "{0}/peer_{1}".format(STORAGE_DIR, i)
            bootstrap_nodes = determinate_bootstrap_nodes
            if self.use_random_bootstrap_nodes:
                bootstrap_nodes = self.random_bootstrapping_nodes(ports)
            config = _test_config(storage_path, bootstrap_nodes)

            while 1:
                # Supress any rendezvous server errors.
                port = ports[i]
                try:
                    node = storjnode.network.Node(
                        api.create_wallet(), port=(port),
                        config=config,
                        nat_type="preserving",
                        node_type="passive",
                        disable_data_transfer=False,
                        passive_bind=PASSIVE_BIND,
                        wan_ip=WAN_IP
                    )
                    break
                except Exception as e:
                    print("Catch exception: " + str(e))
                    port[i] = storjnode.util.get_unused_port()
                    continue

            # Save node.
            nodes.append(node)

        # See if waiting here makes any difference.
        if self.n_sleep:
            time.sleep(self.n_sleep)

        # Re-attempt bootstrapping to see if it makes any difference.
        if self.do_refresh:
            self.aggressive_refresh_neighbours(nodes)

        return nodes

    def stop_network(self):
        for node in self.nodes:
            node.stop()

    def get_knode_by_node(self, node):
        return node.server.node

    def check_hop(self, src_node, dest_node):
        ksrc_node = self.get_knode_by_node(src_node)
        kdest_node = self.get_knode_by_node(dest_node)
        nearest = src_node.server.protocol.router.findNeighbors(
            kdest_node, exclude=ksrc_node
        )

        # Reverse nearest so it can be popped.
        if nearest is not None:
            nearest.reverse()

        next_hop = None
        hop_result = HOP_RESULT.copy()
        while 1:
            # No neighbors nearest destination.
            # Likely indicates there are no routing tables.
            if not nearest:
                hop_result[NO_NEIGHBOURS]["status"] = "x"
                break

            # do not relay away from node
            krelay_node = nearest.pop()
            relay_node = self.get_node_by_knode(krelay_node)
            # assert(krelay_node == kdest_node)

            dist_to_self = kdest_node.distanceTo(ksrc_node)
            dist_to_relay = kdest_node.distanceTo(krelay_node)
            if dist_to_self <= dist_to_relay:
                hop_result[NEIGHBOURS_TOO_FAR]["status"] = "x"
                hop_result[NEIGHBOURS_TOO_FAR]["to_self"] = dist_to_self
                hop_result[NEIGHBOURS_TOO_FAR]["to_relay"] = dist_to_relay
                break

            # Relay node may be the destination --
            # I.e. the route is over.
            next_hop = relay_node
            break

        return hop_result, next_hop

    def find_last_valid_hop(self, hops):
        for hop in hops:
            if hop == None:
                continue

            return hop

        return None

    def visualize_relaying(self, src_node, dest_node):
        ksrc_node = self.get_knode_by_node(src_node)
        kdest_node = self.get_knode_by_node(dest_node)
        buf = \
        """
Source: %s = %d
Destination: %s = %d
Algorithm: XOR metric for distance

Routing . . .

""" % (
            self.node_to_letter(src_node),
            ksrc_node.long_id,
            self.node_to_letter(dest_node),
            kdest_node.long_id
        )

        # Check route and show results:
        hops, success = self.check_route(src_node, dest_node)
        buf += self.show_route(src_node, hops) + "\r\n"

        # Indicate success status.
        if success:
            buf += "\r\nRelaying was successful\r\n\r\n"
        else:
            buf += "\r\nNo route to destination at %s\r\n\r\n" % (
                self.node_to_letter(dest_node)
            )
        buf += "-----------------------"
        buf += "--------------------------------\r\n"

        # Show nearest routing table.
        assert(hops is not None)
        last_hop = self.find_last_valid_hop(hops)
        if last_hop is not None:
            last_hop_node = list(last_hop)[0]
            if last_hop_node is None:
                last_hop_node = src_node

            if last_hop_node is not None:
                klast_hop_node = self.get_knode_by_node(last_hop_node)
                nearest = last_hop_node.server.protocol.router.findNeighbors(
                    kdest_node, exclude=klast_hop_node
                )
                nearest_routing_table = self.show_route_table(
                    last_hop_node,
                    dest_node,
                    nearest
                )
                buf += "======Nodes in %s table nearest to dest\r\n" % (
                    self.node_to_letter(last_hop_node)
                )
                buf += nearest_routing_table + "\r\n"
                if nearest:
                    if nearest[0].id == kdest_node.id:
                        buf += str(hops) + "\r\n\r\n"

                # Get remaining non-neighbour nodes.
                all_knodes = list(self.get_knodes_from_node(last_hop_node))
                remaining_knodes = list(all_knodes)[:]
                for knode in all_knodes:
                    for nearest_knode in nearest:
                        if knode.id == nearest_knode.id:
                            for remaining_knode in remaining_knodes[:]:
                                if remaining_knode.id == knode.id:
                                    remaining_knodes.remove(remaining_knode)
                                    break

                # Show remaining non-neighbour nodes.
                remaining_routing_table = self.show_route_table(
                    last_hop_node,
                    dest_node,
                    remaining_knodes
                )
                buf += "======Nodes in %s table not nearest to dest\r\n" % (
                    self.node_to_letter(last_hop_node)
                )
                buf += remaining_routing_table + "\r\n\r\n"

                # Show violations.
                buf += "======Violations\r\n"
                try:
                    last_hop_result = last_hop[last_hop_node]
                except:
                    last_hop_result = last_hop[None]
                for result_key in list(last_hop_result):
                    lhr = last_hop_result[result_key]
                    status = lhr["status"]
                    description = lhr["description"]
                    buf += "[%s] %s\r\n" % (status, description)

        # Show characteristics.
        buf += "\r\n======Characteristics\r\n"
        buf += "[%d] Sleep after node loop (%d second)\r\n" % (
            self.n_sleep,
            self.n_sleep
        )
        buf += "[%s] Refresh\r\n" % (str(self.do_refresh))
        buf += "[%s] Random refreshes\r\n" % (
            str(self.use_random_refresh_neighbours)
        )
        buf += "[%s] Static routing tables\r\n" % (
            str(self.use_static_bootstrap)
        )
        buf += "[%s] Random bootstrap nodes\r\n" % (
            str(self.use_random_bootstrap_nodes)
        )
        buf += "[%d] Network size / number of nodes\r\n" % (
            self.net_size
        )
        buf += "\r\n"

        # Return success status.
        return buf, success

    def show_route(self, src_node, hops):
        buf = self.node_to_letter(src_node)
        broken_route = " --\--- "
        unbroken_route = " ---> "
        for hop in hops:
            if list(hop)[0] == None:
                buf += broken_route
                break

            buf += unbroken_route
            buf += self.node_to_letter(list(hop)[0])

        return buf

    def show_route_table(self, src_node, dest_node, kfound_nodes=None):
        if kfound_nodes is not None:
            if not len(kfound_nodes):
                return "No nodes in this table"

        kfound_nodes = kfound_nodes or self.get_knodes_from_node(src_node)
        buf = ""
        dest_letter = self.node_to_letter(dest_node)
        kdest_node = self.get_knode_by_node(dest_node)
        for kfound_node in kfound_nodes:
            found_node = self.get_node_by_knode(kfound_node)
            found_letter = self.node_to_letter(found_node)
            xor_result = kfound_node.distanceTo(kdest_node)
            buf += "%s (%d): %s XOR %s = %d\r\n" % (
                found_letter,
                kfound_node.long_id,
                found_letter,
                dest_letter,
                xor_result
            )

        return buf

    def check_route(self, src_node, dest_node):
        hops = []
        next_hop = dest_node
        while next_hop is not None:
            hop_result, next_hop = self.check_hop(src_node, dest_node)
            if next_hop == src_node:
                hop = {None: hop_result}
            else:
                hop = {next_hop: hop_result}
            hops.append(hop)

            # Destination found.
            if next_hop == dest_node:
                break
            else:
                src_node = next_hop

        success = False
        if hops[-1] is not None:
            if list(hops[-1])[0] == dest_node:
                success = True

        return hops, success

    def is_node_in_routing_tables(self, needle_node, haystack_node):
        kneedle_node = self.get_knode_by_node(needle_node)
        kfound_nodes = self.get_knodes_from_node(haystack_node)
        for kfound_node in kfound_nodes:
            if kfound_node.id == kneedle_node.id:
                return True

        return False

    def check_every_possible_route(self):
        for node in self.nodes:
            for dest_node in self.nodes:
                if node == dest_node:
                    continue

                buf, success = self.visualize_relaying(node, dest_node)
                if not success:
                    return buf

        return None

    def aggressive_refresh_neighbours(self, nodes):
        # Everything needs to match behaviour on the main network.
        n = 1 if self.use_random_refresh_neighbours else 5
        for i in range(0, n):
            for node in nodes:
                # Simulate random refresh intervals on main network.
                # Odds won't be this good on the main network.
                if self.use_random_refresh_neighbours:
                    if random.randrange(0, 20) == 10:
                        node.server.refresh_neighbours()
                else:
                    node.server.refresh_neighbours()

            # In reality -- this would be 15 minutes.
            # Effectively network results for with sleep are how
            # The software start off.
            # node.server._refresh_neighbours_interval
            time.sleep(1)

def vary_network_characteristics(attempts=1):
    # Record test results.
    success_tests = [
        "without_sleep",
        "with_sleep",
        "with_refresh"
    ]

    for i in range(0, attempts):
        # Loop through different characistics
        # -- calling check every possible
        if "without_sleep" in success_tests:
            x = BreakRelays(n_sleep=0)
            ret = x.check_every_possible_route()
            if ret is not None:
                print("Without sleep is unreliable")
                print(ret)
                success_tests.remove("without_sleep")

            x.stop_network()


        if "with_sleep" in success_tests:
            x = BreakRelays(n_sleep=5)
            ret = x.check_every_possible_route()
            if ret is not None:
                print("With sleep is unreliable")
                print(ret)
                success_tests.remove("with_sleep")

            x.stop_network()

        if "with_refresh" in success_tests:
            x = BreakRelays(do_refresh=True)
            ret = x.check_every_possible_route()
            if ret is not None:
                print("With aggressive refresh is unreliable")
                print(ret)
                success_tests.remove("with_refresh")

            x.stop_network()

        if not len(success_tests):
            break

    if len(success_tests):
        print("These tests passed: %s" % success_tests)

    if not len(success_tests):
        print("All tests failed at least once")

vary_network_characteristics(attempts=20)

