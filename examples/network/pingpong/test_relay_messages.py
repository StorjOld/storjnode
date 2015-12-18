import signal
import time
import storjnode
import btctxstore
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


btctxstore = btctxstore.BtcTxStore(testnet=False)
wallet = btctxstore.create_wallet()


skunk = storjnode.network.Node(
    btctxstore.create_key(),
    bootstrap_nodes=[("240.0.0.0", 1337)],  # no bootstrap nodes (isolate)
    refresh_neighbours_interval=0.0,
    disable_data_transfer=True
)
robin = storjnode.network.Node(
    btctxstore.create_key(),
    bootstrap_nodes=[("127.0.0.1", skunk.port)],  # only knows skunk
    refresh_neighbours_interval=0.0,
    disable_data_transfer=True
)


def message_handler(node, message):
    # handler prints received value and sends it back incremented by 1
    src_node_id, value = message
    address = storjnode.util.node_id_to_address(src_node_id)
    print("{0} sent {1}".format(address, value))
    node.relay_message(src_node_id, [node.get_id(), value + 1])


skunk.add_message_handler(message_handler)
robin.add_message_handler(message_handler)

# initial message
skunk.relay_message(robin.get_id(), [skunk.get_id(), 0])


try:
    while True:
        time.sleep(0.1)  # run forever
except KeyboardInterrupt:
    pass
finally:
    skunk.stop()
    robin.stop()
