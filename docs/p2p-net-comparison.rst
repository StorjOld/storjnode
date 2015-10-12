###################################
Comparison of P2P network protocols
###################################

Both the Ethereum P2P stack and Telehash aim to make a P2P application
communication frameworks and may be of great use to us no matter what we end
up doing. Both are in development and not yet usable.
It may be worth considering cooperating with one of them.

 - `Telehash <https://github.com/telehash/telehash.org/tree/master/v3>`_
 - `Ethereum P2P statck <https://github.com/ethereum/devp2p/blob/master/rlpx.md>`_

+-------------------------+---------------+---------------+--------------------+---------------+------------------+
|                         | Requirements  | bittorent     | Ethereum P2P stack | Telehash      | Bleep            |
+=========================+===============+===============+====================+===============+==================+
| End-to-end encryption   | Mandatory     | No            | Yes                | Yes           | Yes              |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+
| Node authentication     | Mandatory     | No            | Yes                | Yes           | Yes              |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+
| Perfect Forward Secrecy | Nice to have  | No            | Yes                | Yes           | Yes              |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+
| Distributed Hash Table  | Mandatory     | Yes           | No                 | No            | Yes              |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+
| Messaging               | Mandatory     | No            | Yes                | Yes           | Yes              |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+
| P2P data transfer       | TCP or LEDBAT | LEDBAT        | Non standard       | Non standard  | LEDBAT           |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+
| NAT Traversal           | Minimum UPnP  | UPnP, NAT-PMP | None               | UPnP planned  | Yes              |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+
| Language                |               | C++, PY       | PY2, C++, Go       | Node, C       | Closed source :( |
+-------------------------+---------------+---------------+--------------------+---------------+------------------+


Bittorrent
##########

A well established protocol with a large user base. The only but critical
shortcoming is that it does not support end to end encryption and
authentication.

Critical shortcomings:

 - No end-to-end encryption
 - No Authentication
 - No Messaging
 - Minimal NAT-traversal


Telehash
########

Telehash does seem to be the best match on the surface, but it looks like they
may have overextended themselves by trying to support a wide range of
languages and protocols. They have been developing for years and progress
seems to be slow. It does look like v3 will be useful sometime soon, but
maybe not soon enough for us. Only the Node and C implementations are
noteworthy but python may be added quickly via C bindings.

`Current status <https://github.com/telehash/telehash.org/tree/master/v3#implementations>`_

Critical shortcomings:

 - No DHT
 - No ready
 - Minimal NAT-traversal


Ethereum P2P Stack
##################

While the Ethereum P2P stack suffers from similar over engineering problems
they have made great technical decisions regarding the P2P network
implementation. They seem to be moving at a quicker pace but still not to fast.

 - No DHT
 - No ready
 - No NAT-traversal

`Current status <https://github.com/ethereum/devp2p/blob/master/rlpx.md#implementation-status>`_


Bleep
#####

Bleep is pretty much exactly what we want if all they clame to be true is.
Sadly they are not open source, so we cannot use them.

