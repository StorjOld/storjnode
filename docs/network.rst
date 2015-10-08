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


Connection protocol
###################

Let A and B be the two hosts, each in its own private network; NA and NB are the two NAT devices with globally reachable IP addresses EIPA and EIPB respectively; S is a public server with a well-known globally reachable IP address.

1. A and B each begin a UDP conversation with S; the NAT devices NA and NB create UDP translation states and assign temporary external port numbers EPA and EPB
2. S examines the UDP packets to get the source port used by NA and NB (the external NAT ports EPA and EPB)
3. S passes EIPA:EPA to B and EIPB:EPB to A
4. A sends a packet to EIPB:EPB.
5. NA examines A's packet and creates the following tuple in its translation table: {Source-IP-A, EPA, EIPB, EPB}
6. B sends a packet to EIPA:EPA
7. NB examines B's packet and creates the following tuple in its translation table: {Source-IP-B, EPB, EIPA, EPA}
8. Depending on the state of NA's translation table when B's first packet arrives (i.e. whether the tuple {Source-IP-A, EPA, EIPB, EPB} has been created by the time of arrival of B's first packet), B's first packet is dropped (no entry in translation table) or passed (entry in translation table has been made).
9. Depending on the state of NB's translation table when A's first packet arrives (i.e. whether the tuple {Source-IP-B, EPB, EIPA, EPA} has been created by the time of arrival of A's first packet), A's first packet is dropped (no entry in translation table) or passed (entry in translation table has been made).
10. At worst, the second packet from A reaches B; at worst the second packet from B reaches A. Holes have been "punched" in the NAT and both hosts can communicate.


