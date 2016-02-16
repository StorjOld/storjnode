"""
Previous reads / writes for file transfers were done with blocking I/O.
This meant waiting on calls to finish reading or writing data before
control was passed back to the application = slow.

This class solves the problem by streaming the content. It uses queues to
have content queued to be saved to files or read back. In this way -
the threads preemptively buffer data so there's never a delay. Kind of like
regular BufferedRead + BufferedWriter but with threads handling re-buffering
so the main thread is never blocked.
"""

import time
from threading import Thread
from queue import Queue
from storjnode.util import generate_random_file
import os


class FileStream:
    def __init__(self, chunk_size=1024 * 1024, queue_size=250):
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
                    # Point to end of stream.
                    stream["fp"].seek(stream["bytes_written"], 0)

                    # Reference to queue item without popping.
                    buf = stream["write_queue"].queue[0]
                    try:
                        stream["fp"].write(buf)
                    except IOError:
                        time.sleep(0.0001)
                        continue
                    stream["bytes_written"] += len(buf)

                    # Item is only removed when write is done!
                    stream["write_queue"].get()

                # Process read.
                while stream["read_queue"].qsize() < self.queue_size:
                    if stream["bytes_written"]:
                        if stream["bytes_read"] >= stream["bytes_written"]:
                            break

                    stream["fp"].seek(stream["bytes_read"], 0)
                    try:
                        buf = memoryview(stream["fp"].read(self.chunk_size))
                        if buf == b"":
                            break
                        else:
                            stream["bytes_read"] += len(buf)
                            stream["read_queue"].put(buf)
                    except IOError:
                        # Hard drive is busy.
                        time.sleep(0.0001)
                        pass

            # 50 MB 10 times a second = 500 MB
            # Max speed .:. = 3.9 gbs
            # (Actual speed depends on hardware)
            time.sleep(0.001)

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
            stream["read_offset"] = -1
            stream["write_pointer"] = b""
            stream["fp"] = open(path, 'rb+', 0)  # Unbuffered.
            self.streams[path] = stream

    def close(self, path):
        stream = self.streams[path]
        stream["fp"].close()
        del self.streams[path]

    def read(self, path, position):
        # Get buf offset.
        # print("Reading position " + str(position) + " " + str(path))
        stream = self.streams[path]
        remainder = position % self.chunk_size

        # Reset stream offset.
        if not position:
            stream["read_offset"] = -1

        # Get a new chunk or index existing chunk.
        if not remainder:
            if stream["read_offset"] != position:
                stream["read_pointer"] = stream["read_queue"].get()
                stream["read_offset"] = position

            return stream["read_pointer"]
        else:
            return stream["read_pointer"][remainder:]

    def write(self, path, chunk):
        chunk = chunk
        stream = self.streams[path]
        remainder = self.chunk_size - len(stream["write_pointer"])
        if remainder:
            stream["write_pointer"] += chunk[0:self.chunk_size]

        # Queue this buffer and store the rest in a new buffer.
        if len(stream["write_pointer"]) == self.chunk_size:
            stream["write_queue"].put(stream["write_pointer"])
            stream["write_pointer"] = b""
            if len(chunk[self.chunk_size:]):
                stream["write_pointer"] += chunk[self.chunk_size:]

    def can_write(self, path):
        stream = self.streams[path]
        if stream["write_queue"].qsize() == self.queue_size:
            return False

        return True

    def is_writing_data(self, path):
        # Find stream.
        stream = self.streams[path]

        # Flush write pointer.
        if len(stream["write_pointer"]):
            stream["write_queue"].put(stream["write_pointer"])
            stream["write_pointer"] = b""

        # Return if queue has been processed.
        return not stream["write_queue"].empty()

    def can_read(self, path):
        stream = self.streams[path]
        if len(stream["read_pointer"]):
            return True
        else:
            return not stream["read_queue"].empty()

if __name__ == "__main__":
    """
    one_mb = 1024 * 1024
    x = FileStream()
    fp = generate_random_file(one_mb)
    path = os.path.join(
        os.getcwd(),
        fp.name
    )
    fp.close()
    x.open(path)
    y = x.read(path, 1)
    print(y)
    x.stop()
    print(len(y))
    """
    pass
