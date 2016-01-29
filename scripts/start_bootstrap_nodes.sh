#!/usr/bin/env bash

git pull origin develop
make install

screen -dmS bs9000;
screen -dmS bs9001;
screen -dmS bs9002;
screen -dmS bs9003;
screen -dmS bs9004;
screen -dmS bs9005;
screen -dmS bs9006;
screen -dmS bs9007;
screen -dmS bs9008;
screen -dmS bs9009;

sleep 1

screen -S bs9000 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9000 &> bs9000.log\n'
screen -S bs9001 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9001 &> bs9001.log\n'
screen -S bs9002 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9002 &> bs9002.log\n'
screen -S bs9003 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9003 &> bs9003.log\n'
screen -S bs9004 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9004 &> bs9004.log\n'
screen -S bs9005 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9005 &> bs9005.log\n'
screen -S bs9006 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9006 &> bs9006.log\n'
screen -S bs9007 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9007 &> bs9007.log\n'
screen -S bs9008 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9008 &> bs9008.log\n'
screen -S bs9009 -X stuff $'env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9009 &> bs9009.log\n'
