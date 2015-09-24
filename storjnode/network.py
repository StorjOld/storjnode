import random
import string
import logging
import irc.client
from threading import Thread


log = logging.getLogger(__name__)


def _generate_nick():
    # randomish to avoid collision, does not need to be strong randomness
    chars = string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(chars) for _ in range(12))


class NetworkException(Exception):
    pass


class ServerConnectionError(NetworkException):
    pass


class Network(object):

    def __init__(self, initial_relaynodes):
        self._server_list = initial_relaynodes[:]  # never modify original
        self._client = irc.client.Reactor()
        self._client_thread = None
        self._connection = None  # connection to storj irc network
        self._peer_connections = {}  # { 'address': (state, dcc_connection) }

    def get_current_relaynodes(self):
        server_list = self._server_list[:]  # make a copy
        # TODO order by something
        return server_list

    def start(self):
        log.info("Starting network module!")

        # try to connect to servers in a random order until successful
        # TODO weight according to capacity, ping time
        random.shuffle(self._server_list)
        for host, port in self._server_list:
            self._connect(host, port, _generate_nick())
            if self._connection is not None:
                break
        if self._connection is None:
            log.error("Couldn't connect to network!")
            raise ServerConnectionError()

        self._add_handlers()

        # start irc client process thread
        self._client_thread = Thread(target=self._client.process_forever)
        self._client_thread.start()
        log.info("Network module started!")

    def _connect(self, host, port, nick):
        try:
            logmsg = "Connecting to {host}:{port} as {nick}."
            log.info(logmsg.format(host=host, port=port, nick=nick))
            self._connection = self._client.server().connect(host, port, nick)
            log.info("Connection established!")
        except irc.client.ServerConnectionError:
            logmsg = "Connecting to {host}:{port} as {nick}."
            log.warning(logmsg.format(host=host, port=port, nick=nick))

    def connected(self):
        return (self._connection is not None and
                self._client_thread is not None)

    def restart(self):
        self.stop()
        self.start()

    def stop(self):
        log.info("Stopping network module!")
        # TODO close connection
        # TODO send client stop signal
        #self._client_thread.join()
        #self._client_thread = None
        #self._connection = None
        log.info("Network module stopped!")

    def _add_handlers(self):
        pass  # TODO add connection handlers

    def send_syn(self, msg):
        pass

    def on_syn(self, msg):
        pass

    def send_synack(self, msg):
        pass

    def on_synack(self, msg):
        pass

    def send_ack(self, msg):
        pass

    def on_ack(self, msg):
        pass

    def send_msg(self, msg):
        pass

    def on_msg(self, msg):
        pass

    def send_data(self, data):
        pass

    def on_data(self, data):
        pass
