import os

# constants
PROTOCOL_VERSION = 1
THREAD_SLEEP = 0.001
MAX_PACKAGE_DATA = 548  # 576 MTU - 20 IPv4 Header - 8 UDP Header == 548

# paths
STORJ_HOME = os.path.join(os.path.expanduser("~"), ".storj")
CONFIG_PATH = os.path.join(STORJ_HOME, "cfg.json")

DEFAULT_BOOTSTRAP_NODES = [
    ["104.236.1.59", 4653],     # storj stable
    ["104.236.1.59", 59744],    # storj stable
    ["159.203.64.230", 4653],   # storj develop
    ["159.203.64.230", 25933],  # storj develop
    ["78.46.188.55", 4653],     # F483's server
    ["78.46.188.55", 16851],    # F483's server
    ["158.69.201.105", 6770],   # Rendezvous server 1
    ["158.69.201.105", 63076],  # Rendezvous server 1
    ["162.218.239.6", 35839],   # IPXCORE:
    ["162.218.239.6", 38682],   # IPXCORE:
    ["192.187.97.131", 10322],  # NAT test node
    ["192.187.97.131", 58825],  # NAT test node
    ["185.86.149.128", 20560],  # Rendezvous 2
    ["185.86.149.128", 56701],  # Rendezvous 2
    ["185.61.148.22", 18825],   # dht msg 2
    ["185.61.148.22", 25029],   # dht msg 2
]
