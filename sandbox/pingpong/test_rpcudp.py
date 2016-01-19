# proof rpcudp work well, is fast enough and doesnt drop packets!

import time
import signal
import storjnode
try:
    from Queue import Queue, Full  # py2
except ImportError:
    from queue import Queue, Full  # py3
import threading
from rpcudp.protocol import RPCProtocol
from twisted.internet import reactor
from crochet import setup


# start twisted via crochet and remove twisted handler
setup()
signal.signal(signal.SIGINT, signal.default_int_handler)


class Protocol(RPCProtocol):
    noisy = True

    def __init__(self, *args, **kwargs):
        self.queue = Queue(maxsize=10000)
        self.thread_stop = False
        self.thread = threading.Thread(target=self._thread_loop)
        self.thread.start()
        RPCProtocol.__init__(self, *args, **kwargs)

    def _thread_loop(self):
        while not self.thread_stop:
            time.sleep(0.002)  # dont hog cpu
            for entry in storjnode.util.empty_queue(self.queue):
                self.call(entry["sender"], entry["value"] + 1)

    def stop(self):
        self.thread_stop = True
        self.thread.join()

    def rpc_call(self, sender, value):
        try:
            print("Got {0} from {1}".format(value, sender))
            self.queue.put_nowait({"sender": sender, "value": value})
            return True
        except Full:
            print("Queue full, fuck!")
            return False


alice = Protocol()
bob = Protocol()
reactor.listenUDP(2345, alice)
reactor.listenUDP(3456, bob)


alice.call(('127.0.0.1', 3456), 0)  # initial packet

try:
    while True:
        time.sleep(0.1)  # run forever
except KeyboardInterrupt:
    pass
finally:
    alice.stop()
    bob.stop()
