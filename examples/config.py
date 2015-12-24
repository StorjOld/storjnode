import os
from storjnode.config import DEFAULT_CONFIG_PATH, create
from storjnode.config import save, validate, read
from storjnode.config import get, ConfigFile
from btctxstore import BtcTxStore
print(DEFAULT_CONFIG_PATH)

wallet = BtcTxStore()
config_file = ConfigFile(wallet)
config_file["something"] = 10
config_file["something"] = 11

# Won't work.
config_file["bandwidth"]["sec"]["downstream"] = 0
