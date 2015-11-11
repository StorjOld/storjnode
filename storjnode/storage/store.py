import os
import random
import logging
import storjnode


DEFAULT_APP_HOME = os.path.join(os.path.expanduser("~"), ".storj")
DEFAULT_STORE_PATH = os.path.join(DEFAULT_APP_HOME, "store")
DEFAULT_PATHS = {DEFAULT_STORE_PATH: {"limit": 0, "use_folder_tree": False}}
DEFAULT_SHARD_SIZE = 1024 * 1024 * 128  # 128M


log = logging.getLogger(__name__)


def _get_shard_path(store_path, shard_id, use_folder_tree,
                    create_needed_folders=False):
    if use_folder_tree:
        folders = os.path.join(*storjnode.util.chunks(shard_id, 3))
        store_path = os.path.join(store_path, folders)
        if create_needed_folders:
            storjnode.util.ensure_path_exists(store_path)
    return os.path.join(store_path, shard_id)


def setup(store_paths=None):
    """Setup store so it can be use to store shards.

    This will validate the store paths and create any needed directories.

    Args:
        store_paths: Mapping of storage paths to a dict of optional attributes.
                     limit: The folder size limit in bytes, 0 for no limit.
                     use_folder_tree: Files organized in a folder tree (always
                                      on if path leads to a fat partition).
    Returns:
        The normalized store_paths with any missing attributes added.

    Raises:
        AssertionError: If input not valid.

    Example:
        import storjnode
        store_paths = {
            "path/a": {"limit": 0, "use_folder_tree": False}
            "path/b": {"limit": 2 ** 32, "use_folder_tree": True}
        }
        normalized_paths = storjnode.storage.store.setup(store_paths)
    """
    normal_paths = {}
    store_paths = store_paths or DEFAULT_PATHS
    for path, attributes in store_paths.items():
        attributes = attributes or {}  # None allowed

        # check path
        path = os.path.realpath(path)
        storjnode.util.ensure_path_exists(path)

        # check limit
        limit = attributes.get("limit", 0)
        assert(isinstance(limit, int))
        assert(limit >= 0)
        free = storjnode.util.get_free_space(path)
        used = storjnode.util.get_folder_size(path)
        available = (free + used)
        if limit > available:
            msg = ("Invalid storage limit for {0}: {1} > available {2}."
                   "Using available {2}!")
            log.warning(msg.format(path, limit, available))
            limit = available  # set to available if to large

        # check use_folder_tree
        use_folder_tree = attributes.get("use_folder_tree", False)
        if not use_folder_tree and storjnode.util.get_fs_type(path) == "vfat":
            use_folder_tree = True

        normal_paths[path] = {
            "use_folder_tree": use_folder_tree, "limit": limit
        }
        msg = "Storing data in '{0}' with a capacity of {1}bytes!"
        log.info(msg.format(path, limit or available))
    return normal_paths


def get(store_paths, shard_id):
    """Retreives a shard from storage.

    Args:
        store_paths: Mapping of storage paths to a dict of optional attributes.
                     limit: The folder size limit in bytes, 0 for no limit.
                     use_folder_tree: Files organized in a folder tree (always
                                      on if path leads to a fat partition).
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
        store_paths = {"path/a": None, "path/b": None}
        shard = storjnode.storage.store.add(store_paths, id)
        # do something with the shard
        shard.close()
    """
    assert(storjnode.storage.shard.valid_id(shard_id))
    store_paths = setup(store_paths)  # setup if needed
    for store_path, attributes in store_paths.items():
        use_folder_tree = attributes["use_folder_tree"]
        shard_path = _get_shard_path(store_path, shard_id, use_folder_tree)
        if os.path.isfile(shard_path):
            return open(shard_path, "rb")
    raise KeyError("Shard {0} not found!".format(shard_id))


def add(store_paths, shard):
    """ Add a shard to the storage.

    Args:
        store_paths: Mapping of storage paths to a dict of optional attributes.
                     limit: The folder size limit in bytes, 0 for no limit.
                     use_folder_tree: Files organized in a folder tree (always
                                      on if path leads to a fat partition).
        shard: A file like object representing the shard.

    Raises:
        MemoryError: If note enough storage to add shard.
        AssertionError: If input not valid.

    Example:
        import storjnode
        shard = open("path/to/loose/shard", "rb")
        store_paths = {"path/a": None, "path/b": None}
        storjnode.storage.store.add(store_paths, shard)
        shard.close()
    """
    store_paths = setup(store_paths)  # setup if needed
    shard_id = shard.get_id()
    shard_size = shard.get_size()

    # shuffle store paths to spread shards somewhat evenly
    paths = store_paths.items()
    random.shuffle(paths)
    for store_path, attributes in paths:

        # check if store path limit reached
        used = storjnode.util.get_folder_size(store_path)
        available = attributes["limit"] - used
        if shard_size > available:
            msg = ("Store path limit reached for {3} cannot add {0}: "
                   "Required {1} > {2} available.")
            log.warning(msg.format(shard_id, shard_size, available, store_path))
            continue  # try next storepath

        # check if enough free disc space
        free_space = storjnode.util.get_free_space(store_path)
        if shard_size > free_space:
            msg = ("Not enough disc space to add {0}: "
                   "Required {1} > {2} available.")
            msg = msg.format(shard_id, shard_size, free_space)
            log.warning(msg)
            continue  # try next storepath

        # save shard
        use_folder_tree = attributes["use_folder_tree"]
        shard_path = _get_shard_path(store_path, shard_id, use_folder_tree,
                                     create_needed_folders=True)
        return storjnode.storage.shard.save(shard, shard_path)

    raise MemoryError("Not enough space to add {0}!".format(shard_id))


def remove(store_paths, shard_id):
    """Remove a shard from the store.

    Args:
        store_paths: Mapping of storage paths to a dict of optional attributes.
                     limit: The folder size limit in bytes, 0 for no limit.
                     use_folder_tree: Files organized in a folder tree (always
                                      on if path leads to a fat partition).
        shard_id: Id of the shard to be removed.

    Raises:
        AssertionError: If input not valid.

    Example:
        import storjnode
        id = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"
        store_paths = {"path/a": None, "path/b": None}
        storjnode.storage.store.remove(store_paths, id)
    """
    assert(storjnode.storage.shard.valid_id(shard_id))
    store_paths = setup(store_paths)  # setup if needed
    for store_path, attributes in store_paths.items():
        use_folder_tree = attributes["use_folder_tree"]
        shard_path = _get_shard_path(store_path, shard_id, use_folder_tree)
        if os.path.isfile(shard_path):
            return os.remove(shard_path)


def import_file(store_paths, source_path, max_shard_size=DEFAULT_SHARD_SIZE):
    """Import a file into the store.

    Args:
        source_path: The path of the file to be imported.
        max_shard_size: The maximum shard size.

    Returns: A list of shard ids with the fist entry being the root shard.
                All required shards to reconstruct a file can be obtained
                from the root shard.
    """
    store_paths = setup(store_paths)  # setup if needed
    # FIXME add encryption
    # TODO implement


def export_file(store_paths, root_shard_id, dest_path):
    assert(storjnode.storage.shard.valid_id(root_shard_id))
    store_paths = setup(store_paths)  # setup if needed
    # FIXME add encryption
    # TODO implement
