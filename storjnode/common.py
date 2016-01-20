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
    ["159.203.64.230", 33236],   # storj develop
    ["104.236.1.59", 28647],     # storj stable
]
TESTGROUPB_BOOTSTRAP_NODES = [
    ["104.236.1.59", 4653],     # storj stable
    ["159.203.64.230", 4653],   # storj develop
    ["78.46.188.55", 4653],     # F483's server
    ["158.69.201.105", 6770],   # Rendezvous server 1
    ["162.218.239.6", 35839],   # IPXCORE:
    ["192.187.97.131", 10322],  # NAT test node
    ["185.86.149.128", 20560],  # Rendezvous 2
    ["185.61.148.22", 18825]    # dht msg 2
]
DEFAULT_BOOTSTRAP_NODES = TESTGROUPC_BOOTSTRAP_NODES
