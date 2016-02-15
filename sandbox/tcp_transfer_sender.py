#!/usr/bin/env python
# coding: utf-8

import time
import hashlib
import socket


SIZE = 4096
TRANSPORT = ("127.0.0.1", 12345)
CHUNK = "X" * SIZE


# setup benchmark
sent = 0
hasher = hashlib.sha256()
start = time.time()


# setup socket
_socket = socket.socket()
_socket.connect(TRANSPORT)


# send data
while (time.time() - start) < 30.0:  # send data for 30sec
    _socket.send(CHUNK)
    hasher.update(CHUNK)
    sent += SIZE


# close socket
_socket.shutdown(socket.SHUT_WR)
_socket.close()


# show results
print "Sent: {0}".format(hasher.hexdigest())
print "Speed: {0}Mbit/s".format(((sent / 30.0) / (1024.0 * 1024.0)) * 8.0)
