import os

# constants
PROTOCOL_VERSION = 1
THREAD_SLEEP = 0.1
MAX_PACKAGE_DATA = 548  # 576 MTU - 20 IPv4 Header - 8 UDP Header == 548

# paths
STORJ_HOME = os.path.join(os.path.expanduser("~"), ".storj")
CONFIG_PATH = os.path.join(STORJ_HOME, "cfg.json")

DEFAULT_BOOTSTRAP_NODES = [
    # TODO storj_uswest01
    ["159.203.150.90", 10000],   # storj_useast01
    ["46.101.71.172", 10000],    # storj_eu01
    ["188.166.207.187", 10000],  # storj_asia01
]
