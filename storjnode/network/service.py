import random
import string
import btctxstore
import shlex
import json
import subprocess
import logging
import irc.client
import base64
from threading import Thread
from storjnode.network import package
try:
    from Queue import Queue  # py2
except ImportError:
    from queue import Queue  # py3


log = logging.getLogger(__name__)


class NetworkException(Exception):
    pass


class ConnectionError(NetworkException):
    pass


CONNECTED = "CONNECTED"
CONNECTING = "CONNECTING"
DISCONNECTED = "DISCONNECTED"


def _encode_data(data):
    return base64.b64encode(data).decode("ascii")


def _decode_data(base64_str):
    return base64.b64decode(base64_str.encode("ascii"))


def _generate_nick():
    # randomish to avoid collision, does not need to be strong randomness
    chars = string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(chars) for _ in range(12))


class Service(object):

    def __init__(self, initial_relaynodes, wif, testnet=False):
        self._btctxstore = btctxstore.BtcTxStore(testnet=testnet)
        self._expiretime = 1337  # FIXME get from config
        self._testnet = testnet
        self._server_list = initial_relaynodes[:]  # never modify original
        self._wif = wif
        self._address = self._btctxstore.get_address(self._wif)
        self._channel = "#{address}".format(address=self._address)
        self._client_reactor = irc.client.Reactor()
        self._client_thread = None
        self._client_stop = True
        self._connection = None  # connection to storj irc network

        self._dcc_connections = {}  # {address: {"STATE": X}, ...}
        self._package_received_queue = Queue()

    ######################
    # NETWORK CONNECTION #
    ######################

    def connect(self):
        log.info("Starting network module!")
        self._find_relay_node()
        self._add_handlers()
        self._start_client()
        log.info("Network module started!")

    def _find_relay_node(self):
        # try to connect to servers in a random order until successful
        # TODO weight according to capacity, ping time
        random.shuffle(self._server_list)
        for host, port in self._server_list:
            self._connect_to_relaynode(host, port, _generate_nick())
            if self._connection is not None:
                break
        if self._connection is None:
            log.error("Couldn't connect to network!")
            raise ConnectionError()

    def _connect_to_relaynode(self, host, port, nick):
        try:
            logmsg = "Connecting to {host}:{port} as {nick}."
            log.info(logmsg.format(host=host, port=port, nick=nick))
            server = self._client_reactor.server()
            self._connection = server.connect(host, port, nick)
            log.info("Connection established!")
        except irc.client.ServerConnectionError:
            logmsg = "Failed to connect to {host}:{port} as {nick}."
            log.warning(logmsg.format(host=host, port=port, nick=nick))

    def _add_handlers(self):
        c = self._connection
        c.add_global_handler("welcome", self._on_connect)
        c.add_global_handler("pubmsg", self._on_pubmsg)
        c.add_global_handler("ctcp", self._on_ctcp)
        c.add_global_handler("dccmsg", self._on_dccmsg)
        c.add_global_handler("disconnect", self._on_disconnect)
        c.add_global_handler("nicknameinuse", self._on_nicknameinuse)
        c.add_global_handler("dcc_disconnect", self._on_dcc_disconnect)

    def _on_nicknameinuse(self, connection, event):
        connection.nick(_generate_nick())  # retry in case of miracle

    def _on_disconnect(self, connection, event):
        log.info("{0} disconnected! {1}".format(
            self.__class__.__name__, event.arguments[0]
        ))
        # FIXME what is the best thing to do here, just reconnect?
        #raise ConnectionError()

    def _on_dcc_disconnect(self, connection, event):
        log.info("{0} dcc disconnected! {1}".format(
            self.__class__.__name__, event.arguments[0]
        ))
        self.connection.quit()
        # FIXME remove from _dcc_connections
        #raise ConnectionError()

    def _on_dccmsg(self, connection, event):
        packagedata = _decode_data(event.arguments[0].decode("ascii"))
        parsed = package.parse(packagedata, self._expiretime, self._testnet)

        if parsed is not None and parsed["type"] == "ACK":
            self._on_ack(connection, event, parsed)
        elif parsed is not None:
            log.info("Received package from {0}".format(parsed["node"]))
            self._package_received_queue.put(parsed)

    def _start_client(self):
        self._client_stop = False
        self._client_thread = Thread(target=self._client_thread_loop)
        self._client_thread.start()

    def _client_thread_loop(self):
        # This loop should specifically *not* be mutex-locked.
        # Otherwise no other thread would ever be able to change
        # the shared state of a Reactor object running this function.
        while not self._client_stop:
            self._client_reactor.process_once(timeout=0.2)

    def connected(self):
        return (self._connection is not None and
                self._client_thread is not None)

    def reconnect(self):
        self.disconnect()
        self.connect()

    def disconnect(self):
        log.info("Stopping network module!")

        # stop client
        if self._client_thread is not None:
            self._client_stop = True
            self._client_thread.join()
            self._client_thread = None

        # close connection
        if self._connection is not None:
            self._connection.close()
            self._connection = None

        log.info("Network module stopped!")

    def _on_connect(self, connection, event):
        # join own channel
        # TODO only if config allows incoming connections
        log.info("Connecting to own channel {0}.".format(self._channel))
        connection.join(self._channel)

    ####################
    # NODE CONNECTIONS #
    ####################

    def node_connected(self, node_address):
        return self.node_connection_state(node_address) == CONNECTED

    def node_connection_state(self, node_address):
        if node_address in self._dcc_connections:
            return self._dcc_connections[node_address]["STATE"]
        return DISCONNECTED

    def node_dissconnect(self, node_address):
        if node_address in self._dcc_connections:
            dcc = self._dcc_connections[node_address]["dcc"]
            if dcc is not None:
                dcc.disconnect()
            del self._dcc_connections[node_address]

    ###########################
    # REQUEST NODE CONNECTION #
    ###########################

    def connect_to_node(self, node_address):
        log.info("Requesting connection to node {0}.".format(node_address))

        # check for existing connection
        if self.node_connection_state(node_address) != DISCONNECTED:
            log.warning("Existing connection to {0}.".format(node_address))
            return

        # send connection request
        self._send_syn(node_address)

        # update connection state
        self._dcc_connections[node_address] = {
            "STATE": CONNECTING,
            "dcc": None
        }

    def _send_syn(self, node_address):
        node_channel = "#{address}".format(address=node_address)

        log.info("Connetcion to node channel {0}".format(node_channel))
        self._connection.join(node_channel)  # node checks own channel for syns

        log.info("Sending syn to channel {0}".format(node_channel))
        syn = package.syn(self._wif, testnet=self._testnet)
        self._connection.privmsg(node_channel, _encode_data(syn))

        log.info("Disconneting from node channel {0}".format(node_channel))
        self._connection.part([node_channel])  # leave to reduce traffic

    ##########################
    # ACCEPT NODE CONNECTION #
    ##########################

    def _on_pubmsg(self, connection, event):

        # Ignore messages from other node channels.
        # We may be trying to send a syn in another channel along with others.
        if event.target != self._channel:
            return

        packagedata = _decode_data(event.arguments[0])
        parsed = package.parse(packagedata, self._expiretime,
                               self._testnet)
        if parsed is not None and parsed["type"] == "SYN":
            self._on_syn(connection, event, parsed)

    def _on_syn(self, connection, event, syn):
        log.info("Received syn from {node}".format(**syn))

        # check for existing connection
        if self.node_connection_state(syn["node"]) != DISCONNECTED:
            log.warning("Existing connection to {node}.".format(**syn))
            return

        # accept connection
        dcc = self._send_synack(connection, event, syn)

        # update connection state
        self._dcc_connections[syn["node"]] = {"STATE": CONNECTING, "dcc": dcc}

    def _send_synack(self, connection, event, syn):
        log.info("Sending synack to {node}.".format(**syn))
        dcc = self._client_reactor.dcc("raw")
        dcc.listen()
        msg_parts = map(str, (
            'CHAT',
            _encode_data(package.synack(self._wif, testnet=self._testnet)),
            irc.client.ip_quad_to_numstr(dcc.localaddress),
            dcc.localport
        ))
        msg = subprocess.list2cmdline(msg_parts)
        connection.ctcp("DCC", event.source.nick, msg)
        return dcc

    ############################################
    # ACKNOWLEDGE AND COMPLETE NODE CONNECTION #
    ############################################

    def _on_ctcp(self, connection, event):

        # get data
        payload = event.arguments[1]
        parts = shlex.split(payload)
        command, synack_data, peer_address, peer_port = parts
        if command != "CHAT":
            return
        
        # get synack package
        synack_data = _decode_data(synack_data)
        parsed = package.parse(synack_data, self._expiretime, self._testnet)
        if parsed is None or parsed["type"] != "SYNACK":
            return
        
        node = parsed["node"]
        log.info("Received synack from {0}".format(node))

        # check for existing connection
        if self.node_connection_state(node) != CONNECTING:
            log.warning("Invalid state for {0}.".format(node))
            self.node_dissconnect(node)
            return

        # setup dcc
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        dcc = self._client_reactor.dcc("raw")
        dcc.connect(peer_address, peer_port)

        # acknowledge connection
        log.info("Sending ack to {0}".format(node))
        dcc.privmsg(_encode_data(package.ack(self._wif, testnet=self._testnet)))

        # update connection state
        self._dcc_connections[node] = {"STATE": CONNECTED, "dcc": dcc}

    #####################################
    # COMPLETE ACCEPTED NODE CONNECTION #
    #####################################

    def _on_ack(self, connection, event, ack):
        log.info("Received ack from {0}".format(ack["node"]))

        # check current connection state
        if self.node_connection_state(ack["node"]) != CONNECTING:
            log.warning("Invalid state for {0}.".format(ack["node"]))
            self.node_dissconnect(ack["node"])
            return

        # update connection state
        self._dcc_connections[ack["node"]]["STATE"] = CONNECTED

    #############
    # MESSAGING #
    #############

    def send_message(self, node_address, msg_type, msg_data):
        log.info("Sending message to {0}".format(node_address))
        dcc = self._dcc_connections[node_address]["dcc"]
        dcc.privmsg(_encode_data(package.data(self._wif, msg_data, testnet=self._testnet)))

    def get_messages_received(self):
        messages = []
        while not self._package_received_queue.empty():
            messages.append(self._package_received_queue.get())
        return messages

    ##################
    # RELAY NODE MAP #
    ##################

    def get_current_relaynodes(self):
        server_list = self._server_list[:]  # make a copy
        # TODO order by something
        return server_list
