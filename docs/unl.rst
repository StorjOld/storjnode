What is a UNL?

UNL, short for "Universal Node Locator" is a base64 encoded binary structure used to connect directly to other nodes with a standard TCP connection. Specifically, each UNL represent a node's networking configuration which includes:
* The WAN IP / Internet address
* The LAN IP
* Ports to connect to
* Whether or not those ports have been forwarded
* The type of NAT the router uses
* The node ID used in the kademlia DHT

This information makes it possible for other nodes to establish direct connections with a given node in a number of configurations:
1. Ports are open with UPnP - connect directly: if it fails go to 2.
2. Ports are open with NATPMP - connect directly: if it fails go to 3.
3. NAT is predictable - use TCP hole punching: if it fails go to 4.
4. Attempt to connect to the person making the connection instead: if it fails connection cannot be established.

The first 2 steps can result in the node being reachable directly but if they fail: step 3 allows nodes to punch holes through the NAT by using a technique called TCP hole punching. In practice: the technique is surprisingly reliable and works even through multiple NATs: but step 4 is where things get interesting. Because TCP connections are double-sided it means that either side of the connection can be used to establish it.

So imagine that you need to connect to a node behind a firewall or NAT: instead of making the connection yourself you can instruct them to connect back to you. If both sides of the connection are making the connect call this is easy enough to organise: both sides have each other's UNL details and the side that is reachable from the other side's perspective is who is connected to. But in cases where only one side is making the connection there needs to be some way to instruct the opposite side to connect back to us if its required. The solution so far is to use a DHT which is where node IDs come in.

Under a failure scenario, the node_id portion of the UNL allows messages to be routed to a given host but using a hop-based routing scheme. The messages are routed with UDP so things aren't 100% reliable, but perhaps reliable and low-cost enough where a reverse connect notification (and multiple small, redundant messages) can get through. In the future: there may be a simple TCP-based relay system but for now this is the architecture used for direct connect.

