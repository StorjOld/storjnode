#########
storjnode
#########

|BuildLink|_ |CoverageLink|_ |LicenseLink|_ 


.. |BuildLink| image:: https://travis-ci.org/Storj/storjnode.svg?branch=master
.. _BuildLink: https://travis-ci.org/Storj/storjnode

.. |CoverageLink| image:: https://coveralls.io/repos/Storj/storjnode/badge.svg
.. _CoverageLink: https://coveralls.io/r/Storj/storjnode

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

    # Run node and join network.
    $ storjnode run

    # Run node on non default port and join network.
    $ storjnode --port=1337 run


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
    import btctxstore

    # start node
    node_key = btctxstore.BtcTxStore().create_key()  # btc wif or hwif
    node = storjnode.network.BlockingNode(node_key)  # using default port 4653
    time.sleep(12)  # Giving node some time to find peers

    # The blocking node interface is very simple and behaves like a dict.
    node["examplekey"] = "examplevalue"  # put key value pair into DHT
    retrieved = node["examplekey"]  # retrieve value by key from DHT
    print("{key} => {value}".format(key="examplekey", value=retrieved))

    # A node does not know of its size or all entries.
    try:
        node.items()
    except NotImplementedError as e:
        print(e)

    # A node can only write to the DHT.
    try:
        del node["examplekey"]
    except NotImplementedError as e:
        print(e)

    # stop twisted reactor to disconnect from network
    node.stop_reactor()

Multinode usage
---------------

Using more then one node in a python script.

If your are using more then one node in a single script, you must assign them
different ports and manage the twisted reactor yourself.

.. code:: python

    #!/usr/bin/env python
    # from examples/multinode_usage.py

    import time
    import threading
    import storjnode
    import btctxstore
    from twisted.internet import reactor

    # create alice node
    alice_wallet = btctxstore.BtcTxStore().create_wallet()  # hwif
    alice_node = storjnode.network.BlockingNode(alice_wallet, port=4653,
                                                start_reactor=False)

    # create bob node
    bob_key = btctxstore.BtcTxStore().create_wallet()  # wif
    bob_node = storjnode.network.BlockingNode(bob_key, port=4654,
                                              start_reactor=False)

    # start twisted reactor yourself
    reactor_thread = threading.Thread(target=reactor.run,
                                      kwargs={"installSignalHandlers": False})
    reactor_thread.start()
    time.sleep(12)  # Giving node some time to find peers

    # use nodes
    alice_node["examplekey"] = "examplevalue"  # alice inserts value
    stored_value = bob_node["examplekey"]  # bob retrievs value
    print("{key} => {value}".format(key="examplekey", value=stored_value))

    # stop twisted reactor
    reactor.stop()
    reactor_thread.join()
