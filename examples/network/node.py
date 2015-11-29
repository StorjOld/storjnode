import tempfile
from pyp2p.lib import get_wan_ip
from btctxstore import BtcTxStore
import storjnode
import time
from crochet import setup
setup()

# isolate swarm
bootstrap_nodes = [("127.0.0.1", 1337)]

# Create nodes.
node_no = 2
nodes = []
for i in range(0, node_no):
    # Create node.
    btctxstore = BtcTxStore(testnet=False)
    node = storjnode.network.Node(
        btctxstore.create_wallet(), port=1339 + i, ksize=8,
        bootstrap_nodes=[("127.0.0.1", 1337)],
        refresh_neighbours_interval=0.0,
        store_config={tempfile.mkdtemp(): None},
        nat_type="preserving",
        node_type="passive",
        wan_ip=get_wan_ip(),
        passive_port=10500 + i,
        disable_data_transfer=False,
        simulate_dht=True
    )

    # Record node.
    nodes.append(node)


# Test get UNL.
def callback(unl):
    print("GOT UNL!")
    print(unl)

# Output UNL when nodes respond.
nodes[0].get_unl_by_node_id(nodes[1].get_id()).addCallback(callback)

time.sleep(10)

# stop nodes
for i in range(0, node_no):
    nodes[i].stop()
