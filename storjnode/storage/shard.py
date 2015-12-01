import re
import hashlib


def valid_id(shard_id):
    return bool(re.match(r"^[0-9abcdef]{64}$", shard_id))


def get_size(shard):
    """Get the size of a shard.

    Args:
        shard: A file like object representing the shard.

    Returns: The shard size in bytes.
    """
    shard.seek(0, 2)
    return shard.tell()


def get_hash(shard, salt=None, limit=None):
    """Get the hash of the shard.

    Args:
        shard: A file like object representing the shard.
        salt: Optional salt to add as a prefix before hashing.

    Returns: Hex digetst of sha256(salt + shard).
    """
    shard.seek(0)
    hasher = hashlib.sha256()
    if salt is not None:
        hasher.update(salt)

    # Don't read whole file into memory.
    remaining = limit
    max_chunk_size = 4096

    def get_chunk_size(remaining, max_chunk_size):
        if remaining is not None:
            if remaining < max_chunk_size:
                return remaining
            else:
                return max_chunk_size
        else:
            return max_chunk_size

    while 1:
        chunk_size = get_chunk_size(remaining, max_chunk_size)
        chunk = shard.read(chunk_size)
        if chunk == b"":
            break

        hasher.update(chunk)
        if remaining is not None:
            remaining -= chunk_size

    shard.seek(0)
    return hasher.hexdigest()


def get_id(shard):
    """Returns the sha256 sum of the shard"""
    return get_hash(shard)


def copy(src_shard, dest_fobj):
    """Copy a shard to a file like object.

    Args:
        src_shard: A file like object representing the shard to copy.
        dest_fobj: A file like object to copy the shard to.
    """
    src_shard.seek(0)
    dest_fobj.write(src_shard.read())


def save(shard, path):
    """Copy a shard to a file.

    Args:
        src_shard: A file like object representing the shard to copy.
        path: The path to save the shard at.
    """
    with open(path, "wb") as fobj:
        copy(shard, fobj)
