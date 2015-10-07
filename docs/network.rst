===================
Storj Network Layer
===================

Network layer responsibilities:

 - Broadcast messages (initially via IRC)
 - Node descovery (initially via IRC)
 - Establishing P2P connections (NAT traversal)
 - P2P data transfer


Interface
#########

TODO


NAT Traversal
#############

Because everyone is not using IPv6 we have to deal with NAT and there is no
prefect solution to establishing a P2P network with nodes behind NAT. This is
why many P2P clients such as bitcoin do not do this.

It has to do with there being no standard for NAT and also the centralization
of the internet services pushing P2P out of intrest for NAT providers.

In some cases like stacked NAT devices where one is symmetric it is impossable
to overcome and get a P2P connection.


NAT Traversal options
=====================

The following practical NAT traversal options exist for P2P applications.


Classic UDP hole punching
-------------------------

Use STUN to get a transport address (ip & port), then use that to establish a
UDP connection.

This requires a STUN server with a public ip, but they are lightweight and 
can easily be part of the client.

Drawbacks:

 - Doesn't work with Symmetric NAT devices.

Links:

 - `Wiki/STUN <https://en.wikipedia.org/wiki/STUN>`_
 - `Wiki/UDP_hole_punching <https://en.wikipedia.org/wiki/UDP_hole_punching>`_
 - `Proof of Concept <https://gist.github.com/koenbollen/464613>`_


Automatic port forwarding
-------------------------

Protocols exist to find NAT devices and have them automaticly forward ports.

Drawbacks: 

 - It is not universaly deployed.
 - Only works if there is a single NAT layer (IPv4 depletion is now
   causing ISPs to NAT internaly and this will only get worse).
 - These protocols have had a bad security track record.

Links:

 - `Wiki/NAT-PMP <https://en.wikipedia.org/wiki/NAT_Port_Mapping_Protocol>`_
 - `Wiki/UPnP <https://en.wikipedia.org/wiki/Universal_Plug_and_Play>`_


Manually port forwarding
------------------------

Most NAT device support manual port forwarding.

Drawbacks: 

 - Obviously this requires the end user to configure the NAT device.
 - Only works if there is a single NAT layer (IPv4 depletion is now
   causing ISPs to NAT internaly and this will only get worse).




Storj NAT Traversal stragegy
============================


UDP Connections
---------------

First we initially use UDP since we do not need the features of tcp. 
Node messages, should fit in a single UDP package and for file transfer it 
doesn't matter if the packets arrive out of order. It is also not important 
if some packets are dropped as storj will be able to deal with flaky
connections anyway.


Public and Private Nodes
------------------------

We distinguish between Public nodes and private nodes.

 - Public nodes have a public ip and run light weight STUN and IRC servers.
 - Private nodes are behind a NAT and use Public nodes to overcome this.

Initially we will only support UDP hole punching to overcome NAT, this is
relativly easy to implement and doesnt expose users to the security risks of
automatic port forwarding. Later we can add support for automatic port 
forwarding.

This pretty much falls in line with what most modern P2P application do.
