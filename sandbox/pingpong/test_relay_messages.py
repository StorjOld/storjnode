import yappi
import signal
import random
import time
import storjnode
import btctxstore
from crochet import setup
from storjnode.network.server import WALK_TIMEOUT
yappi.start()


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


SIZE = 128
KSIZE = 10
PORT = 5000
BOOTSTRAP_NODES = [("127.0.0.1", PORT)]


def message_handler(node, message):
    # handler prints received value and sends it back incremented by 1
    src_node_id, value = message
    address = storjnode.util.node_id_to_address(src_node_id)
    print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX {0} sent {1}".format(address, value))
    node.relay_message(src_node_id, [node.get_id(), value + 1])


btctxstore = btctxstore.BtcTxStore()
swarm = []
try:
    # create swarm
    for i in range(SIZE):
        port = PORT + i
        node_key = btctxstore.create_key()
        peer = storjnode.network.Node(node_key, port=port, ksize=KSIZE,
                                      refresh_neighbours_interval=0.0,
                                      bootstrap_nodes=BOOTSTRAP_NODES)
        swarm.append(peer)
        print("Started peer {0} on port {1}.".format(i, port))

    # refresh nodes
    print("refreshing neighbours")
    time.sleep(WALK_TIMEOUT)
    for node in swarm:
        node.refresh_neighbours()
    time.sleep(WALK_TIMEOUT)
    for node in swarm:
        node.refresh_neighbours()
    time.sleep(WALK_TIMEOUT)

    # start relay loop
    while True:
        try:
            alice = random.choice(swarm)
            bob = random.choice(swarm)
            assert(alice is not bob)
            alice_peers = list(map(lambda n: n.id, alice.get_known_peers()))
            bob_peers = list(map(lambda n: n.id, bob.get_known_peers()))
            assert(bob.get_id() not in alice_peers)
            assert(alice.get_id() not in bob_peers)

            print("start relying messages")
            alice.add_message_handler(message_handler)
            bob.add_message_handler(message_handler)
            alice.relay_message(bob.get_id(), [alice.get_id(), 0])
            break
        except AssertionError:
            print("unusable alice and bob")

    # serve forever
    print("Running swarm with {0} ...".format(len(swarm)))
    while True:
        time.sleep(0.1)

except KeyboardInterrupt:
    pass

finally:
    print("Stopping nodes")
    for node in swarm:
        node.stop()

yappi.get_func_stats().print_all()
yappi.get_thread_stats().print_all()
