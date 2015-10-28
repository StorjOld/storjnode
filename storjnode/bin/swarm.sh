#!/usr/bin/env bash

bs_port=5000
bs_key=Kx7pB2r86viiTz5r33au5cg49oaXHXzjpHGAowjKpd8efz5bJomF
bs_id=ffce25851238332ec4f41d0ed57dcf7d6b125b66
swarm_port_start=5001
swarm_port_finish=5100

# known bootstrap node
screen -S testserver_$bs_port -d -m storjnode --debug --bootstrap=127.0.0.1:$bs_port --port=$bs_port --node_key=$bs_key run

# rest of the swarm
for i in `seq $swarm_port_start $swarm_port_finish`;
do
    echo "starting server $i"
    sleep 0.2
    screen -S testserver_$i -d -m storjnode --debug --bootstrap=127.0.0.1:$bs_port --port=$i run
done   

# send relay message
#screen -S testclient -d -m storjnode --debug --bootstrap=127.0.0.1:5100 --port=5501 relay_message $bs_id testit
# to kill swarm `killall screen`
