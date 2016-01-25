#!/usr/bin/env bash
screen -S bs6000 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6000
screen -S bs6001 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6001
screen -S bs6002 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6002
screen -S bs6003 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6003
screen -S bs6004 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6004
screen -S bs6005 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6005
screen -S bs6006 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6006
screen -S bs6007 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6007
screen -S bs6008 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6008
screen -S bs6009 -d -m env/bin/python scripts/start_bootstrap_only_node.py --debug --port=6009
