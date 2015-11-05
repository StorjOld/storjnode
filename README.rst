#########
storjnode
#########

|BuildLink|_ |CoverageLink|_ |BuildLink2|_ |CoverageLink2|_ |LicenseLink|_

.. |BuildLink| image:: https://img.shields.io/travis/Storj/storjnode/master.svg?label=Build-Master
.. _BuildLink: https://travis-ci.org/Storj/storjnode

.. |CoverageLink| image:: https://img.shields.io/coveralls/Storj/storjnode/master.svg?label=Coverage-Master
.. _CoverageLink: https://coveralls.io/r/Storj/storjnode

.. |BuildLink2| image:: https://img.shields.io/travis/Storj/storjnode/develop.svg?label=Build-Develop
.. _BuildLink2: https://travis-ci.org/Storj/storjnode

.. |CoverageLink2| image:: https://img.shields.io/coveralls/Storj/storjnode/develop.svg?label=Coverage-Develop
.. _CoverageLink2: https://coveralls.io/r/Storj/storjnode

.. |LicenseLink| image:: https://img.shields.io/badge/license-MIT-blue.svg
.. _LicenseLink: https://raw.githubusercontent.com/Storj/storjnode


Low level storj protocol reference implementation.


Setup
#####

Windows
=======

Download `latest windows release from github <https://github.com/Storj/storjnode/releases>`_.

Extract the zip file to the folder where you wish to have it installed.

::

    $ storjnode.exe version


Linux
=====

Install client

::

    $ sudo apt-get install python-pip python-dev
    $ sudo pip install storjnode
    $ storjnode version

Update client

::

    $ sudo pip install storjnode --upgrade
    $ storjnode version


OSX
===

Install client

::

    $ brew install python
    $ rehash
    $ pip install storjnode
    $ storjnode version

Update client

::

    $ pip install storjnode --upgrade
    $ storjnode version


Usage
#####

CLI reference node
==================

Using the CLI reference implementation.

::

    # Show help text.
    $ storjnode --help

    # Show version number.
    $ storjnode version

    # Put key value pair in DHT.
    $ storjnode put <KEY> <VALUE>

    # Retrieve value from DHT.
    $ storjnode get <KEY>

    # Send node a direct message
    $ storjnode direct_message <NODEID> <MESSAGE>

    # Send node a relay message
    $ storjnode relay_message <NODEID> <MESSAGE>

    # Run node and join network.
    $ storjnode run

    # Run node on non default port and join network.
    $ storjnode --port=<PORT> run

    # Run node with provided key, used for node id, auth and encryption
    $ storjnode --node_key=<BITCOIN WIF/HWIF> run

    # Show node id
    $ storjnode --node_key=<BITCOIN WIF/HWIF> showid

    # Show node type (Public with public ip or private behind a NAT)
    $ storjnode --node_key=<BITCOIN WIF/HWIF> showtype


Python
======

Normal usage
------------

Starting and using a node in python.

.. code:: python

    #!/usr/bin/env python
    # from examples/usage.py

    import time
    import storjnode
    from crochet import setup, TimeoutError
    setup()  # start twisted via crochet

    # start node (use bitcoin wif or hwif as node key)
    node_key = "KzygUeD8qXaKBFdJWMk9c6AVib89keoZFBNdFBsj73kYZfAc4n1j"
    node = storjnode.network.BlockingNode(node_key)

    print("Giving nodes some time to find peers.")
    time.sleep(30)

    try:
        # The blocking node interface is very simple and behaves like a dict.
        node["examplekey"] = "examplevalue"  # put key value pair into DHT
        retrieved = node["examplekey"]  # retrieve value by key from DHT
        print("{key} => {value}".format(key="examplekey", value=retrieved))

        # A node cannot know of the DHT size or all entries.
        try:
            node.items()
        except NotImplementedError as e:
            print(repr(e))

        # A node can only write to the DHT.
        try:
            del node["examplekey"]
        except NotImplementedError as e:
            print(repr(e))

    except TimeoutError:
        print("Got timeout error")

    finally:
        node.stop()


Multinode usage
---------------

Using more then one node in a python script.

