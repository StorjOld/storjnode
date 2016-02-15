"""
Previous reads / writes for file transfers were done with blocking I/O.
This meant waiting on calls to finish reading or writing data before control was passed back to the application = slow.

This class solves the problem by streaming the content. It uses queues to
have content queued to be saved to files or read back. In this way -
the threads preemptively buffer data so there's never a delay. Kind of like
regular BufferedRead + BufferedWriter but with threads handling re-buffering
so the main thread is never blocked.
"""

import time
from threading import Thread
from queue import Queue


class FileStream:
    def __init__(self, chunk_size=1024 * 1024, queue_size=30000):
        # (chunk_size * queue_size) ~50 MB memory use
        self.chunk_size = chunk_size
        self.queue_size = queue_size
        self.streams = {}  # "queue", "fp"
        self.is_running = False
        self.start()

    def start(self):
        self.is_running = True
        t = Thread(target=self.process_streams)
        t.setDaemon(True)
        t.start()

    def stop(self):
        self.is_running = False

    def process_streams(self):
        while self.is_running:
            for path in list(self.streams):
                # Get stream.
                stream = self.streams[path]

                # Process write.
                while not stream["write_queue"].empty():
                    stream["fp"].seek(stream["bytes_written"], 0)
                    buf = stream["write_queue"].get()
                    stream["fp"].write(buf)
                    stream["bytes_written"] += len(buf)

                # Process read.
                while stream["read_queue"].qsize() < self.queue_size:
                    if stream["bytes_written"]:
                        if stream["bytes_read"] >= stream["bytes_written"]:
                            break

                    stream["fp"].seek(stream["bytes_read"], 0)
                    buf = memoryview(stream["fp"].read(self.chunk_size))
                    if buf == b"":
                        break
                    else:
                        stream["bytes_read"] += len(buf)
                        stream["read_queue"].put(buf)

            time.sleep(0.00001)

    def open(self, path):
        if path in self.streams:
            return self.streams[path]
        else:
            stream = {}
            stream["read_queue"] = Queue(maxsize=self.queue_size)
            stream["write_queue"] = Queue(maxsize=self.queue_size)
            stream["bytes_read"] = 0
            stream["bytes_written"] = 0
            stream["read_pointer"] = b""
            stream["fp"] = open(path, 'rb+', 0)  # Unbuffered.
            self.streams[path] = stream

    def close(self, path):
        stream = self.streams[path]
        stream["fp"].close()
        del self.streams[path]

    def read(self, path, position):
        stream = self.streams[path]
        remainder = position % self.chunk_size
        if not remainder:
            # Todo - don't get here if already got.
            stream["read_pointer"] = stream["read_queue"].get()
            return stream["read_pointer"]
        else:
            return stream["read_pointer"][remainder:]

    def write(self, path, chunk):
        stream = self.streams[path]
        stream["write_queue"].put(chunk)

    def can_write(self, path):
        if path not in self.streams:
            return True

        stream = self.streams[path]
        if stream["write_queue"].qsize() == self.queue_size:
            return False

        return True

    def can_read(self, path):
        if path not in self.streams:
            return True

        stream = self.streams[path]
        if len(stream["read_pointer"]):
            return True
        else:
            return not stream["read_queue"].empty()

"""
x = FileStream()
path = "test"
x.open(path)
x.write(path, "a")
time.sleep(1)
y = FileStream()
y.open(path)
print(y.read(path))
"""