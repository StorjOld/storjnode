import storjnode
import btctxstore

print(storjnode.config.DEFAULT_CONFIG_PATH)
config = storjnode.config.get(btctxstore.BtcTxStore(),
                              storjnode.config.DEFAULT_CONFIG_PATH)
print(config)
