====================
storj protocol stack
====================


+---------------+--------+---------------+---------------+
| Dispatcher    |        |               |               |
+---------------+ Wallet | Contract DB   |               |
| Validation    |        |               | Configuration |
+---------------+--------+---------------+               |
| Serialization                          |               |
+----------------------------------------+               |
| Firewall                               |               |
+----------------------------------------+               |
| Throttle                               |               |
+----------------------------------------+               |
| Network                                |               |
+----------------------------------------+---------------+


Configuration
=============

Each layer will be supplied a configuration object where it obtains its
configuration values. This will allow intelligent high level clients to control
the low level protocol inner working.


Network
=======

This is the lowest layer in the Storj protocol stack. Initially IRC/DCC will
be used to bootstrap the network layer, but may be replaced at a later stage
if it proves insufficient.

Responsibilities:

 * Broadcasts (storage requests/offers)
 * Node messaging
 * Node discovery
 * Data transfer

Pros:

 * Well established (many libs, tools and well tested)
 * NAT traversal.

Cons:

 * Requires a network of voluntary servers.


Throttle
========

Restricts network IO to configured bandwidth limits.


Firewall
========

The firewall layer is responsible for security and makes sure everything is
properly encrypted and authenticated. Almost everything is encrypted in storj
anything that requires authentication but fails is immediately dropped.

 * Broadcasts: Unencrypted as they need to be public by design.
 * Node messaging: Asymmetrically encrypted so only the receiving party can decrypt.
 * Node discovery: Establishes an encrypted authenticated communication channel between nodes.
 * Data transfer: Asymmetrically or symmetrically encrypted so the storing node cannot view the data.

Additional filters such as black/white lists may be provided by high level clients.


Serialization
=============

Convert byte data into internal representation.


Validation
==========

Messages and data are validated according to the storj protocol specification.
Anything that is invalid is immediately dropped.


Dispatcher
==========

The dispatcher is responsible for handling incoming/outgoing messages/data and routing them to the appropriate modules.


Contract DB
===========

A key value storage of current contracts the node is involved with, required by validation module.


Wallet
======

A simple block chain interface required for contract validation.
