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


def get_hash(shard, salt=None):
    """Get the hash of the shard.

    Args:
        shard: A file like object representing the shard.
        salt: Optional salt to add as a prefix before hashing.

    Returns: Hex digetst of sha256(salt + shard).
    """
    hasher = hashlib.sha256()
    if salt is not None:  # salt hash if requested
        hasher.update(salt)
    shard.seek(0)
    hasher.update(shard.read())
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
