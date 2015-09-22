#! /usr/bin/env python

# Opjective: transfer a file via DCC


import shutil
import hashlib
import time
import threading
import random
import string
import logging
import tempfile
import os
import struct
import sys
import subprocess
import shlex
import irc.client


VALID_NICK_CHARS = string.ascii_lowercase + string.ascii_uppercase
SERVER = "irc.quakenet.org"
PORT = 6667
SENDER_NICK = ''.join(random.choice(VALID_NICK_CHARS) for _ in range(12))
RECEIVER_NICK = ''.join(random.choice(VALID_NICK_CHARS) for _ in range(12))
IN_FILEPATH = tempfile.mktemp()
IN_FILENAME = os.path.split(IN_FILEPATH)[1]
OUT_DIR = tempfile.mkdtemp()
OUT_FILEPATH = os.path.join(OUT_DIR, IN_FILENAME)
LOG_FORMAT = "%(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
logger = logging.getLogger("dcctransfer")


def cleanup():
    with open(IN_FILEPATH, 'rb') as f:
        input_sha256 = hashlib.sha256(f.read()).hexdigest()
    with open(OUT_FILEPATH, 'rb') as f:
        output_sha256 = hashlib.sha256(f.read()).hexdigest()
    assert(input_sha256 == output_sha256)
    logger.info("Data transfered successfully!")
    os.remove(IN_FILEPATH)
    shutil.rmtree(OUT_DIR)


class DCCSend(irc.client.SimpleIRCClient):

    def __init__(self, receiver, filename):
        irc.client.SimpleIRCClient.__init__(self)
        self.receiver = receiver
        self.filename = filename
        self.filesize = os.path.getsize(self.filename)
        self.file = open(filename, 'rb')
        self.sent_bytes = 0

    def on_welcome(self, connection, event):
        self.dcc = self.dcc_listen("raw")
        msg_parts = map(str, (
            'SEND',
            os.path.basename(self.filename),
            irc.client.ip_quad_to_numstr(self.dcc.localaddress),
            self.dcc.localport,
            self.filesize,
        ))
        msg = subprocess.list2cmdline(msg_parts)
        self.connection.ctcp("DCC", self.receiver, msg)

    def on_dcc_connect(self, connection, event):
        if self.filesize == 0:
            self.dcc.disconnect()
            return
        self.send_chunk()

    def on_dcc_disconnect(self, connection, event):
        print("Sent file %s (%d bytes)." % (self.filename, self.filesize))
        self.connection.quit()

    def on_dccmsg(self, connection, event):
        acked = struct.unpack("!I", event.arguments[0])[0]
        if acked == self.filesize:
            self.dcc.disconnect()
            self.connection.quit()
        elif acked == self.sent_bytes:
            self.send_chunk()

    def on_disconnect(self, connection, event):
        sys.exit(0)

    def on_nosuchnick(self, connection, event):
        print("No such nickname:", event.arguments[0])
        self.connection.quit()

    def send_chunk(self):
        data = self.file.read(1024)
        self.dcc.send_bytes(data)
        self.sent_bytes = self.sent_bytes + len(data)


class DCCReceive(irc.client.SimpleIRCClient):

    def __init__(self):
        irc.client.SimpleIRCClient.__init__(self)
        self.received_bytes = 0

    def on_ctcp(self, connection, event):
        payload = event.arguments[1]
        parts = shlex.split(payload)
        command, filename, peer_address, peer_port, size = parts
        assert(filename == IN_FILENAME)
        if command != "SEND":
            return
        self.filename = OUT_FILEPATH
        if os.path.exists(self.filename):
            print("A file named", self.filename,
                  "already exists. Refusing to save it.")
            self.connection.quit()
            return
        self.file = open(self.filename, "wb")
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        self.dcc = self.dcc_connect(peer_address, peer_port, "raw")

    def on_dccmsg(self, connection, event):
        data = event.arguments[0]
        self.file.write(data)
        self.received_bytes = self.received_bytes + len(data)
        self.dcc.send_bytes(struct.pack("!I", self.received_bytes))

    def on_dcc_disconnect(self, connection, event):
        self.file.close()
        print("Received file %s (%d bytes)." % (self.filename,
                                                self.received_bytes))
        self.connection.quit()
        cleanup()

    def on_disconnect(self, connection, event):
        sys.exit(0)


def main():

    logger.info("TEST SETUP")
    logger.info("Server: " + SERVER)
    logger.info("Port: " + str(PORT))
    logger.info("Sender nick: " + SENDER_NICK)
    logger.info("Receiver nick: " + RECEIVER_NICK)
    logger.info("Input file: " + IN_FILEPATH)
    logger.info("Output dir: " + OUT_DIR)

    # create random file
    with open(IN_FILEPATH, 'wb') as fout:
        fout.write(os.urandom(1024))  # 1K random data

    # start receiver
    def receiver_main():
        logger.info("Starting receiver")
        client_receiver = DCCReceive()
        try:
            client_receiver.connect(SERVER, PORT, RECEIVER_NICK)
        except irc.client.ServerConnectionError as x:
            print(x)
            sys.exit(1)
        client_receiver.start()

    # start sender
    def sender_main():
        logger.info("Starting sender")
        client_sender = DCCSend(RECEIVER_NICK, IN_FILEPATH)
        try:
            client_sender.connect(SERVER, PORT, SENDER_NICK)
        except irc.client.ServerConnectionError as x:
            print(x)
            sys.exit(1)
        client_sender.start()

    # start threads
    receiver_thread = threading.Thread(target=receiver_main)
    receiver_thread.start()
    time.sleep(10)
    sender_thread = threading.Thread(target=sender_main)
    sender_thread.start()


if __name__ == "__main__":
    main()
