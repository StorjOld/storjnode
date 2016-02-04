#!/usr/bin/env bash

git pull origin develop
make install
screen -dmS bootstrapnode;
sleep 1
screen -S bootstrapnode -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=10000 &> bootstrapnode.log\n'
