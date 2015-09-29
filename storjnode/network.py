import random
import string
import shlex
import json
import subprocess
import logging
import irc.client
import base64
from threading import Thread


log = logging.getLogger(__name__)


CONNECTED = "CONNECTED"
CONNECTING = "CONNECTING"
DISCONNECTED = "DISCONNECTED"


def generate_nick():
    # randomish to avoid collision, does not need to be strong randomness
    chars = string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(chars) for _ in range(12))


def _encode_message(message):
    json_str = json.dumps(message)
    json_data = json_str.encode("ascii")
    base64_data = base64.b64encode(json_data)
    base64_str = base64_data.decode("ascii")
    return base64_str


def _decode_message(base64_str):
    base64_data = base64_str.encode("ascii")
    json_data = base64.b64decode(base64_data)
    json_str = json_data.decode("ascii")
    message = json.loads(json_str)
    return message


def _make_message(sender_address, message_type, message_data):
    return _encode_message({
        "type": message_type,
        "node": sender_address,
        "date": "TODO",  # TODO add date
        "data": message_data,
        "sig": "TODO"  # TODO add sig of "{type} {node} {date} {data}"
    })


def _parse_message(encoded_message):
    try:
        message = _decode_message(encoded_message)
        assert("type" in message)
        assert("node" in message)
        assert("date" in message)
        assert("data" in message)
        assert("sig" in message)
        # TODO validate date
        # TODO validate sig
        return message
    except Exception as e:
        log.warning("Error reading message! {0}".format(repr(e)))
        return None


def _make_syn(sender_address):
    return _make_message(sender_address, "syn", "")


def _parse_syn(encoded_message):
    message = _parse_message(encoded_message)
    return message if message["type"] == "syn" else None


def _make_synack(sender_address):
    return _make_message(sender_address, "synack", "")


def _parse_synack(encoded_message):
    message = _parse_message(encoded_message)
    return message if message["type"] == "synack" else None


def _make_ack(sender_address):
    return _make_message(sender_address, "ack", "")


class NetworkException(Exception):
    pass


class ConnectionError(NetworkException):
    pass


class Network(object):

    def __init__(self, initial_relaynodes, node_address):
        self._server_list = initial_relaynodes[:]  # never modify original
        self._address = node_address
        self._channel = "#{address}".format(address=self._address)
        self._client_reactor = irc.client.Reactor()
        self._client_thread = None
        self._client_stop = True
        self._connection = None  # connection to storj irc network

        # FIXME mutex all _dcc_connections access
        # FIXME isolate by moving to NodeConnectionsManager
        self._dcc_connections = {}  # {address: {"STATE": X}, ...}

        self._message_handlers = []
        self._data_handlers = []

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
            self._connect_to_relaynode(host, port, generate_nick())
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
        connection.nick(generate_nick())  # retry in case of miracle

    def _on_disconnect(self, connection, event):
        log.info("{0} disconnected! {1}".format(
            self.__class__.__name__, event.arguments[0]
        ))
        #raise ConnectionError()

    def _on_dcc_disconnect(self, connection, event):
        log.info("{0} dcc disconnected! {1}".format(
            self.__class__.__name__, event.arguments[0]
        ))
        self.connection.quit()
        #raise ConnectionError()

    def _on_dccmsg(self, connection, event):
        message = _parse_message(event.arguments[0].decode("ascii"))
        if message is not None and message["type"] == "ack":
            self._on_ack(connection, event, message)
        if message is not None:
            self._on_message(connection, event, message)

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
        self._connection.privmsg(node_channel, _make_syn(self._address))

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

        syn = _parse_syn(event.arguments[0])
        if syn is not None:
            self._on_syn(connection, event, syn)

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
            _make_synack(self._address),
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
        synack = _parse_synack(synack_data)
        if command != "CHAT" or synack is None:
            return
        node_address = synack["node"]
        log.info("Received synack from {0}".format(node_address))

        # check for existing connection
        if self.node_connection_state(node_address) != CONNECTING:
            log.warning("Invalid state for {0}.".format(node_address))
            self.node_dissconnect(node_address)
            return

        # setup dcc
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        dcc = self._client_reactor.dcc("raw")
        dcc.connect(peer_address, peer_port)

        # acknowledge connection
        log.info("Sending ack to {node}".format(**synack))
        dcc.privmsg(_make_ack(self._address))

        # update connection state
        self._dcc_connections[node_address] = {"STATE": CONNECTED, "dcc": dcc}

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

    def add_message_handler(self, handler):
        if handler not in self._message_handlers:
            self._message_handlers.append(handler)

    def remove_message_handler(self, handler):
        if handler in self._message_handlers:
            self._message_handlers.remove(handler)

    def send_message(self, node_address, msg_type, msg_data):
        log.info("Sending message to {0}".format(node_address))
        dcc = self._dcc_connections[node_address]["dcc"]
        dcc.privmsg(_make_message(self._address, msg_type, msg_data))

    def _on_message(self, connection, event, message):
        log.info("Received message from {0}".format(message["node"]))
        for handler in self._message_handlers:
            handler(message)

    ########
    # DATA #
    ########

    def add_data_handler(self, handler):
        if handler not in self._data_handlers:
            self._data_handlers.append(handler)

    def remove_data_handler(self, handler):
        if handler in self._data_handlers:
            self._data_handlers.remove(handler)

    def send_data(self, node_address, fobj):
        log.info("Sending data to {0}".format(node_address))
        dcc = self._dcc_connections[node_address]["dcc"]
        dcc.privmsg(_make_data(self._address, msg_type, msg_data))

    def _on_data(self, connection, event, data):
        log.info("Received data from {0}".format(data["node"]))
        for handler in self._data_handlers:
            handler(data)

    ##################
    # RELAY NODE MAP #
    ##################

    def get_current_relaynodes(self):
        server_list = self._server_list[:]  # make a copy
        # TODO order by something
        return server_list
