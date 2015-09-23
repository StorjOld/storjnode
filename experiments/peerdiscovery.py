#! /usr/bin/env python

"""
Opjective
  One peer finds another and they establish a DCC connection.

Method
  Use channels to find peers as nicknames may be squatted.

Protocol:
 - SYN: Alice broadcasts a signed connection request message in bobs channel.
 - SYN-ACK: Bob opens a dcc connection and sends a signed response.
 - ACK: Alice sends a signed acknowledgment.
"""


import sys
import time
import shlex
import random
import subprocess
import string
import logging
import threading
import irc.client


LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
BOB_CHANNEL = "#19PqWiGFUivXb9ESCoZAowpoEkaodj5dFt"


# network setup
SERVER = "irc.quakenet.org"
PORT = 6667


# setup logger
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
logger = logging.getLogger("findpeer")


def generate_nick():
    chars = string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(chars) for _ in range(12))


class BaseClient(irc.client.SimpleIRCClient):

    def on_nicknameinuse(self, connection, event):
        connection.nick(generate_nick())  # retry in case of miracle

    def on_disconnect(self, connection, event):
        logger.info("{0} disconnected! {1}".format(
            self.__class__.__name__, event.arguments[0]
        ))
        sys.exit(-1)

    def on_welcome(self, connection, event):
        logger.info("{0} joining {1}".format(
            self.__class__.__name__, BOB_CHANNEL
        ))
        connection.join(BOB_CHANNEL)

    def on_dcc_disconnect(self, connection, event):
        logger.info("{0} dcc disconnected! {1}".format(
            self.__class__.__name__, event.arguments[0]
        ))
        self.connection.quit()
        sys.exit(-1)


class AliceClient(BaseClient):

    def on_join(self, connection, event):
        self.send_syn(connection, event)

    def send_syn(self, connection, event):
        logger.info("Alice sending syn")
        connection.privmsg(BOB_CHANNEL, "alicessyn")

    def send_ack(self, connection, event):
        logger.info("Alice sending ack")
        self.dcc.privmsg("alicesack")

    def on_ctcp(self, connection, event):
        payload = event.arguments[1]
        parts = shlex.split(payload)
        command, synack, peer_address, peer_port = parts
        if command != "CHAT" or synack != "bobssynack":
            return
        logger.info("Alice recieved bob syn-ack")

        # setup dcc
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        self.dcc = self.dcc_connect(peer_address, peer_port)

        self.send_ack(connection, event)


class BobClient(BaseClient):

    def on_dccmsg(self, connection, event):
        if event.arguments[0] != b"alicesack":
            return
        logger.info("Bob recieved alice ack")
        logger.info("Peers discovery successfull and dcc channel established!")
        sys.exit(0)

    def send_syn_ack(self, connection, event):
        logger.info("Bob sending syn-ack")
        self.dcc = self.dcc_listen()
        msg_parts = map(str, (
            'CHAT',
            "bobssynack",
            irc.client.ip_quad_to_numstr(self.dcc.localaddress),
            self.dcc.localport
        ))
        msg = subprocess.list2cmdline(msg_parts)
        connection.ctcp("DCC", event.source.nick, msg)

    def on_pubmsg(self, connection, event):
        if event.target != BOB_CHANNEL or event.arguments[0] != "alicessyn":
            return
        logger.info("Bob recieved alices syn")
        self.send_syn_ack(connection, event)


def start_client(client_class):
    client = client_class()
    try:
        nick = generate_nick()
        logmsg = "Starting client {0} with nick {1}"
        logger.info(logmsg.format(client_class.__name__, nick))
        client.connect(SERVER, PORT, nick)
    except irc.client.ServerConnectionError as x:
        logger.error("Failed to start client!")
        logger.error(repr(x))
        sys.exit(1)
    client.start()


def main():

    # start bob
    def bob_main():
        start_client(BobClient)
    bob_thread = threading.Thread(target=bob_main)
    bob_thread.start()

    time.sleep(2)

    # start alice
    def alice_main():
        start_client(AliceClient)
    alice_thread = threading.Thread(target=alice_main)
    alice_thread.start()


if __name__ == "__main__":
    main()
