"""
Universal Node Locator (UNL.) Allows nodes to direct connect and helps to debug issues in doing so.
"""

from .globals import *
from .lib import *
import time
import bitcoin.base58
import struct
import random
import binascii

class UNL():
    def __init__(self, net):
        self.version = 1
        self.net = net
        self.nat_type_lookup = {
            "m": "random",
            "g": "preserving",
            "e": "reuse"
        }

        self.forwarding_type_lookup = {
            "m": "mapped",
            "U": "UPnP",
            "N": "NATPMP"
        }

        self.node_type_lookup = {
            "p": "passive",
            "a": "active",
            "s": "simultaneous"
        }

    def connect(self, our_unl, their_unl):
        #Figure out who should make the connection.
        int_our_unl = int(binascii.hexlify(our_unl), 16)
        int_their_unl = int(binascii.hexlify(their_unl), 16)
        if int_our_unl > int_their_unl:
            master = 1
        else:
            master = 0

        #Deconstruct binary UNLs into dicts.
        our_unl = self.deconstruct(our_unl)
        their_unl = self.deconstruct(their_unl)
        if our_unl == None:
            raise Exception("Unable to deconstruct our UNL.")
        if their_unl == None:
            raise Exception("Unable to deconstruct their UNL.")

        print(our_unl)
        print(their_unl)

        #Active nodes can't connect to each other.
        if our_unl["node_type"] == "active" and \
        their_unl["node_type"] == "active":
            raise Exception("No way for nodes to connect.")

        #This means the nodes are behind the same router.
        if our_unl["wan_ip"] == their_unl["wan_ip"]:
            #Connect to LAN IP.
            our_unl["wan_ip"] = our_unl["lan_ip"]
            their_unl["wan_ip"] = their_unl["lan_ip"]

            #Already behind NAT so no forwarding needed.
            our_unl["node_type"] = "passive"
            their_unl["node_type"] = "passive"
            

        print("Master = " + str(master))

        #Are they already connected?
        con = self.net.con_by_ip(their_unl["wan_ip"])
        if con != None:
            return their_unl["wan_ip"]

        #Valid node types.
        for node_type in ["passive", "simultaneous"]:
            #Matches for this node type.
            nodes = []
            if our_unl["node_type"] == node_type:
                nodes.append(our_unl)

            if their_unl["node_type"] == node_type:
                nodes.append(their_unl)

            #Try the next node type.
            if len(nodes):
                #We only want one connection.
                if len(nodes) == 2:
                    if not master:
                        #They will connect to us.
                        nodes.remove(their_unl)
                    else:
                        #We will connect to them.
                        nodes.remove(our_unl)

                #Don't connect to ourself.
                node = nodes[0]
                if node == their_unl:
                    if self.net.add_node(their_unl["wan_ip"], their_unl["passive_port"], their_unl["node_type"], timeout=60) != None:
                        return their_unl["wan_ip"]
                else:
                    #They will connect to us.
                    for i in range(0, 60):
                        con = self.net.con_by_ip(their_unl["wan_ip"])
                        if con != None:
                            return their_unl["wan_ip"]

                        time.sleep(1)
                    
        #Invalid node types.
        raise Exception("Unable to setup direct connect.")

    def deconstruct(self, unl):
        try:
            #Separate checksum.
            unl = bitcoin.base58.decode(unl)
            checksum_size = 4
            checksum = unl[-checksum_size:]
            unl = unl[:-checksum_size]

            #Check checksum.
            expected_checksum = hashlib.sha256(hashlib.sha256(unl).digest()).digest()
            expected_checksum = expected_checksum[0:4]
            if checksum != expected_checksum:
                raise Exception("Invalid checksum -- UNL is probably corrupt.")

            #Separate the other fields.
            version, node_type, nat_type, forwarding_type, passive_port, wan_ip, lan_ip, timestamp, nonce = struct.unpack("<BBBBHIIQI", unl)
            node_type = chr(node_type)
            node_type = self.node_type_lookup[node_type]
            nat_type = chr(nat_type)
            nat_type = self.nat_type_lookup[nat_type]
            forwarding_type = chr(forwarding_type)
            forwarding_type = self.forwarding_type_lookup[forwarding_type]
            wan_ip = int2ip(wan_ip)
            lan_ip = int2ip(lan_ip)

            #Return meaningful fields.
            ret = {
                "version": version,
                "node_type": node_type,
                "nat_type": nat_type,
                "forwarding_type": forwarding_type,
                "passive_port": passive_port,
                "wan_ip": wan_ip,
                "lan_ip": lan_ip,
                "timestamp": timestamp,
                "nonce": nonce
            }

            return ret
        except Exception as e:
            print(e)
            return None

    def construct(self):
        #Translate bind address.
        wan_ip = get_wan_ip()
        unspecific_bind = ["0.0.0.0", "127.0.0.1", wan_ip, "localhost"]
        if self.net.passive_bind in unspecific_bind:
            lan_ip = get_lan_ip(self.net.interface)
        else:
            lan_ip = self.net.passive_bind

        #Generate UNL.
        unl = struct.pack("<BBBBHIIQI", \
            self.version,
            ord(self.net.node_type[0]),
            ord(self.net.nat_type[-1]),
            ord(self.net.forwarding_type[0]),
            self.net.passive_port,
            ip2int(wan_ip),
            ip2int(lan_ip),
            int(time.time()),
            random.randrange(0, 2 ** (4 * 8))
        )

        #Build checksum and make base58.
        checksum = hashlib.sha256(hashlib.sha256(unl).digest()).digest()
        checksum = checksum[0:4]
        unl = unl + checksum
        unl = bitcoin.base58.encode(unl)
        
        return unl

if __name__ == "__main__":
    global direct_net
    unl = UNL(direct_net)
    print(unl.construct())

    print(unl.deconstruct('x'))

    #print(unl.deconstruct(unl.construct()))


