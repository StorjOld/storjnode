from .net import *

nat_type = "unknown"
node_type = "unknown"
interface = "default"
max_outbound = 10
max_inbound = 10
passive_bind = "0.0.0.0"
passive_port = "44444"
rendezvous_servers = [
    {
        "addr": "127.0.0.1",
        "bind": "0.0.0.0",
        "port": 8000
    }
]
forwarding_servers = 


p2p_rendezvous = RendezvousClient(nat_type, config["rendezvous_servers"], interface)
p2p_net = Net(nat_type, node_type, max_outbound, max_inbound, passive_bind, passive_port, config["forwarding_servers"], p2p_rendezvous, interface, local_only, error_log_path=error_log_path)
if args.skipforwarding != None:
    p2p_net.disable_forwarding()
p2p_net.start()
