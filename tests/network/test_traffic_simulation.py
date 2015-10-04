import time
import threading
import unittest
import btctxstore
from storjnode import network


INITIAL_RELAYNODES = [("127.0.0.1", 6667)]


class TestTraficSimulation(unittest.TestCase):

    def setUp(self):
        self.btctxstore = btctxstore.BtcTxStore()
        self.alice_wif = self.btctxstore.create_key()
        self.bob_wif = self.btctxstore.create_key()
        self.alice_address = self.btctxstore.get_address(self.alice_wif)
        self.bob_address = self.btctxstore.get_address(self.bob_wif)
        self.alice = network.Service(INITIAL_RELAYNODES, self.alice_wif)
        self.bob = network.Service(INITIAL_RELAYNODES, self.bob_wif)
        self.alice.connect()
        self.bob.connect()
        self.alice_thread = None
        self.alice_stop = False
        self.bob_thread = None
        self.bob_stop = False
        self.alice_received = 0
        self.bob_received = 0
        self.alice_sent = 0
        self.bob_sent = 0
        time.sleep(15)  # allow time to connect

    def tearDown(self):
        self.alice.disconnect()
        self.bob.disconnect()

    def _alice_loop(self):
        while not self.alice_stop:  # thread loop
            received = self.alice.received()  # empty input queue
            self.alice_received += len(received.get(self.bob_address, b""))
            self.alice.send(self.bob_address, b"data")
            self.alice_sent += 4
            time.sleep(0.2)

    def _bob_loop(self):
        while not self.bob_stop:  # thread loop
            received = self.bob.received()  # empty input queue
            self.bob_received += len(received.get(self.alice_address, b""))
            self.bob.send(self.alice_address, b"data")
            self.bob_sent += 4
            time.sleep(0.2)

    def _start_threads(self):
        self.alice_thread = threading.Thread(target=self._alice_loop)
        self.alice_thread.start()
        self.bob_thread = threading.Thread(target=self._bob_loop)
        self.bob_thread.start()

    def _stop_threads(self):
        self.alice_stop = True
        self.alice_thread.join()
        self.bob_stop = True
        self.bob_thread.join()

    def test_simulation(self):

        # other test is responsable for simultainous connect
        self.alice.send(self.bob_address, b"alice")
        time.sleep(15)

        self._start_threads()
        time.sleep(60)
        self._stop_threads()

        print("ALICE SENT:", self.alice_sent)
        print("ALICE RECEIVED:", self.alice_received)
        print("BOB SENT:", self.bob_sent)
        print("BOB RECEIVED:", self.bob_received)


if __name__ == "__main__":
    unittest.main()
