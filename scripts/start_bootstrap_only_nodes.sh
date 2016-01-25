#!/usr/bin/env bash
screen -S bs5000 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5000
screen -S bs5001 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5001
screen -S bs5002 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5002
screen -S bs5003 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5003
screen -S bs5004 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5004
screen -S bs5005 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5005
screen -S bs5006 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5006
screen -S bs5007 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=5007
