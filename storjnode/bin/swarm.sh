#!/usr/bin/env bash

# known bootstrap node
screen -S testserver_5000 -d -m storjnode --debug --bootstrap=127.0.0.1:5000 --port=5000 --node_key=Kx7pB2r86viiTz5r33au5cg49oaXHXzjpHGAowjKpd8efz5bJomF run

# rest of the swarm
for i in `seq 5001 5100`;
do
    echo "starting server $i"
    sleep 0.2
    screen -S testserver_$i -d -m storjnode --debug --bootstrap=127.0.0.1:5000 --port=$i run
done   

# send relay message
#screen -S testclient -d -m storjnode --debug --bootstrap=127.0.0.1:5100 --port=5501 relay_message ffce25851238332ec4f41d0ed57dcf7d6b125b66 testit
# to kill swarm `killall screen`
