#######
Network
#######

A lightweight, stateless and fault tolerant P2P networking protocol.

Everything we want? https://github.com/ethereum/devp2p/blob/master/rlpx.md#network-formation


Features
########


Lightweight
===========

The protocol is based on UDP, all network messages fit in a single small UDP
packet. Not needing the overhead TCP increases the overall performance.


Stateless
=========

All packages contain the all state information required. This vastly simplifies
protocol implementation and does not require clients to save any state
information.


Authentication
==============

Nodes use bitcoin public/private key pairs for authentication. The node id is
a bitcoin address and packages are signed.


Encryption
==========

TODO how best to encrypt everything?


NAT Aware
=========

Nodes know if they are ``public nodes`` with a public IP address, or
``private nodes`` behind a NAT. ``Public nodes`` help ``private nodes``
traverse NAT as best they can (this is not always possible).


Distributed hash table
======================

Uses a kademlia based DHT store network information.


Network formantion and node discovery
=====================================

Uses a kademlia based protocol organize the network.


Message relaying
================

Small messages can be relayed across the network from one node to another.


P2P data/file transfer
======================

Once nodes have established a P2P ``link`` then can transfer larger amounts of
data using uTorrent transport protocol.

Links:

 - `uTP <http://libtorrent.org/utp.html>`_
 - `BEP 29 <http://www.bittorrent.org/beps/bep_0029.html>`_
 - `LEDBAT rfc6817 <https://datatracker.ietf.org/doc/rfc6817/?include_text=1>`_


Broadcast channels
==================

TODO figure out how to do broadcast channels ...


Terminology
###########


Node
====

A client participating in the network.

Node ID
=======

A bitcoin address used to identify the node.


Signature
=========

A bitcoin signature used for authentication.


Network ID
==========

A eight byte identifier used to distinguish separate networks.


Address
=======

An ip and port tuple where a node is reachable.


Public Node
===========

A ``node`` that has a public ``address`` and can be reached directly.


Private Node
============

A ``node`` behind a NAT and that requires NAT traversal to be reached directly.


Link
====

Two ``nodes`` are linked when there is recent proof of bidirectional
communication between both nodes. Because UDP is connectionless the term
linked was chosen to avoid misunderstandings with TCP connections.


Relay Message
=============

A message relayed from node to node across the network until it finds its
destination or is dropped.


Protocol
########

Linking nodes
=============

Direct linking
--------------

Used to establish links to public nodes. It does not matter if the initiating
node is public or private since the required NAT entry is created by the
initial package.

This is similar to a TCP handshake but the terms have been changed to avoid
misunderstandings with TCP connections.


Alice establishes a link to public node Bob:

 * Alice sends Bob a ``Link Request package``.
 * Bob sends Alice a ``Link Request Confirm package``.
 * Alice has proof of bidirectional communication and recognizes the link.
 * Alice sends Bob an ``Link Confirm package``.
 * Bob has proof of bidirectional communication and recognizes the link.
 * Link is established for both nodes.


Assisted linking
----------------

Used to overcome NAT establish links to private nodes.

Bob establishes a link to private node Alice with assistance of the network.

 * If Bob is a private node he sends a ``Punch package`` to Alice's address.
 * Alice can now send packages to Bob because the required NAT entry exists.
 * Bob sends a ``Relayed Link Request package`` to Alice via network relay.
 * Alice receives the ``Relayed Link Request package``.
 * All requirements are now met so that direct linking can be done.
 * The Direct linking protocol is now followed (initiated by Alice).


Ping Pong
=========

TODO describe


Relay node discovery
====================

TODO describe


Walk node discovery
===================

TODO describe


Relay message
=============

TODO describe


Data transfer
=============

TODO describe


Distributed hash table
======================

https://en.wikipedia.org/wiki/Kademlia
https://github.com/bmuller/kademlia


Packet types
############

Packets containing application data should avoid creating packets larger then
512-byte.


Punch
=====

A packet containing noise, used by private nodes for NAT traversal.


Link Request (SYN)
==================

 -   1-byte Protocol version
 -   8-byte Network ID
 -   2-byte Packet Type
 -   8-byte Unix time stamp (No year 2038 problem)
 -  21-byte Sender Node ID
 -  21-byte Receiver Node ID
 -  65-byte Signature

Total: 126 bytes


Link Request Confirm (SYNACK)
=============================

 -   1-byte Protocol version
 -   8-byte Network ID
 -   2-byte Packet Type
 -   8-byte Unix time stamp (No year 2038 problem)
 - 126-byte Source ``Link Request`` Package
 -  16-byte Source IP (IPv6 supported)
 -   2-byte Source Port
 -  65-byte Signature

Total: 228 bytes


Link Confirm (ACK)
==================

 -   1-byte Protocol version
 -   8-byte Network ID
 -   2-byte Packet Type
 -   8-byte Unix time stamp (No year 2038 problem)
 - 228-byte Source ``Link Request Confirm`` Package
 -  16-byte Source IP (IPv6 supported)
 -   2-byte Source Port
 -  65-byte Signature

Total: 318 bytes


Relayed Link Request
====================

 -   1-byte Protocol version
 -   8-byte Network ID
 -   2-byte Packet Type
 -   8-byte Unix time stamp (No year 2038 problem)
 -  21-byte Sender Node ID
 -  21-byte Receiver Node ID
 -  16-byte Sender IP (IPv6 supported)
 -   2-byte Sender Port
 -  65-byte Signature

Total: 144 bytes


Relay Message
=============

 -   1-byte Protocol version
 -   8-byte Network ID
 -   2-byte Packet Type
 -   8-byte Unix time stamp (No year 2038 problem)
 -  21-byte Sender Node ID
 -  21-byte Receiver Node ID
 - 386-byte Max Message data
 -  65-byte Signature

Total: 126 - 512 bytes