If your are using more then one node in a single script, you must assign them
different ports.

.. code:: python

    #!/usr/bin/env python
    # from examples/multinode.py

    import time
    import storjnode
    from crochet import setup, TimeoutError
    setup()  # start twisted via crochet

    # create alice node (with bitcoin wif as node key)
    alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
    alice_node = storjnode.network.BlockingNode(alice_key)

    # create bob node (with bitcoin hwif as node key)
    bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
               "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
    bob_node = storjnode.network.BlockingNode(bob_key)

    print("Giving nodes some time to find peers.")
    time.sleep(30)

    try:
        # use nodes
        alice_node["examplekey"] = "examplevalue"  # alice inserts value
        stored_value = bob_node["examplekey"]  # bob retrievs value
        print("{key} => {value}".format(key="examplekey", value=stored_value))

    except TimeoutError:
        print("Got timeout error")

    finally:  # stop nodes
        alice_node.stop()
        bob_node.stop()


Node messaging
--------------

Nodes can send messages to each other. You can send direct messages or relay
messages from node to node.

**Direct messages**: 

The node spidercrawls the network to find the receiving node and sends the
message directly. This will fail if the receiving node is behind a NAT and
doesn't have a public ip.

.. code:: python

    #!/usr/bin/env python
    # from examples/direct_message.py

    import time
    import storjnode
    from crochet import setup, TimeoutError
    setup()  # start twisted via crochet

    # isolate nodes becaues this example fails behind a NAT

    # create alice node (with bitcoin wif as node key)
    alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
    alice_node = storjnode.network.BlockingNode(
        alice_key, bootstrap_nodes=[("240.0.0.0", 1337)]
    )

    # create bob node (with bitcoin hwif as node key)
    bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
               "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
    bob_node = storjnode.network.BlockingNode(
        bob_key, bootstrap_nodes=[("127.0.0.1", alice_node.port)]
    )

    time.sleep(5)

    try:
        # send direct message (blocking call)
        alice_node.send_direct_message(bob_node.get_id(), "hi bob")
        if bob_node.has_messages():
            print("bob received:", bob_node.get_messages())
        else:
            print("direct message failed")

    except TimeoutError:
        print("Got timeout error")

    finally:  # stop nodes
        alice_node.stop()
        bob_node.stop()


**Relay messages**:

Relay messages are sent to the node nearest the receiver in the routing table
that accepts the relay message. This continues until it reaches the destination
or the nearest node to the receiver is reached.

Because messages are always relayed only to reachable nodes in the current
routing table, there is a fare chance nodes behind a NAT can be reached if
it is connected to the network.

.. code:: python

    # from examples/messaging.py
    # from examples/relay_message.py

    import time
    import storjnode
    from crochet import setup, TimeoutError
    setup()  # start twisted via crochet

    # create alice node (with bitcoin wif as node key)
    alice_key = "Kyh4a6zF1TkBZW6gyzwe7XRVtJ18Y75C2bC2d9axeWZnoUdAVXYc"
    alice_node = storjnode.network.BlockingNode(
        alice_key#, bootstrap_nodes=[("240.0.0.0", 1337)]  # isolate
    )

    # create bob node (with bitcoin hwif as node key)
    bob_key = ("xprv9s21ZrQH143K3uzRG1qUPdYhVZG1TAxQ9bLTWZuFf1FHR5hiWuRf"
               "o2L2ZNoUX9BW17guAbMXqHjMJXBFvuTBD2WWvRT3zNbtVJ1S7yxUvWd")
    bob_node = storjnode.network.BlockingNode(
        bob_key#, bootstrap_nodes=[("127.0.0.1", alice_node.port)]  # isolate
    )

    print("Giving nodes some time to find peers.")
    time.sleep(60)

    try:
        # send relayed message (non blocking call)
        bob_node.send_relay_message(alice_node.get_id(), "hi alice")
        time.sleep(10)  # wait for it to be relayed
        if alice_node.has_messages():
            print("alice received:", alice_node.get_messages())
        else:
            print("relay message failed")

    except TimeoutError:
        print("Got timeout error")

    finally:  # stop nodes
        alice_node.stop()
        bob_node.stop()
