import os
import random
import storjnode
from storjnode.common import STORJ_HOME


DEFAULT_SHARD_SIZE = 1024 * 1024 * 128  # 128M
DEFAULT_STORE_PATH = os.path.join(STORJ_HOME, "store")
DEFAULT_STORE_CONFIG = {
    DEFAULT_STORE_PATH: {"limit": 0, "use_folder_tree": False}
}


_log = storjnode.log.getLogger(__name__)
_builtin_open = open


def _get_shard_path(store_path, shard_id, use_folder_tree,
                    create_needed_folders=False):
    if use_folder_tree:
        folders = os.path.join(*storjnode.util.chunks(shard_id, 3))
        store_path = os.path.join(store_path, folders)
        if create_needed_folders:
            storjnode.util.ensure_path_exists(store_path)
    return os.path.join(store_path, shard_id)


def setup(store_config=None):
    """Setup store so it can be use to store shards.

    This will validate the store paths and create any needed directories.

    Args:
        store_config: Dict of storage paths to optional attributes.
                      limit: The dir size limit in bytes, 0 for no limit.
                      use_folder_tree: Files organized in a folder tree
                                       (always on for fat partitions).
    Returns:
        The normalized store_config with any missing attributes added.

    Raises:
        AssertionError: If input not valid.

    Example:
        import storjnode
        store_config = {
            "path/alpha": {"limit": 0, "use_folder_tree": False}
            "path/beta": {"limit": 2**32, "use_folder_tree": True}
        }
        normalized_paths = storjnode.storage.store.setup(store_config)
    """
    normal_paths = {}
    store_config = store_config or DEFAULT_STORE_CONFIG
    for path, attributes in store_config.items():
        attributes = attributes or {}  # None allowed

        # check path
        path = os.path.realpath(path)
        storjnode.util.ensure_path_exists(path)

        # check limit
        limit = attributes.get("limit", 0)
        assert(isinstance(limit, int) or isinstance(limit, long))
        assert(limit >= 0)
        free = storjnode.util.get_free_space(path)
        used = storjnode.util.get_folder_size(path)
        available = (free + used)
        if limit > available:
            msg = ("Invalid storage limit for {0}: {1} > available {2}. "
                   "Using available {2}!")
            _log.warning(msg.format(path, limit, available))
            limit = available  # set to available if to large

        # check use_folder_tree
        use_folder_tree = attributes.get("use_folder_tree", False)
        if not use_folder_tree and storjnode.util.get_fs_type(path) == "vfat":
            use_folder_tree = True  # pragma: no cover

        normal_paths[path] = {
            "use_folder_tree": use_folder_tree, "limit": limit
        }
        msg = "Storing data in '{0}' with a capacity of {1}bytes!"
        # _log.info(msg.format(path, limit or available))
    return normal_paths


def open(store_config, shard_id):
    """Retreives a shard from storage.

    Args:
        store_config: Dict of storage paths to optional attributes.
                      limit: The dir size limit in bytes, 0 for no limit.
                      use_folder_tree: Files organized in a folder tree
                                       (always on for fat partitions).
        shard_id: Id of the shard to retreive.

    Returns:
        A read only file object for the shard, the caller is responsable
        for closing the file object.

    Raises:
        KeyError: If shard was not found.
        AssertionError: If input not valid.

    Example:
        import storjnode
        id = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        store_config = {"path/alpha": None, "path/beta": None}
        with storjnode.storage.store.open(store_config, id) as shard:
            print(storjnode.storage.shard.get_id(shard)
    """
    shard_path = find(store_config, shard_id)
    if shard_path is not None:
        return _builtin_open(shard_path, "rb")
    else:
        raise KeyError("Shard {0} not found!".format(shard_id))


def capacity(store_config):
    """ Get the total, used and free capacity of the store.

    Args:
        store_config: Dict of storage paths to optional attributes.
                      limit: The dir size limit in bytes, 0 for no limit.
                      use_folder_tree: Files organized in a folder tree
                                       (always on for fat partitions).

    Returns:
        {"total": int, "used": int, "free": int}

    Raises:
        AssertionError: If input not valid.

    Example:
        import storjnode
        store_config = {"path/alpha": None, "path/beta": None}
        print(storjnode.storage.manager.capacity(store_config))
    """
    store_config = setup(store_config=store_config)  # setup if needed
    total, used, free = 0, 0, 0
    # FIXME doesn't give correct total if multiple paths on same drive
    for store_path, attributes in store_config.items():
        free_disc_space = storjnode.util.get_free_space(store_path)
        limit = attributes["limit"] or free_disc_space
        path_used = storjnode.util.get_folder_size(store_path)
        total += limit
        used += path_used
        free += limit - used
    return {"total": total, "used": used, "free": free}


