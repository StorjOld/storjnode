import storjnode
import subprocess

for transport_address in storjnode.network.node.DEFAULT_BOOTSTRAP_NODES:
    print(subprocess.Popen(["/bin/ping", "-c1", "-w100", transport_address[0]],
                           stdout=subprocess.PIPE).stdout.read(), "\n")
