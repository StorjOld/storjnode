import os


PROTOCOL_VERSION = 1
MAX_PACKAGE_DATA = 548  # 576 MTU - 20 IPv4 Header - 8 UDP Header == 548

STORJ_HOME = os.path.join(os.path.expanduser("~"), ".storj")
CONFIG_PATH = os.path.join(STORJ_HOME, "config.json")
