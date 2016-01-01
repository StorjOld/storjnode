import os
import psutil
import socket
import pyp2p
import tempfile
import binascii
import sys
import random
from crochet import wait_for
from pycoin.encoding import a2b_hashed_base58, b2a_hashed_base58
from collections import OrderedDict


# Converts unprintable strings to printable hex (if needed.)
def safe_log_var(v):
    try:
        v.encode("ascii")
        return v.decode("utf-8") + u" (ascii)"
    except UnicodeEncodeError:
        # To a byte string.
        as_bytes = b""
        if sys.version_info >= (3, 0, 0):
            codes = []
            for ch in v:
                codes.append(ord(ch))

            if len(codes):
                as_bytes = bytes(codes)
        else:
            for ch in v:
                as_bytes += chr(ord(ch))

        return binascii.hexlify(as_bytes).decode("utf-8") + u" (hex)"
    except UnicodeDecodeError:
        return binascii.hexlify(v).decode("utf-8") + u" (hex)"


def ordered_dict_to_list(o):
    l = []
    for key in list(o):
        value = o[key]
        if type(value) == OrderedDict:
            value = ordered_dict_to_list(value)

        pair = (key, value)
        l.append(pair)

    return l


def list_to_ordered_dict(l):
    d = OrderedDict()
    for key, value in l:
        if type(value) == list:
            d[key] = list_to_ordered_dict(value)
        else:
            d[key] = value

    return d


def generate_random_file(file_size):
    max_chunk_size = 8192
    remaining = file_size
    junk, path = tempfile.mkstemp()
    fp = open(path, "ab+", 0)  # Unbuffered.
    while remaining:
        if remaining < max_chunk_size:
            chunk_size = remaining
        else:
            chunk_size = max_chunk_size

        chunk = os.urandom(chunk_size)
        fp.write(chunk)
        remaining -= chunk_size

    fp.seek(0, 0)
    return fp


def parse_node_id_from_unl(unl):
    try:
        unl = pyp2p.unl.UNL(value=unl).deconstruct()
        return unl["node_id"]
    except:
        return b""


def address_to_node_id(address):
    """Convert a bitcoin address to a node id."""
    return a2b_hashed_base58(address)[1:]


def node_id_to_address(node_id):
    """Convert a node id to a bitcoin address."""
    return b2a_hashed_base58(b'\0' + node_id)


def full_path(path):
    """Resolves, sym links, rel paths, variables, and tilds to abs paths."""
    return os.path.realpath(os.path.expandvars(os.path.expanduser(path)))


def default_defered(defered, default):
    """Returns a default value if the defered failed, otherwise the result."""
    return defered.addCallback(lambda r: r[0] and r[1] or default)


def wait_for_defered(defered, timeout=5.0):
    """ Wait until defered resolves or fail if timeout exceeded.

    A simple wrapper around crochet.wait_for.

    Args:
        defered: twisted.internet.defer.Deferred to wait for
        timeout: time in seconds to wait befor call fails

    Raises:
        crochet.TimeoutError if call exceeds given timeout
    """
    @wait_for(timeout=timeout)
    def callback():
        return defered
    return callback()


def empty_queue(queue):
    result = []
    while not queue.empty():
        result.append(queue.get())
    return result


def get_inet_facing_ip():
    # source http://stackoverflow.com/a/1267524/90351
    try:
        return [l for l in ([ip for ip in socket.gethostbyname_ex(
            socket.gethostname())[2] if not ip.startswith("127.")][:1],
            [[(s.connect(('8.8.8.8', 80)), s.getsockname()[0], s.close())
                for s in [socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]
    except:  # pragma: no cover
        # inet not reachable
        return None  # pragma: no cover


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
    except (socket.error, ValueError) as e:
        return False


def valid_ipv6(ip):
    """Returns True if the given string is a valid IPv6 address."""
    try:
        socket.inet_pton(socket.AF_INET6, ip)
    except (socket.error, ValueError) as e:  # not a valid ip
        return False
    return True


def valid_ip(ip):
    """Returns True if the given string is a valid IPv4 or IPv6 address."""
    return valid_ipv4(ip) or valid_ipv6(ip)


def valid_port(port):
    return isinstance(port, int) and (0 <= port < 2 ** 16)


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


def get_fs_type(path):
    """Returns: path filesystem type or None.

    Example:
        > get_fs_type("/home")
        'ext4'
    """
    partitions = {}
    for partition in psutil.disk_partitions():
        partitions[partition.mountpoint] = (partition.fstype,
                                            partition.device)
    if path in partitions:
        return partitions[path][0]
    splitpath = path.split(os.sep)
    for i in range(len(splitpath), 0, -1):
        subpath = os.sep.join(splitpath[:i]) + os.sep
        if subpath in partitions:
            return partitions[subpath][0]
        subpath = os.sep.join(splitpath[:i])
        if subpath in partitions:
            return partitions[subpath][0]
    return None


def get_free_space(dirname):
    """Return folder/drive free space (in bytes)."""
    return psutil.disk_usage(dirname).free


def get_folder_size(start_path):  # source http://stackoverflow.com/a/1392549
    """Returns the total size of all files in a directory."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def ensure_path_exists(path):
    """Creates need directories if they do not already exist."""
    if not os.path.exists(path):
        os.makedirs(path)
    if not os.path.exists(path):
        msg = "Creating path {0} failed!"  # pragma: no cover
        raise Exception(msg.format(path))  # pragma: no cover


def get_unused_port(port):
    """Checks if port is already in use."""
    if port is None or port < 1024 or port > 49151:
        port = random.randint(1024, 49151)
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('', port))  # Try to open port
        except socket.error as e:
            if e.errno is 98:  # Errorno 98 means address already bound
                port += 1
                continue
            raise e
        s.close()
        return port
