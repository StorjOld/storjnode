"""
Handles P2P connections.
All networking functions are ultimately done through
this class.
"""

import socket
import random
import urllib.request
import select
import netifaces
import copy
from threading import Thread
import hashlib


from .upnp import *
from .nat_pmp import NatPMP
from .lib import *
from .sock import *
from .rendezvous_client import *
from .hybrid_reply import *

#How many times a single message can be retransmitted.
max_retransmissions = 100

#Minimum time that must pass between retransmissions.
min_retransmit_interval = 5

#A theoretical time for a message to propagate across the network.
propagation_delay = 5

#A table of message hashes for received messages.
seen_messages = {} 

def is_msg_old(msg):
    if type(msg) == str:
        msg = msg.encode("ascii")
    response_hash = hashlib.sha256(msg).hexdigest()
    if response_hash in seen_messages:
        seen = seen_messages[response_hash]
        elapsed = int(time.time()) - seen["last"]
        if elapsed < min_retransmit_interval:
            return 1

        if seen["times"] >= max_retransmissions:
            return 1

    return 0

def record_msg_hash(msg):
    if type(msg) == str:
        msg = msg.encode("ascii")
    response_hash = hashlib.sha256(msg).hexdigest()

    if not is_msg_old(msg):
        timestamp = int(time.time())
        if response_hash in seen_messages:
            seen = seen_messages[response_hash]
            seen["times"] += 1
            seen["last"] = timestamp
        else:
            seen_messages[response_hash] = {
                "times": 1,
                "last": timestamp
            }

        return 1
    else:
        return 0

