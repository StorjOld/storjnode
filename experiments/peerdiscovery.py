#! /usr/bin/env python

"""
Opjective
  One peer finds another and they establish a DCC connection.

Method
  Use deterministic channels to find peers as nicknames may be squatted and
  thus prevent immidiate opening of a dcc connection.

Protocol:
 - SYN: Alice broadcasts a signed connection request message in bobs channel.
 - SYN-ACK: Bob opens a dcc connection and sends a signed response.
 - ACK: Alice sends a signed acknowledgment.
"""


import sys
import json
import time
import random
import string
import logging
import threading
import irc.client
from btctxstore import BtcTxStore


LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
btctxstore = BtcTxStore()


# network setup
SERVER = "irc.quakenet.org"
PORT = 6667


# setup logger
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
logger = logging.getLogger("findpeer")


# setup peer alice
# ALICE_WIF = btctxstore.create_key()
ALICE_WIF = "L44yDewfmYTX3cY8SBBCirFmDgSThCyf1JWEUKXWQBJqaEfTVti8"
ALICE_ADDRESS = btctxstore.get_address(ALICE_WIF)
logger.info("ALICE_WIF: " + ALICE_WIF)
logger.info("ALICE_ADDRESS: " + ALICE_ADDRESS)


# setup peer bob
# BOB_WIF = btctxstore.create_key()
BOB_WIF = "L3bQTLbxMuAJ9fH2uWNwLoByBeSQUcHLgqrUv8aiz8TvP2SV89Um"
BOB_ADDRESS = btctxstore.get_address(BOB_WIF)
BOB_CHANNEL = "#{0}".format(BOB_ADDRESS)
logger.info("BOB_WIF: " + BOB_WIF)
logger.info("BOB_ADDRESS: " + BOB_ADDRESS)


def generate_nick():
    chars = string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(chars) for _ in range(12))


class BaseClient(irc.client.SimpleIRCClient):

    def on_nicknameinuse(self, connection, event):
        connection.nick(generate_nick())  # retry in case of miracle

    def on_disconnect(self, connection, event):
        logger.info("Disconnected {0}".format(repr(event)))
        sys.exit(0)

    def on_welcome(self, connection, event):
        logger.info("Join {0}".format(BOB_CHANNEL))
        connection.join(BOB_CHANNEL)

    def on_dcc_disconnect(self, connection, event):
        self.connection.quit()


class AliceClient(BaseClient):

    def send_syn(self, connection, event):
        logmsg = "SYN: Alice sending connection request to {0}."
        logger.info(logmsg.format(BOB_CHANNEL))
        connection.privmsg(BOB_CHANNEL, json.dumps({
            "type": "connection_request",
            "address": ALICE_ADDRESS
        }))

    def on_join(self, connection, event):
        self.send_syn(connection, event)


class BobClient(BaseClient):

    def check_syn(self, connection, event):
        try:
            if event.target != BOB_CHANNEL:
                return None
            message = json.loads(event.arguments[0])
            if message["type"] == "connection_request":
                return {
                    "nick": event.source.split("!")[0],
                    "address": message["address"]
                }
        except Exception as e:
            logger.warning("Couldn't parse message data! {0}".format(repr(e)))
        return None

    def send_syn_ack(self, connection, event, source):
        logmsg = "SYN-ACK: Bob sending connection response to {0}."
        logger.info(logmsg.format(repr(source)))

    def on_pubmsg(self, connection, event):
        source = self.check_syn(connection, event)
        if source is not None:
            self.send_syn_ack(connection, event, source)

#    def on_dccmsg(self, connection, event):
#        data = event.arguments[0]
#        text = data.decode('utf-8')
#        connection.privmsg("You said: " + text)


def alice_main():
    alice_client = AliceClient()
    try:
        logger.info("Starting alice client")
        alice_client.connect(SERVER, PORT, generate_nick())
    except irc.client.ServerConnectionError as x:
        logger.error("Failed to start alice client!")
        logger.error(repr(x))
        sys.exit(1)
    alice_client.start()


def bob_main():
    bob_client = BobClient()
    try:
        logger.info("Starting bob client")
        bob_client.connect(SERVER, PORT, generate_nick())
    except irc.client.ServerConnectionError as x:
        logger.error("Failed to start bob client!")
        logger.error(repr(x))
        sys.exit(1)
    bob_client.start()


def main():
    bob_thread = threading.Thread(target=bob_main)
    bob_thread.start()
    time.sleep(1)
    alice_thread = threading.Thread(target=alice_main)
    alice_thread.start()


if __name__ == "__main__":
    main()
