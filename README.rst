#########
storjnode
#########

|BuildLink|_ |TestLink|_ |CoverageLink|_ |BuildLink2|_ |TestLink2|_ |CoverageLink2|_ |LicenseLink|_

.. |BuildLink| image:: https://img.shields.io/appveyor/ci/Storj/storjnode/master.svg?label=Build-Master
.. _BuildLink: https://ci.appveyor.com/project/littleskunk/storjnode/branch/master

.. |TestLink| image:: https://img.shields.io/travis/Storj/storjnode/master.svg?label=Test-Master
.. _TestLink: https://travis-ci.org/Storj/storjnode

.. |CoverageLink| image:: https://img.shields.io/coveralls/Storj/storjnode/master.svg?label=Coverage-Master
.. _CoverageLink: https://coveralls.io/r/Storj/storjnode

.. |BuildLink2| image:: https://img.shields.io/appveyor/ci/Storj/storjnode/develop.svg?label=Build-Develop
.. _BuildLink2: https://ci.appveyor.com/project/littleskunk/storjnode/branch/develop

.. |TestLink2| image:: https://img.shields.io/travis/Storj/storjnode/develop.svg?label=Test-Develop
.. _TestLink2: https://travis-ci.org/Storj/storjnode

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

    $ sudo apt-get install python-dev gcc
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

Starting a farmer on the local machine.

The wallet is used for node authentication and payment if no cold storage
address is provided in the config.

If no wallet is given a temporary wallet will be generated, but only if
at least one cold storage address is provided in the config.

::

    $ storjnode --wallet=BITCOIN_WIF_OR_HWIF farm


Preventing loss of funds
------------------------

You must provide either a wallet via the arguments or at least one
cold storage address in the config! Not doing this will cause an error, to
prevent loosing funds.

Please back up your provided wallet and the cold storage keys to prevent
any loss of funds.


Configuration
#############

All configuration taken from the config file, stored in the following
locations by default.
If it does not exist a default config file will be
created with conservative settings.

::

    # default windows config path
    C:\Users\USERNAME\.storj\cfg.json

    # default linux config pathg
    /home/USERNAME/.storj/cfg.json

    # default mac config path
    /Users/USERNAME/.storj/cfg.json


A custom config can be given if your are running more then one client.

::

    $ storjnode --config=/path/to/custom/config.json farm


Using the API
#############

The storj protocol interface is be made available to other applications via a
`standard json-rpc service <http://www.jsonrpc.org/specification>`_.

The rpc interface matches the cli interface exactly.

::

    $ storjnode farm --port=8080 --hostname=localhost

For more information see https://github.com/F483/apigen


Using the API via the json-rpc service from python
==================================================

.. code:: python

    # pip install python-jsonrpc
    import pyjsonrpc
    client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    client.version()


Using the API via the json-rpc service from node.js
===================================================

.. code:: javascript

    // npm install node-json-rpc
    var rpc = require('node-json-rpc');
    
    var client = new rpc.Client({port: 8080, host: '127.0.0.1', path: '/'});
    
    client.call({
        "jsonrpc": "2.0",
        "method": "version",
        "params": { },
        "id": 0
      },
      function(err, res) {
        if (err) {
          console.log("Error add");
          console.log(err);
        } else {
          console.log("Success add");
          console.log(res); // {jsonrpc: '2.0', id: 0, result: "versionstr"}
        }
      }
    );


API call list
#############

Basic commands
==============


Get node information
--------------------

+---------------+-----------------------------------------------------------+
| Command       | info                                                      |
+---------------+-----------------------------------------------------------+
| Arguments     |                                                           |
+---------------+-----------------------------------------------------------+
| Returns       | json                                                      |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.info()
    # TODO add output


Start the farmer and optionally the json-rpc service.
-----------------------------------------------------

The call will not exit until a SIGINT signal is received, it is the only
call not exposed via the json-rpc service as it is used to start it.

+---------------+-----------------------------------------------------------+
| Command       | farm                                                      |
+---------------+-----------------------------------------------------------+
| Arguments     | - rpc=False (bool): Also start the json-rpc service.      |
|               | - hostname="localhost" (string): Service interface.       |
|               | - port=8080 (integer): Service port.                      |
+---------------+-----------------------------------------------------------+
| Returns       |                                                           |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.farm()


Config commands
===============

Get the current config.
-----------------------

+---------------+-----------------------------------------------------------+
| Command       | cfg_get_current                                           |
+---------------+-----------------------------------------------------------+
| Arguments     |                                                           |
+---------------+-----------------------------------------------------------+
| Returns       | json                                                      |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.cfg_get_current()
    # TODO add output


Get the default config.
-----------------------

+---------------+-----------------------------------------------------------+
| Command       | cfg_get_default                                           |
+---------------+-----------------------------------------------------------+
| Arguments     |                                                           |
+---------------+-----------------------------------------------------------+
| Returns       | json                                                      |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.cfg_get_default()
    # TODO add output


Get the jsonschema for config validation.
-----------------------------------------

+---------------+-----------------------------------------------------------+
| Command       | cfg_get_schema                                            |
+---------------+-----------------------------------------------------------+
| Arguments     |                                                           |
+---------------+-----------------------------------------------------------+
| Returns       | json                                                      |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.cfg_get_schema()
    # TODO add output


DHT commands
============

Insert a key/value pair into the DHT.
-------------------------------------

+---------------+-----------------------------------------------------------+
| Command       | dht_put                                                   |
+---------------+-----------------------------------------------------------+
| Arguments     | - key (json): TODO help text                              |
|               | - value (json): TODO help text                            |
+---------------+-----------------------------------------------------------+
| Returns       | bool                                                      |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.dht_put("key", {"foo": "bar"})
    True


Get value from the DHT for a given key.
---------------------------------------

+---------------+-----------------------------------------------------------+
| Command       | dht_get                                                   |
+---------------+-----------------------------------------------------------+
| Arguments     | - key (json): TODO help text                              |
+---------------+-----------------------------------------------------------+
| Returns       | json                                                      |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.dht_get("key")
    {"foo": "bar"}


Dump the contents of the nodes DHT storage.
-------------------------------------------

+---------------+-----------------------------------------------------------+
| Command       | dht_dump                                                  |
+---------------+-----------------------------------------------------------+
| Arguments     |                                                           |
+---------------+-----------------------------------------------------------+
| Returns       | json                                                      |
+---------------+-----------------------------------------------------------+
| Raises        |                                                           |
+---------------+-----------------------------------------------------------+

.. code:: python

    # pip install python-jsonrpc
    >>> import pyjsonrpc
    >>> client = pyjsonrpc.HttpClient(url="http://localhost:8080")
    >>> client.dht_dump()
    # TODO add output


