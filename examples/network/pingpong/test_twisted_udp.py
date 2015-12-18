# proof twisted work well, is fast enough and doesnt drop packets!


from twisted.internet import protocol
from twisted.internet import reactor


class Protocol(protocol.DatagramProtocol):
    noisy = False

    def __init__(self, name):
        self.name = name

    def datagramReceived(self, datagram, address):
        i = int(datagram)
        j = i + 1
        print("{0} received packet {1}".format(self.name, i))
        print("{0} sending packet {1}".format(self.name, j))
        self.transport.write(str(i + 1), address)


alice = Protocol("alice")
bob = Protocol("bob")
reactor.listenUDP(4567, alice)
reactor.listenUDP(5678, bob)
alice.transport.write(str(0), ("127.0.0.1", 5678))
reactor.run()
