import os

# constants
PROTOCOL_VERSION = 1
THREAD_SLEEP = 0.001
MAX_PACKAGE_DATA = 548  # 576 MTU - 20 IPv4 Header - 8 UDP Header == 548

# paths
STORJ_HOME = os.path.join(os.path.expanduser("~"), ".storj")
CONFIG_PATH = os.path.join(STORJ_HOME, "cfg.json")

# bootstrap nodes
TESTGROUPC_BOOTSTRAP_NODES = [
    ["159.203.64.230", 33236],  # storj develop
    ["104.236.1.59", 28647],    # storj stable
    ["78.46.188.55", 44216],    # F483's server
    ["158.69.201.105", 12512],  # Rendezvous server 1
    ["162.218.239.6", 56112],   # IPXCORE:
    ["192.187.97.131", 34339],  # NAT test node
    ["185.86.149.128", 37308],  # Rendezvous 2
    ["185.61.148.22", 24192]    # dht msg 2
]
TESTGROUPB_BOOTSTRAP_NODES = [
    ["104.236.1.59", 59744],     # storj stable
    ["159.203.64.230", 25933],   # storj develop
    ["78.46.188.55", 16851],     # F483's server
    ["158.69.201.105", 63076],   # Rendezvous server 1
    ["162.218.239.6", 38682],   # IPXCORE:
    ["192.187.97.131", 58825],  # NAT test node
    ["185.86.149.128", 56701],  # Rendezvous 2
    ["185.61.148.22", 25029]    # dht msg 2
]
DEFAULT_BOOTSTRAP_NODES = TESTGROUPC_BOOTSTRAP_NODES
