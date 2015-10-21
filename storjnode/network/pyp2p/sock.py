"""
Implements a custom protocol for sending and receiving
line delineated messages. For blocking sockets,
time-out is required to avoid DoS attacks when talking
to a misbehaving or malicious third party.

The benefit of this class is it makes communication
with the P2P network easy to code without having to
depend on threads and hence on mutexes (which are hard
to use correctly.)

In practice, a connection to a node on the P2P network
would be done using the default options of this class
and the connection would periodically be polled for
replies. The processing of replies would automatically
break once the socket indicated it would block and
to prevent a malicious node from sending replies as
fast as it could - there would be a max message limit
per check period.
"""

import socket
import time
import ssl
import select
from .lib import *

class Sock:
    def __init__(self, addr=None, port=None, blocking=0, timeout=5, interface="default", use_ssl=0):
        self.reply_filter = None
        self.buf = ""
        self.max_buf = 1024 * 1024 #1 MB.
        self.max_chunks = 1024 #Prevents spamming of multiple short messages.
        self.chunk_size = 100 * 1024
        self.replies = []
        self.blocking = blocking
        self.timeout = timeout
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.use_ssl = use_ssl
        if self.use_ssl:
            self.s = ssl.wrap_socket(self.s)
        self.connected = 0
        self.interface = interface

        #Set a timeout for blocking operations so they don't DoS the program.
        #Disabled after connect if non-blocking is set.
        self.s.settimeout(self.timeout)

        #Connect socket.
        if addr != None and port != None:
            self.connect(addr, port)

    def set_sock(self, s):
        self.close() #Close old socket.
        self.s = s
        self.connected = 1
        if not self.blocking:
            #Non-blocking.
            self.s.setblocking(self.blocking)
        else:
            #Blocking.
            if self.timeout != None:
                self.s.settimeout(self.timeout)

    def connect(self, addr, port):
        if self.s == None:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.use_ssl:
                self.s = ssl.wrap_socket(self.s)

        #Make connection from custom interface.
        if self.interface != "default":
            try:
                src_ip = get_lan_ip(self.interface)
                self.s.bind((src_ip, 0))
            except:
                #Already bound.
                pass

        try:
            self.s.connect((addr, int(port)))
            self.connected = 1
            if not self.blocking:
                self.s.setblocking(self.blocking)
        except:
            self.close()
            raise Exception("Socket connect failed.")

    def close(self):
        try:
            try:
                self.s.shutdown(socket.SHUT_RDWR)
            except:
                pass
            self.s.close()
            self.s = None
            self.connected = 0
        except:
            pass

    def parse_buf(self):
        """
        Since TCP is a stream-orientated protocol, responses aren't guaranteed
        to be complete when they arrive. The buffer stores all the data and
        this function splits the data into replies based on the new line
        delimiter.
        """
        buf_len = len(self.buf)
        replies = []
        reply = ""
        chop = 0
        skip = 0
        i = 0
        for ch in self.buf:
            if skip:
                skip -= 1
                i += 1
                continue

            nxt = i + 1
            if nxt < buf_len:
                if ch == "\r" and self.buf[nxt] == "\n":
                    #Append new reply.
                    if reply != "":
                        replies.append(reply)
                        reply = ""

                    #Truncate the whole buf if chop is out of bounds.
                    chop = nxt + 1
                    skip = 1
                    i += 1
                    continue

            reply += ch
            i += 1

        #Truncate buf.
        if chop:
            self.buf = self.buf[chop:]

        return replies

    def get_chunks(self):
        """
        This is the function which handles retrieving new data chunks. It's
        main logic is avoiding a recv call blocking forever and halting
        the program flow. To do this, it manages errors and keeps an eye
        on the buffer to avoid overflows and DoS attacks.

        http://stackoverflow.com/questions/16745409/what-does-pythons-socket-recv-return-for-non-blocking-sockets-if-no-data-is-r
        http://stackoverflow.com/questions/3187565/select-and-ssl-in-python
        """

        #Socket is disconnected.
        if not self.connected:
            return

        #Recv chunks until network buffer is empty.
        repeat = 1
        wait = 0.2
        t = time.time()
        chunk_no = 0
        while repeat:
            #Timeout.
            elapsed = int(time.time() - t)
            if elapsed >= self.timeout and self.timeout and self.blocking:
                raise socket.error("Socket timeout.")
                break

            chunk_size = self.chunk_size
            while True:
                #Don't exceed buffer size.
                buf_len = len(self.buf)
                if buf_len >= self.max_buf:
                    break
                remaining = self.max_buf - buf_len
                if remaining < chunk_size:
                    chunk_size = remaining

                #Don't allow non-blocking sockets to be
                #DoSed by multiple small replies.
                if chunk_no >= self.max_chunks and not self.blocking:
                    break
                
                try:
                    chunk = self.s.recv(chunk_size)
                except socket.timeout as e:
                    #Timeout on blocking sockets.
                    err = e.args[0]
                    if err == "timed out":
                        break
                except ssl.SSLError as e:
                    #Will block on non-blocking SSL sockets.
                    if e.errno == ssl.SSL_ERROR_WANT_READ:
                        break
                    else:
                        self.close()
                        return
                except socket.error as e:
                    #Will block on nonblocking non-SSL sockets.
                    err = e.args[0]
                    if err == socket.EAGAIN or err == socket.EWOULDBLOCK:
                        break
                    else:
                        #Connection closed or other problem.
                        self.close()
                        return
                else:
                    if chunk == b"":
                        self.close()
                        return

                    #Avoid decoding errors.
                    try:
                        self.buf += chunk.decode("utf-8")
                    except:
                        continue

                    if self.blocking:
                        break

                    chunk_no += 1

            repeat = 0
            if self.blocking:
                #Partial response.
                if "\r\n" not in self.buf:
                    repeat = 1
                    time.sleep(wait)

    def reply_callback(self, callback):
        self.reply_callback = callback

    #Called to check for replies and update buffers.
    def update(self):
        self.get_chunks()        
        self.replies = self.parse_buf()

    def send(self, msg):
        if not self.connected:
            return 0

        if type(msg) == str:
            msg = msg.encode("ascii")

        try:
            self.s.send(msg)
            return len(msg)
        except:
            self.close()
            return 0

    def recv(self, n):
        if not self.connected:
            return 0
        try:
            ret = self.s.recv(n)
            if type(ret) == bytes:
                return ret.decode("utf-8")
            else:
                return ret
        except:
            self.close()
            return 0

    #Sends a new message delimitered by a new line.
    def send_line(self, msg):
        if not self.connected:
            print("Connection died before send!")
            return 0

        msg += "\r\n"
        try:
            self.s.send(msg.encode("ascii"))
            return 1
        except Exception as e:
            print(e)
            print("Connection died before send 2!")
            self.close()
            return 0

    #Receives a new message delimited by a new line.
    #(Blocking until at least one reply or max buf.)
    def recv_line(self):
        while not len(self.replies) or len(self.buf) >= self.max_buf:
            #Socket is disconnected.
            if not self.connected:
                return ""

            self.update()

        if len(self.replies):
            temp = self.replies[0]
            self.replies = self.replies[1:]
            return temp
        else:
            raise socket.error("Buffer full.")

    """
    These functions here make the class behave like a list. The
    list is a collection of replies received from the socket.
    Every iteration also has the bonus of checking for any
    new replies so it is very easy, for example to do:
    for replies in sock:
        To process replies without handling networking boilerplate.
    """
    def __len__(self):
        self.update()
        return len(self.replies)

    def __getitem__(self, key):
        self.update()
        return self.replies[key]

    def __setitem__(self, key, value):
        self.update()
        self.replies[key] = value

    def __delitem__(self, key):
        self.update()
        del self.replies[key]

    def __iter__(self):
        #Get replies.
        self.update()

        #Execute callbacks on replies.
        if self.reply_filter != None:
            replies = list(filter(self.reply_filter, self.replies))
        else:
            replies = self.replies

        #Clear old replies.
        self.replies = []

        #Return replies.
        return iter(replies)

    def __reversed__(self):
        return self.__iter__()