def add(store_config, shard):
    """ Add a shard to the storage.

    Args:
        store_config: Dict of storage paths to optional attributes.
                      limit: The dir size limit in bytes, 0 for no limit.
                      use_folder_tree: Files organized in a folder tree
                                       (always on for fat partitions).
        shard: A file like object representing the shard.

    Returns:
        Path to the added shard.

    Raises:
        MemoryError: If note enough storage to add shard.
        AssertionError: If input not valid.

    Example:
        import storjnode
        store_config = {"path/a": None, "path/b": None}
        with open("path/to/loose/shard", "rb") as shard:
            storjnode.storage.store.add(store_config, shard)
    """
    store_config = setup(store_config=store_config)  # setup if needed
    shard_id = storjnode.storage.shard.get_id(shard)
    shard_size = storjnode.storage.shard.get_size(shard)

    # check if already in storage
    shard_path = find(store_config, shard_id)
    if shard_path is not None:
        return shard_path

    # shuffle store paths to spread shards somewhat evenly
    items = store_config.items()
    random.shuffle(items)
    for store_path, attributes in items:

        # check if store path limit reached
        limit = attributes["limit"]
        used = storjnode.util.get_folder_size(store_path)
        free = limit - used
        if limit > 0 and shard_size > free:
            msg = ("Store path limit reached for {3} cannot add {0}: "
                   "Required {1} > {2} free.")
            _log.warning(msg.format(shard_id, shard_size,
                                    free, store_path))
            continue  # try next storepath

        # check if enough free disc space
        free_space = storjnode.util.get_free_space(store_path)
        if shard_size > free_space:
            msg = ("Not enough disc space in {3} to add {0}: "
                   "Required {1} > {2} free.")
            msg = msg.format(shard_id, shard_size, free_space, store_path)
            _log.warning(msg)
            continue  # try next storepath

        # save shard
        use_folder_tree = attributes["use_folder_tree"]
        shard_path = _get_shard_path(store_path, shard_id, use_folder_tree,
                                     create_needed_folders=True)
        storjnode.storage.shard.save(shard, shard_path)
        return shard_path

    raise MemoryError("Not enough space to add {0}!".format(shard_id))


def remove(store_config, shard_id):
    """Remove a shard from the store.

    Args:
        store_config: Dict of storage paths to optional attributes.
                      limit: The dir size limit in bytes, 0 for no limit.
                      use_folder_tree: Files organized in a folder tree
                                       (always on for fat partitions).
        shard_id: Id of the shard to be removed.

    Raises:
        AssertionError: If input not valid.

    Example:
        import storjnode
        id = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        store_config = {"path/alpha": None, "path/beta": None}
        storjnode.storage.store.remove(store_config, id)
    """
    shard_path = find(store_config, shard_id)
    if shard_path is not None:
        return os.remove(shard_path)


def find(store_config, shard_id):
    """Find the path of a shard.

    Args:
        store_config: Dict of storage paths to optional attributes.
                      limit: The dir size limit in bytes, 0 for no limit.
                      use_folder_tree: Files organized in a folder tree
                                       (always on for fat partitions).
        shard_id: Id of the shard to find.

    Returns:
        Path to the shard or None if not found.

    Raises:
        AssertionError: If input not valid.

    Example:
        import storjnode
        id = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        store_config = {"path/alpha": None, "path/beta": None}
        shard_path = storjnode.storage.store.remove(store_config, id)
        print("shard located at %s" % shard_path)
    """
    assert(storjnode.storage.shard.valid_id(shard_id))
    store_config = setup(store_config=store_config)  # setup if needed
    for store_path, attributes in store_config.items():
        use_folder_tree = attributes["use_folder_tree"]
        shard_path = _get_shard_path(store_path, shard_id, use_folder_tree)
        if os.path.isfile(shard_path):
            return shard_path
    return None


# def import_file(store_config, source_path,
#                 max_shard_size=DEFAULT_SHARD_SIZE):
#     """Import a file into the store.
#
#     Args:
#         source_path: The path of the file to be imported.
#         max_shard_size: The maximum shard size.
#
#     Returns: A list of shard ids with the fist entry being the root shard.
#                 All required shards to reconstruct a file can be obtained
#                 from the root shard.
#     """
#     store_config = setup(store_config=store_config)  # setup if needed
#     # FIXME add encryption
#     # TODO implement
#
#
# def export_file(store_config, root_shard_id, dest_path):
#     assert(storjnode.storage.shard.valid_id(root_shard_id))
#     store_config = setup(store_config=store_config)  # setup if needed
#     # FIXME add encryption
#     # TODO implement
