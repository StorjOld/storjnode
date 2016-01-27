#!/usr/bin/env bash
git pull origin develop
make install
screen -S bs9000 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9000
screen -S bs9001 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9001
screen -S bs9002 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9002
screen -S bs9003 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9003
screen -S bs9004 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9004
screen -S bs9005 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9005
screen -S bs9006 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9006
screen -S bs9007 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9007
screen -S bs9008 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9008
screen -S bs9009 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=9009
