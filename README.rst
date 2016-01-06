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

    $ storjnode.exe --help


Linux (Ubuntu/Mint/Debian)
==========================

Install client

::

    $ sudo pip install storjnode
    $ storjnode --help


Update client

::

    $ sudo pip install storjnode --upgrade
    $ storjnode --help


OSX
===

Install client

::

    $ brew install python
    $ rehash
    $ pip install storjnode
    $ storjnode --help

Update client

::

    $ pip install storjnode --upgrade
    $ storjnode --help


Python usage examples
#####################

Normal usage
============

Starting and using a node in python.

.. code:: python

    #!/usr/bin/env python
    # from examples/usage.py
    import time
    import signal
    import storjnode
    from crochet import setup, TimeoutError

    # start twisted via crochet and remove twisted handler
    setup()
    signal.signal(signal.SIGINT, signal.default_int_handler)

    # start node (use bitcoin wif or hwif as node key)
    node_key = "KzygUeD8qXaKBFdJWMk9c6AVib89keoZFBNdFBsj73kYZfAc4n1j"
    node = storjnode.network.Node(node_key)

    try:
        print("Giving nodes some time to find peers.")
        time.sleep(storjnode.network.WALK_TIMEOUT)

        # The blocking node interface is very simple and behaves like a dict.
        node["examplekey"] = "examplevalue"  # put key value pair into DHT
        retrieved = node["examplekey"]  # retrieve value by key from DHT
        print("{key} => {value}".format(key="examplekey", value=retrieved))

    except TimeoutError:
        print("Got timeout error")

    except KeyboardInterrupt:
        pass

    finally:
        print("Stopping node")
        node.stop()


Multinode usage
===============

Using more then one node in a python script.

If your are using more then one node in a single script, you must assign them
different ports.

See examples/network/multinode.py


Node messaging
==============

Relay messages are sent to the node nearest the receiver in the routing table
that accepts the relay message. This continues until it reaches the destination
or the nearest node to the receiver is reached.

Because messages are always relayed only to reachable nodes in the current
routing table, there is a fare chance nodes behind a NAT can be reached if
it is connected to the network.

See examples/network/relay_message.py

Network mapping
===============

You can crawl the network to create a map of the network. Generating a graph
of the network is also possable (though not reccomended for networks with
many nodes).

See examples/network/map_network.py
