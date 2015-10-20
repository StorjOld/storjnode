from kademlia.protocol import KademliaProtocol


class StorjProtocol(KademliaProtocol):

    def rpc_message(self, sender, message):
        print("RECEIVED MESSAGE:", message)
        # FIXME add to received queue
        return (sender[0], sender[1])  # return (ip, port)

    def callMessage(self, nodeToAsk, message):
        address = (nodeToAsk.ip, nodeToAsk.port)
        d = self.message(address, self.sourceNode.id, message)
        return d.addCallback(self.handleCallResponse, nodeToAsk)
