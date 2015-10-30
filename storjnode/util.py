import os
import socket
import threading


def process_parallel_map(function, sequence):
    # TODO implement
    return list(map(function, sequence))


def threaded_parallel_map(function, sequence):
    # see http://stackoverflow.com/a/1704501/90351
    # see https://www.quantstart.com/articles/parallelising-python-with-threading-and-multiprocessing
    # TODO implement
    return list(map(function, sequence))


def empty_queue(queue):
    result = []
    while not queue.empty():
        result.append(queue.get())
    return result


def blocking_call(async_func, *args, **kwargs):
    """Converts an async function call into a synchronous blocking call.

    Arags:
        async_func: function that returns a twisted.internet.defer.Deferred
        *args: async function arguments
        **kwargs: async funtion keyword arguments

    Returns: Result of the async_func function call.
    """
    # FIXME replace usage with crochet calls
    finished = threading.Event()
    return_values = []

    def callback(*args, **kwargs):
        assert(len(args) == 1)
        return_values.append(args[0])
        finished.set()

    async_func(*args, **kwargs).addCallback(callback)
    finished.wait()  # block until callback called
    return return_values[0] if len(return_values) == 1 else None


def get_inet_facing_ip():
    # source http://stackoverflow.com/a/1267524/90351
    # better to use https://pypi.python.org/pypi/netifaces ?
    try:
        ip = [l for l in ([ip for ip in socket.gethostbyname_ex(
            socket.gethostname())[2] if not ip.startswith("127.")][:1],
            [[(s.connect(('8.8.8.8', 80)), s.getsockname()[0], s.close())
                for s in [socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]
        if not valid_ip(ip):
            return None
        return ip
    except:
        return None


def valid_ipv4(ip):
    """Returns True if the given string is a valid IPv4 address."""
    try:
        socket.inet_pton(socket.AF_INET, ip)
        return True
    except AttributeError:  # no inet_pton
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False
    except socket.error:
        return False


def valid_ipv6(ip):
    """Returns True if the given string is a valid IPv6 address."""
    try:
        socket.inet_pton(socket.AF_INET6, ip)
    except socket.error:  # not a valid ip
        return False
    return True


def valid_ip(ip):
    """Returns True if the given string is a valid IPv4 or IPv6 address."""
    return valid_ipv4(ip) or valid_ipv6(ip)


def chunks(items, size):
    """ Split list into chunks of the given size.
    Original order is preserved.

    Example:
        > chunks([1,2,3,4,5,6,7,8,9], 2)
        [[1, 2], [3, 4], [5, 6], [7, 8], [9]]
    """
    return [items[i:i+size] for i in range(0, len(items), size)]


def baskets(items, count):
    """ Place list itmes in list with given basket count.
    Original order is not preserved.

    Example:
        > baskets([1,2,3,4,5,6,7,8, 9, 10], 3)
        [[1, 4, 7, 10], [2, 5, 8], [3, 6, 9]]
    """
    _baskets = [[] for _ in range(count)]
    for i, item in enumerate(items):
        _baskets[i % count].append(item)
    return list(filter(None, _baskets))


# FIXME breaks windows build and is not needed yet.
#import psutil
#def get_fs_type(path):
#    """Returns: path filesystem type or None.
#
#    Example:
#        > get_fs_type("/home")
#        'ext4'
#    """
#    partitions = {}
#    for partition in psutil.disk_partitions():
#        partitions[partition.mountpoint] = (partition.fstype,
#                                            partition.device)
#    if path in partitions:
#        return partitions[path][0]
#    splitpath = path.split(os.sep)
#    for i in range(len(splitpath), 0, -1):
#        subpath = os.sep.join(splitpath[:i]) + os.sep
#        if subpath in partitions:
#            return partitions[subpath][0]
#        subpath = os.sep.join(splitpath[:i])
#        if subpath in partitions:
#            return partitions[subpath][0]
#    return None


def ensure_path_exists(path):
    """Creates need directories if they do not already exist."""
    if not os.path.exists(path):
        os.makedirs(path)