class Net():
    def __init__(self, nat_type="unknown", node_type="unknown", max_outbound=10, max_inbound=10, passive_bind="127.0.0.1", passive_port=50500, forwarding_servers=None, rendezvous=None, interface="default", local_only=0, error_log_path="error.log"):
        self.nodes = {}
        self.outbound = []
        self.inbound = []
        self.passive = None
        self.rendezvous = rendezvous
        self.node_type = node_type
        self.nat_type = nat_type
        self.passive_bind = passive_bind
        self.passive_port = int(passive_port)
        self.max_outbound = int(max_outbound)
        self.max_inbound = int(max_inbound)
        self.forwarding_servers = forwarding_servers
        self.last_bootstrap = None
        self.last_listen = None
        self.rendezvous_interval = 2 * 60 #How often to bootstrap.
        self.interface = interface
        self.min_connected = 3
        self.is_accepting_clients = 0
        self.is_passive_sim_opening = 0
        self.sim_open_interval = 2
        self.last_passive_sim_open = 0
        self.enable_bootstrap = 1
        self.enable_advertise = 1
        self.enable_forwarding = 1
        self.seen_messages = {}
        self.error_log_path = error_log_path
        self.local_only = local_only
        self.forwarding_type = "manual"

    def disable_bootstrap(self):
        self.enable_bootstrap = 0

    def disable_advertise(self):
        self.enable_advertise = 0

    def disable_forwarding(self):
        self.enable_forwarding = 0

    def get_connection_no(self):
        return (len(self.outbound) + len(self.inbound))

    def validate_node(self, node_ip, node_port=None, same_nodes=1):
        """
        Don't accept connections from self to passive server
        or connections to already connected nodes.
        """
        #Don't connect to ourself.
        if node_ip == "127.0.0.1" or node_ip == get_lan_ip(self.interface) or node_ip == get_wan_ip():
            return 0

        #No, really: don't connect to ourself.
        if node_ip == self.passive_bind and node_port == self.passive_port:
            return 0

        #Don't connect to same nodes.
        if same_nodes:
            for node in self.outbound + self.inbound:
                try:
                    addr, port = node["con"].s.getpeername()
                    if node_ip == addr:
                        return 0
                except:
                    return 0
        
        return 1

    def add_node(self, node_ip, node_port, node_type, timeout=5):
        #Correct tpye for port.
        node_port = int(node_port)

        #Already connected.
        for node in self.outbound + self.inbound:
            if node_ip == node["ip"]:
                return node["con"]

        #Avoid connecting to ourself.
        if not self.validate_node(node_ip, node_port):
            return None
        
        #Simultaneous open.
        if node_type == "simultaneous":
            if self.nat_type != "random" and self.nat_type != "reuse":
                #Attempt to make active simultaneous connection.
                old_timeout = self.rendezvous.timeout
                try:
                    self.rendezvous.timeout = timeout
                    con = self.rendezvous.simultaneous_challenge(node_ip, node_port, "TCP")
                except Exception as e:
                    error = parse_exception(e)
                    log_exception(self.error_log_path, error)
                    return None
                self.rendezvous.timeout = old_timeout

                #Record node details and return con.
                self.rendezvous.simultaneous_cons = []
                if con != None:
                    node = {
                        "con": con,
                        "type": "simultaneous",
                        "ip": node_ip,
                        "port": 0
                    }
                    self.outbound.append(node)
                    return con

        #Passive outbound.
        if node_type == "passive":
            try:
                #Try connect to passive server.
                con = Sock(node_ip, node_port, blocking=0, timeout=timeout, interface=self.interface)
                node = {
                    "con": con,
                    "type": "passive",
                    "ip": node_ip,
                    "port": node_port
                }
                self.outbound.append(node)
                return con
            except Exception as e:
                error = parse_exception(e)
                log_exception(self.error_log_path, error)
                return None
        
        return None

    def bootstrap(self):
        """
        When the software is first started, it needs to retrieve
        a list of nodes to connect to the network to. This function
        asks the server for N nodes which consists of at least N
        passive nodes and N simultaneous nodes. The simultaneous
        nodes are prioritized if the node_type for the machine
        running this software is simultaneous, with passive nodes
        being used as a fallback. Otherwise, the node exclusively
        uses passive nodes to bootstrap.

        This algorithm is designed to preserve passive node's
        inbound connection slots.
        """
        #Disable bootstrap.
        if not self.enable_bootstrap:
            return

        #Avoid raping the rendezvous server.
        t = time.time()
        if self.last_bootstrap != None:
            if t - self.last_bootstrap <= self.rendezvous_interval:
                return
        self.last_bootstrap = t

        try:
            connection_slots = self.max_outbound - len(self.outbound)
            passive_outbound = []
            simultaneous_outbound = []
            if connection_slots > 0:
                #Connect to rendezvous server.
                rendezvous_con = Sock(self.rendezvous.rendezvous_servers[0]["addr"], self.rendezvous.rendezvous_servers[0]["port"], blocking=1, interface=self.interface, timeout=3)

                #Retrieve random nodes to bootstrap with.
                rendezvous_con.send_line("BOOTSTRAP " + str(self.max_outbound * 2))
                choices = rendezvous_con.recv_line()
                if choices == "NODES EMPTY":
                    rendezvous_con.close()
                    return
                choices = re.findall("(?:(p|s)[:]([0-9]+[.][0-9]+[.][0-9]+[.][0-9]+)[:]([0-9]+))+\s?", choices)
                rendezvous_con.s.close()

                #Attempt to make active simultaneous connections.
                passive_nodes = []
                for node in choices:
                    #Out of connection slots.
                    if not connection_slots:
                        break

                    #Simultaneous nodes.
                    node_type, node_ip, node_port = node
                    if node_type == "s":
                        con = self.add_node(node_ip, node_port, "simultaneous")
                        if con != None:
                            connection_slots -= 1

                    #Passive nodes.
                    if node_type == "p":
                        passive_nodes.append(node)

                #Use passive nodes to make up the difference.
                i = 0
                while i < len(passive_nodes) and connection_slots > 0:
                    node_type, node_ip, node_port = passive_nodes[i]
                    con = self.add_node(node_ip, node_port, "passive")
                    if con != None:
                        connection_slots -= 1

                    i += 1

        except Exception as e:
            error = parse_exception(e)
            log_exception(self.error_log_path, error)

    def advertise(self):
        #Avoid raping the rendezvous server.
        t = time.time()
        if self.last_listen != None:
            if t - self.last_listen <= self.rendezvous_interval:
                return
            if len(self.inbound) >= self.min_connected:
                return
        self.last_bootstrap = t

        try:
            if self.node_type == "passive" and self.passive_port != None and self.enable_advertise:
                self.rendezvous.passive_listen(self.passive_port, self.max_inbound)

            """
            Simultaneous open is only used as a fail-safe for connections to nodes on the direct_net and only direct_net can list itself as simultaneous so its safe to leave this enabled.
            """
            if self.node_type == "simultaneous":
                self.rendezvous.simultaneous_listen()
        except Exception as e:
            error = parse_exception(e)
            log_exception(self.error_log_path, error)
        self.is_accepting_clients = 1

    def determine_node(self):
        #Manually set node_type as simultaneous.
        if self.node_type == "simultaneous":
            if self.nat_type != "unknown":
                return "simultaneous"

        #Passive node checks.
        lan_ip = get_lan_ip(self.interface)
        if lan_ip != None and self.passive_port != None and self.enable_forwarding:
            #Check port isn't already forwarded.
            if is_port_forwarded(lan_ip, self.passive_port, "TCP", self.forwarding_servers):
                self.forwarding_type = "mapped"
                return "passive"

            #Most routers.
            try:
                print("Starting UPnP")
                UPnP(self.interface).forward_port("TCP", self.passive_port, lan_ip)
                print("Ending UPnP")
                if is_port_forwarded(lan_ip, self.passive_port, "TCP", self.forwarding_servers):
                    self.forwarding_type = "UPnP"
            except:
                #Apple devices.
                try:
                    print("Starting NATPMP")
                    NatPMP(self.interface).forward_port("TCP", self.passive_port, lan_ip)
                    print("Ending NATPMP")
                    if is_port_forwarded(lan_ip, self.passive_port, "TCP", self.forwarding_servers):
                        self.forwarding_type = "NATPMP"
                except:
                    pass

            #Check it worked.
            print("Port forward 2")
            print(self.passive_port)
            if self.forwarding_type != "manual":
                print("Open.")
                return "passive"

        #Fail-safe node types.
        if self.nat_type != "unknown":
            return "simultaneous"
        else:
            return "active"

    def start_passive_server(self):
        self.passive = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.passive.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.passive.bind((self.passive_bind, self.passive_port))
        self.passive.listen(self.max_inbound)

    def start(self):
        #Determine NAT type.
        if self.nat_type == "unknown":
            try:
                nat_type = self.rendezvous.determine_nat()
                if nat_type != None and nat_type != "unknown":
                    self.nat_type = nat_type
                    self.rendezvous.nat_type = nat_type
            except:
                pass

        #Determine node type.
        self.start_passive_server()
        if self.node_type == "unknown":
            self.node_type = self.determine_node()

        #Close stray cons from determine_node() tests.
        self.close_cons()

    def stop(self):
        pass

    def filter_old_messages(self, msg, bypass_filter=0):
        #Invalid type.
        if type(msg) != str and type(msg) != HybridReply and (not callable(msg)):
            return 0

        #Extract msg from hybrid reply object.
        if type(msg) == HybridReply:
            #Bypass filter.
            if not msg.record_seen:
                bypass_filter = 1

            #Nestled reply messages.
            if type(msg.msg) == list:
                for sub_msg in msg.msg:
                    ret = self.filter_old_messages(sub_msg, bypass_filter)
                    if not ret:
                        return 0

                return 1
            else:
                #Message is dynamic so it will be unique.
                msg = msg.msg
                if callable(msg):
                    return 1

        #Process msg.
        if is_msg_old(msg):
            return 0
        else:
            if not bypass_filter:
                record_msg_hash(msg)
            return 1

    def con_by_ip(self, ip):
        for node in self.outbound + self.inbound:
            if node["ip"] == ip:
                return node["con"]

        return None
        
    def broadcast(self, msg, source_con=None):
        #Todo: only if they've paid a small fee or solved proof of work
        for node in self.outbound + self.inbound:
            if node["con"] != source_con:
                node["con"].send_line(msg)

    def close_cons(self):
        #Close all connections.
        for node in self.inbound + self.outbound:
            node["con"].close()

        #Flush client queue for passive server.
        if self.node_type == "passive" and self.passive != None:
            self.passive.close()
            self.start_passive_server()

        #Start from scratch.
        self.inbound = []
        self.outbound = []

    def synchronize(self):
        #Todo: rebootstrap if needed. *
        #Todo: relist passive and simultanous if needed.
        #Todo: quit
        #Todo: code reconnect *

        #Clean up dead connections.
        for node_list_name in ["self.inbound", "self.outbound"]:
            node_list = eval(node_list_name)[:]
            for node in node_list:
                if not node["con"].connected:
                    eval(node_list_name).remove(node)

        #Accept new passive inbound connections.
        if len(self.inbound) < self.max_inbound:
            #Tell rendezvous server to list us.
            if not self.is_accepting_clients:
                self.bootstrap()
                self.advertise()

            if self.passive != None:
                r, w, e = select.select([self.passive], [], [], 0)
                for s in r:
                    if s == self.passive: 
                        client, address = self.passive.accept()
                        con = Sock()
                        con.set_sock(client)
                        node_ip, node_port = con.s.getpeername()
                        if self.validate_node(node_ip, node_port):
                            node = {
                                "type": "accept",
                                "con": con,
                                "ip": con.s.getpeername()[0],
                                "port": con.s.getpeername()[1],
                            }
                            self.inbound.append(node)
                        else:
                            con.close()

                        #QUIT.
                        if len(self.inbound) == self.max_inbound:
                            try:
                                self.rendezvous.leave_fight()
                                self.is_accepting_clients = 0
                            except:
                                continue

        #Accept new passive simultaneous connections.
        if self.node_type == "simultaneous":
            """
            This is basically the code that passive simultaneous
            nodes periodically call to parse any responses from the
            Rendezvous Server which should hopefully be new
            requests to initiate hole punching from active
            simultaneous nodes.

            If a challenge comes in, the passive simultaneous
            node accepts the challenge by giving details to the
            server for the challenging node (active simultaneous)
            to complete the simultaneous open.
            """
            if len(self.inbound) < self.max_inbound:
                #Tell rendezvous server to relist us.
                if not self.is_accepting_clients:
                    self.bootstrap()
                    self.advertise()

                #try:
                t = time.time()
                if self.rendezvous.server_con != None:
                    for reply in self.rendezvous.server_con:
                        #Reconnect.
                        if re.match("^RECONNECT$", reply) != None:
                            self.rendezvous.simultaneous_listen()
                            continue

                        #Find any challenges.
                        #CHALLENGE 192.168.0.1 50184 50185 50186 50187 TCP
                        parts = re.findall("^CHALLENGE ([0-9]+[.][0-9]+[.][0-9]+[.][0-9]+) ((?:[0-9]+\s?)+) (TCP|UDP)$", reply)
                        if not len(parts):
                            continue
                        candidate_ip, candidate_predictions, candidate_proto = parts[0]

                        #Already connected.
                        if not self.validate_node(candidate_ip):
                            continue

                        #Last meeting was too recent.
                        if t - self.last_passive_sim_open < self.sim_open_interval:
                            continue

                        #Accept challenge.
                        our_ntp = get_ntp()
                        if our_ntp == None:
                            continue
                        msg = "ACCEPT %s %s TCP %s" % (candidate_ip, self.rendezvous.predictions, str(our_ntp))
                        ret = self.rendezvous.server_con.send_line(msg)
                        if not ret:
                            continue

                        """
                        Adding threading here doesn't work because Python's
                        fake threads and the act of starting a thread ruins
                        the timing between code synchronisation - especially
                        code running on the same host or in a LAN. Will
                        compensate by reducing the NTP delay to have the
                        meetings occur faster and setting a limit for meetings
                        to occur within the same period. 
                        """
                        #Walk to fight and return holes made.
                        self.last_passive_sim_open = t
                        con = self.rendezvous.attend_fight(self.rendezvous.mappings, candidate_ip, candidate_predictions, our_ntp)
                        if con != None:
                            node = {
                                "type": "simultaneous",
                                "con": con,
                                "ip": con.s.getpeername()[0],
                                "port": con.s.getpeername()[1],
                            }
                            self.inbound.append(node)

                        #Create new predictions ready to accept next client.
                        self.rendezvous.simultaneous_cons = []
                        self.rendezvous.simultaneous_listen()

                        #Quit
                        if len(self.inbound) == self.max_inbound:
                            if self.rendezvous.server_con != None:
                                self.rendezvous.server_con.send_line("CLEAR")
                                self.rendezvous.server_con.close()
                                self.is_accepting_clients = 0

        #Bootstrap again if needed.
        self.bootstrap()
                    
    """
    These functions here make the class behave like a list. The
    list is a collection of connections (inbound) + (outbound.)
    Every iteration also has the bonus of reaping dead connections,
    making new ones (if needed), and accepting connections
    """
    def __len__(self):
        self.synchronize()
        return len(self.inbound) + len(self.outbound)

    def __iter__(self):
        #Process connections.
        self.synchronize()

        cons = []
        for node in self.inbound:
            cons.append(node["con"])
        for node in self.outbound:
            cons.append(node["con"])

        #Filter(): Remove old messages from replies.
        #Todo: record message hash?
        def old_msg_check(msg):
            return not is_msg_old(msg)

        #Patch sock objects to reject duplicate replies.
        for con in cons:
            con.reply_filter = old_msg_check

        #Return patched socks.
        return iter(cons)

if __name__ == "__main__":
    pass
