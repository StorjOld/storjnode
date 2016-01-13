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


Storj protocol reference implementation.


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


Usage
#####


Farming
=======

Start a farmer on the local machine.

The wallet is used for node authentication and payment if no cold storage
address is provided in the config.

If no wallet is given a temporary wallet will be generated, but only if
at least one cold storage address is provided in the config.

::

    $ storjnode --wallet=BITCOIN_WIF_OR_HWIF startserver


Preventing loss of funds
------------------------

You must provide either a wallet via the arguments or at least one
cold storage address in the config! Not doing this will cause an error to
prevent loosing funds.

Please back up your provided wallet and the cold storage keys to prevent
any loss of funds.


Using the json-rpc service
##########################

The storj protocol interface is be made available to other applications via a
[standard json-rpc service](http://www.jsonrpc.org/specification).

The rpc interface matches the cli interface exactly.

::

    $ storjnode startserver --port=8080 --hostname=localhost

For more information see https://github.com/F483/apigen


Accessing the json-rpc service from python
==========================================

::

    pip install python-jsonrpc


.. code:: python

    import pyjsonrpc
    rpc = pyjsonrpc.HttpClient(url="http://localhost:8080")
    rpc.version()

