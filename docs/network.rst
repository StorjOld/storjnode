===================
Storj Network Layer
===================


Overview
========

Storj is built on UDP since it does not need the features of TCP. Node
messages fit in a single UDP package and the storj protocol is designed to be 
tolerant of dropped and out of order packages, flaky connections are expected.
Not needing the features of TCP will also increase performance.

Network layer responsibilities:

 - Broadcast messages (initially via IRC)
 - Node discovery (initially via IRC)
 - Establishing P2P connections (NAT traversal)
 - P2P data transfer
 - Authentication

Not responsible for higher level functions like:

 - Data interpretation (it only knows packages of bytes)
 - Data encryption

Not abstracted, to avoid the illusion of stable connections are:

 - Dropped packages
 - Out of order packages
 - Package size limitations


Public and Private Nodes
========================

Since NAT Traversal is required, we distinguish public and private nodes.

Public nodes have a public IP, run light weight STUN and IRC servers.
Private nodes are behind a NAT and use Public nodes to overcome this.

Initially we will support UDP hole punching to overcome NAT. Later automatic
port forwarding via PAT-PMP and UPnP will be added.


Exposed interface
#################

TODO link to generated interface documentation


Protocol
########

TODO exact protocol documentation once implemented

