#!/usr/bin/env python
# coding: utf-8


import hashlib
import socket


SIZE = 4096
TRANSPORT = ("127.0.0.1", 12345)


# setup socket
_socket = socket.socket()
_socket.bind(TRANSPORT)


# wait for connection
_socket.listen(5)
while True:
    connection, addr = _socket.accept()
    print 'Connection from', addr

    # receive data
    hasher = hashlib.sha256()
    data = connection.recv(1024)
    while (data):
        hasher.update(data)
        data = connection.recv(1024)

    # close connection
    print "Received: {0}".format(hasher.hexdigest())
    connection.close()
