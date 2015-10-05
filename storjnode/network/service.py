import random
import time
import string
import btctxstore
import shlex
import subprocess
import logging
import irc.client
import base64
import threading
import datetime
from storjnode import deserialize
from storjnode.network import package
try:
    from Queue import Queue  # py2
except ImportError:
    from queue import Queue  # py3


_log = logging.getLogger(__name__)


AWAITING = "AWAITING"  # when a simultaneous connection attempt occured
CONNECTED = "CONNECTED"
CONNECTING = "CONNECTING"
DISCONNECTED = "DISCONNECTED"


class ConnectionError(Exception):
    pass


def _encode(data):
    return base64.b64encode(data).decode("ascii")


def _decode(base64_str):
    return base64.b64decode(base64_str.encode("ascii"))


def _generate_nick():
    # randomish to avoid collision, does not need to be strong randomness
    chars = string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(chars) for _ in range(12))


class Service(object):

    def __init__(self, relaynodes, wif, testnet=False, expiretime=30,
                 relaynode_update_interval=3600):
        """Create a network service instance with the given configuration.

        Arguments:
            relaynodes: Known relay nodes as `["ip-or-domain:port", ...]`
            wif: Bitcoin wif used as this nodes identity and to sign packages.
            testnet: If the bitcoin testnet is being used.
            expiretime: The time in seconds after which packages become stale.
        """
        self._btctxstore = btctxstore.BtcTxStore(testnet=testnet)

        # package settings
        self._expiretime = expiretime
        self._testnet = testnet
        self._wif = wif
        self._relaynode_update_interval = relaynode_update_interval

        # syn listen channel
        self._address = self._btctxstore.get_address(self._wif)
        self._relaynodes = relaynodes[:]  # never modify original
        self._channel = "#{address}".format(address=self._address)

        # reactor
        self._reactor = irc.client.Reactor()
        self._reactor_thread = None
        self._reactor_stop = True

        # sender
        self._sender_thread = None
        self._sender_stop = True

        # relaynode updater
        self._relaynode_update_thread = None
        self._relaynode_update_stop = True

        # relaynode updater
        self._timeout_thread = None
        self._timeout_stop = True

        # irc connection
        self._in_own_channel = False
        self._irc_connection = None
        self._irc_connection_mutex = threading.RLock()

        # peer connections
        self._dcc_connections = {}  # {
        #     address: {"state": str, "dcc": obj, "lastused": datetime}, ...
        # }
        self._dcc_connections_mutex = threading.RLock()

        # io queues
        self._received_queue = Queue()
        self._outgoing_queues = {}  # {address: Queue, ...}

    def connect(self):
        """Connects to the irc network via one of the initial relaynodes.

        Raises:
            storjnode.network.ConnectionError on failure to connect.
            storjnode.deserialize.InvalidRelayNodeURL
        """
        _log.info("Starting network service!")
        self._find_relay_node()
        self._add_handlers()
        self._start_threads()
        while not self.connected():  # block until connected
            time.sleep(0.1)
        _log.info("Network service started!")

    def _find_relay_node(self):
        # try to connect to servers in a random order until successful
        # TODO weight according to capacity, ping time
        random.shuffle(self._relaynodes)
        for relaynode_string in self._relaynodes:
            host, port = deserialize.relaynode(relaynode_string)
            self._connect_to_relaynode(host, port, _generate_nick())

            with self._irc_connection_mutex:
                if (self._irc_connection is not None and
                        self._irc_connection.is_connected()):  # successful
                    break
        with self._irc_connection_mutex:
            if not (self._irc_connection is not None and
                    self._irc_connection.is_connected()):
                _log.error("Couldn't connect to network!")
                raise ConnectionError()

    def _connect_to_relaynode(self, host, port, nick):
        with self._irc_connection_mutex:
            try:
                _log.info("Connecting to %s:%s as %s.", host, port, nick)
                server = self._reactor.server()
                self._irc_connection = server.connect(host, port, nick)
                _log.info("Connection established!")
            except irc.client.ServerConnectionError:
                _log.warning("Failed connecting to %s:%s as %s", host,
                             port, nick)

    def _add_handlers(self):
        with self._irc_connection_mutex:
            c = self._irc_connection
            c.add_global_handler("welcome", self._on_connect)
            c.add_global_handler("pubmsg", self._on_pubmsg)
            c.add_global_handler("ctcp", self._on_ctcp)
            c.add_global_handler("dccmsg", self._on_dccmsg)
            c.add_global_handler("disconnect", self._on_disconnect)
            c.add_global_handler("nicknameinuse", self._on_nicknameinuse)
            c.add_global_handler("dcc_disconnect", self._on_dcc_disconnect)
            c.add_global_handler("join", self._on_join)

    def _on_join(self, connection, event):
        if event.target == self._channel:
            self._in_own_channel = True
            _log.info("Joined own channel %s", self._channel)

    def _on_nicknameinuse(self, connection, event):
        connection.nick(_generate_nick())  # retry in case of miracle

    def _on_disconnect(self, connection, event):
        _log.info("Disconnected! %s", event.arguments[0])
        self._in_own_channel = False

    def _on_dcc_disconnect(self, connection, event):
        with self._dcc_connections_mutex:
            for node, props in self._dcc_connections.copy().items():
                if props["dcc"] == connection:
                    del self._dcc_connections[node]
                    _log.info("%s disconnected!", node)
                    return
        assert(False)  # NOQA

    def _on_dccmsg(self, connection, event):
        packagedata = event.arguments[0]
        parsed = package.parse(packagedata, self._expiretime, self._testnet)
        if parsed is not None and parsed["type"] == "ACK":
            self._on_ack(connection, event, parsed)
        elif parsed is not None and parsed["type"] == "DATA":
            _log.info("Received package from %s", parsed["node"])
            self._received_queue.put(parsed)
            with self._dcc_connections_mutex:
                now = datetime.datetime.now()
                self._dcc_connections[parsed["node"]]["lastused"] = now

    def _start_threads(self):

        # start reactor
        self._reactor_stop = False
        self._reactor_thread = threading.Thread(target=self._reactor_loop)
        self._reactor_thread.start()

        # start sender
        self._sender_stop = False
        self._sender_thread = threading.Thread(target=self._sender_loop)
        self._sender_thread.start()

        # start timeout
        self._timeout_stop = False
        self._timeout_thread = threading.Thread(target=self._timeout_loop)
        self._timeout_thread.start()

        # start relaynode updater
        self._relaynode_update_stop = False
        self._relaynode_update_thread = threading.Thread(
            target=self._relaynode_update_loop
        )
        self._relaynode_update_thread.start()

    def _send_bytes(self, dcc, data):
        try:
            dcc.send_bytes(data)
            return True
        except:
            return False

    def _send_data(self, node, dcc, data):
        _log.info("Sending %sbytes of data to %s", len(data), node)
        bytes_sent = 0
        for chunk in btctxstore.common.chunks(data, package.MAX_DATA_SIZE):
            packagedchunk = package.data(self._wif, chunk,
                                         testnet=self._testnet)
            if not self._send_bytes(dcc, packagedchunk):
                break
            bytes_sent += len(chunk)
        if bytes_sent > 0:
            with self._dcc_connections_mutex:
                now = datetime.datetime.now()
                self._dcc_connections[node]["lastused"] = now
        return bytes_sent

    def _clear_outgoing_queue(self, queue):
        data = b""
        while not queue.empty():
            data = data + queue.get()
        return data

    def _process_outgoing(self, node, queue):
        with self._dcc_connections_mutex:
            if self._node_state(node) in [CONNECTING, AWAITING]:
                pass  # wait until connected
            elif self._node_state(node) == DISCONNECTED:
                self._node_connect(node)
                # and wait until connected
            else:  # CONNECTED, process send queue
                dcc = self._dcc_connections[node]["dcc"]
                assert(dcc is not None)
                data = self._clear_outgoing_queue(queue)
                if len(data) > 0:
                    bytes_sent = self._send_data(node, dcc, data)
                    if bytes_sent != len(data):
                        # FIXME close connection and requeue data safely
                        raise Exception("Failed to send data!")

    def _sender_loop(self):
        while not self._sender_stop:  # thread loop
            if self.connected():
                for node, queue in self._outgoing_queues.items():
                    self._process_outgoing(node, queue)
            time.sleep(0.1)

    def _timeout_loop(self):
        while not self._timeout_stop:
            with self._dcc_connections_mutex:
                for node, status in self._dcc_connections.items():
                    if status["state"] == AWAITING:
                        pass  # TODO check timeout
                    elif status["state"] == CONNECTING:
                        pass  # TODO check timeout
                    elif status["state"] == CONNECTED:
                        pass  # TODO check timeout
            time.sleep(0.1)

    def _reactor_loop(self):
        # This loop should specifically *not* be mutex-locked.
        # Otherwise no other thread would ever be able to change
        # the shared state of a Reactor object running this function.
        while not self._reactor_stop:
            self._reactor.process_once(timeout=0.1)

    def connected(self):
        """Returns True if connected to the network."""
        # FIXME check if joined channel
        with self._irc_connection_mutex:
            return (self._irc_connection is not None and
                    self._irc_connection.is_connected() and
                    self._reactor_thread is not None and
                    self._in_own_channel)

    def reconnect(self):
        """Reconnect to the network.

        Raises:
            storjnode.network.ConnectionError on failure to connect.
        """
        self.disconnect()
        self.connect()

    def _stop_threads(self):
        if self._relaynode_update_thread is not None:
            self._relaynode_update_stop = True
            self._relaynode_update_thread.join()
            self._relaynode_update_thread = None

        if self._timeout_thread is not None:
            self._timeout_stop = True
            self._timeout_thread.join()
            self._timeout_thread = None

        if self._reactor_thread is not None:
            self._reactor_stop = True
            self._reactor_thread.join()
            self._reactor_thread = None

        if self._sender_thread is not None:
            self._sender_stop = True
            self._sender_thread.join()
            self._sender_thread = None

    def _close_connection(self):
        with self._irc_connection_mutex:
            if self._irc_connection is not None:
                self._irc_connection.close()
                self._irc_connection = None

    def disconnect(self):
        """Disconnect from the network."""
        _log.info("Stopping network service!")
        self._in_own_channel = False
        self._stop_threads()
        self._disconnect_nodes()
        self._close_connection()
        _log.info("Network service stopped!")

    def _on_connect(self, connection, event):
        # join own channel
        connection.join(self._channel)

    def _node_state(self, node):
        with self._dcc_connections_mutex:
            if node in self._dcc_connections:
                return self._dcc_connections[node]["state"]
            return DISCONNECTED

    def _disconnect_nodes(self):
        with self._dcc_connections_mutex:
            for node in self._dcc_connections.copy().keys():
                self._disconnect_node(node)
            assert(len(self._dcc_connections) == 0)

    def _disconnect_node(self, node):
        with self._dcc_connections_mutex:
            if node in self._dcc_connections:
                _log.info("Disconnecting node %s", node)
                dcc = self._dcc_connections[node]["dcc"]
                if dcc is not None:
                    dcc.disconnect()
                    # _on_dcc_disconnect handles entry deletion
                else:
                    del self._dcc_connections[node]

    def _node_connect(self, node):
        _log.info("Requesting connection to node %s", node)
        assert(self._node_state(node) == DISCONNECTED)

        # send connection request
        if not self._send_syn(node):
            return

        # update connection state
        with self._dcc_connections_mutex:
            self._dcc_connections[node] = {
                "state": CONNECTING,
                "dcc": None,
                "lastused": datetime.datetime.now()
            }

    def _send_syn(self, node):
        with self._irc_connection_mutex:
            if not self.connected():
                _log.warning("Cannot send syn, not connected!")
                return False

            node_channel = "#{address}".format(address=node)
            _log.info("Sending syn to node channel %s", node_channel)
            self._irc_connection.join(node_channel)
            syn = package.syn(self._wif, testnet=self._testnet)
            self._irc_connection.privmsg(node_channel, _encode(syn))
            self._irc_connection.part([node_channel])
            return True

    def _on_pubmsg(self, connection, event):

        # Ignore messages from other node channels.
        # We may be trying to send a syn in another channel along with others.
        if event.target != self._channel:
            return

        packagedata = _decode(event.arguments[0])
        parsed = package.parse(packagedata, self._expiretime, self._testnet)
        if parsed is not None and parsed["type"] == "SYN":
            self._on_syn(connection, event, parsed)

    def _on_simultaneous_connect(self, node):
        _log.info("Handeling simultaneous connection from %s", node)

        # first both sides abort and reset to nothing
        self._disconnect_node(node)

        # node whos address is first when sorted alphanumericly
        # is repsonsabe for restarting the connection
        if sorted([self._address, node])[0] == self._address:
            _log.info("Attemting to reconnect to %s", node)
            # _process_outgoing will reconnect automaticly when reset
        else:
            _log.info("Waiting for %s to reconnect", node)
            # prevent _process_outgoing from reconnecting automaticly
            with self._dcc_connections_mutex:
                self._dcc_connections[node] = {
                    "state": AWAITING,
                    "dcc": None,
                    "lastused": datetime.datetime.now()
                }

    def _on_syn(self, connection, event, syn):
        _log.info("Received syn from %s", syn["node"])

        # check for existing connection
        if self._node_state(syn["node"]) not in [DISCONNECTED, AWAITING]:
            self._on_simultaneous_connect(syn["node"])
            return

        # accept connection
        dcc = self._send_synack(connection, event, syn)

        # update connection state
        with self._dcc_connections_mutex:
            self._dcc_connections[syn["node"]] = {
                "state": CONNECTING,
                "dcc": dcc,
                "lastused": datetime.datetime.now()
            }

    def _send_synack(self, connection, event, syn):
        _log.info("Sending synack to %s", syn["node"])
        dcc = self._reactor.dcc("raw")
        dcc.listen()
        msg_parts = map(str, (
            'CHAT',
            _encode(package.synack(self._wif, testnet=self._testnet)),
            irc.client.ip_quad_to_numstr(dcc.localaddress),
            dcc.localport
        ))
        msg = subprocess.list2cmdline(msg_parts)
        connection.ctcp("DCC", event.source.nick, msg)
        return dcc

    def _on_ctcp(self, connection, event):

        # get data
        payload = event.arguments[1]
        parts = shlex.split(payload)
        command, synack_data, peer_address, peer_port = parts
        if command != "CHAT":
            return

        # get synack package
        synack = _decode(synack_data)
        parsed = package.parse(synack, self._expiretime, self._testnet)
        if parsed is None or parsed["type"] != "SYNACK":
            return
        self._on_synack(parsed, peer_address, peer_port)

    def _on_synack(self, parsed_synack, peer_address, peer_port):
        node = parsed_synack["node"]
        _log.info("Received synack from %s", node)

        # check for existing connection
        state = self._node_state(node)
        if state != CONNECTING:
            logmsg = "Invalid state for %s %s != %s"
            _log.warning(logmsg, node, state, CONNECTING)
            self._disconnect_node(node)
            return

        # setup dcc
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        dcc = self._reactor.dcc("raw")
        dcc.connect(peer_address, peer_port)

        # acknowledge connection
        _log.info("Sending ack to %s", node)
        ack = package.ack(self._wif, testnet=self._testnet)
        successful = self._send_bytes(dcc, ack)
        if not successful:
            _log.info("Failed to send ack to %s", node)
            # disconnect because anything else causes an invalid state
            self._disconnect_node(ack["node"])
            return

        with self._dcc_connections_mutex:
            self._dcc_connections[node] = {
                "state": CONNECTED,
                "dcc": dcc,
                "lastused": datetime.datetime.now()
            }

    def _on_ack(self, connection, event, ack):
        _log.info("Received ack from %s", ack["node"])

        # check current connection state
        if self._node_state(ack["node"]) != CONNECTING:
            _log.warning("Invalid state for %s", ack["node"])
            self._disconnect_node(ack["node"])
            return

        # update connection state
        with self._dcc_connections_mutex:
            now = datetime.datetime.now()
            self._dcc_connections[ack["node"]]["state"] = CONNECTED
            self._dcc_connections[ack["node"]]["lastused"] = now

    def send(self, node, data):
        """Send bytes to node.

        Arguments:
            node: The bitcoin address of the node to receive the data.
            data: The data to send to the node, must be instance of `bytes`.
        """
        assert(isinstance(data, bytes))
        assert(self._btctxstore.validate_address(node))
        queue = self._outgoing_queues.get(node)
        if queue is None:
            self._outgoing_queues[node] = queue = Queue()
        queue.put(data)
        _log.info("Queued %sbytes to send %s", len(data), node)

    def has_queued_output(self):
        """Returns True if data is queued to be sent to other nodes."""
        queues = self._outgoing_queues.values()
        for queue in queues:
            if not queue.empty():
                return True
        return False

    def has_received(self):
        """Returns True if data was received from nodes but not yet gotten."""
        return not self._received_queue.empty()

    def get_received(self):
        """Returns a dict with data received from nodes since the last call.

        Format: {
            "NODE_BITCOIN_ADDRESS": b"bytes recieved since last call",
            ...
        }
        """
        result = {}
        while not self._received_queue.empty():
            package = self._received_queue.get()
            node = package["node"]
            newdata = package["data"]
            prevdata = result.get(node, None)
            result[node] = newdata if prevdata is None else prevdata + newdata
        return result

    def nodes_connected(self):
        """Returns a list of nodes currently connected."""
        with self._dcc_connections_mutex:
            nodes = []
            for node, status in self._dcc_connections.items():
                if status["state"] == CONNECTED:
                    nodes.append(node)
            return nodes

    def _relaynode_update_loop(self):
        last_update = None
        delta = datetime.timedelta(seconds=self._relaynode_update_interval)
        while not self._relaynode_update_stop:
            now = datetime.datetime.now()
            if last_update is None or last_update + delta < now:
                # FIXME update list, see experiments/servermap.py
                last_update = now
            time.sleep(0.1)

    def get_relaynodes(self):
        """Returns list of current relay nodes.

        Format: ["ip-or-domain:port", ...]
        """
        relaynodes = self._relaynodes[:]  # make a copy
        # TODO order by something
        return relaynodes
