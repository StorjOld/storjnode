import os
import random
import logging
from storjnode import util


DEFAULT_APP_HOME = os.path.join(os.path.expanduser("~"), ".storj")
DEFAULT_STORE_PATH = os.path.join(DEFAULT_APP_HOME, "store")
DEFAULT_PATHS = {DEFAULT_STORE_PATH: {"limit": 0, "use_folder_tree": False}}
DEFAULT_SHARD_SIZE = 1024 * 1024 * 128  # 128M
DEFAULT_REDUNDANCY_LEVEL = 3


log = logging.getLogger(__name__)


class Store(object):

    def __init__(self, paths=None):
        """Storage manages shard storage and also has usefull shard functions.

        Args:
            paths: Mapping of storage folder paths to a dict of optional
                   attributes. Attribute "limit" is the folder size limit in
                   bytes. Attribute "use_folder_tree" will organize files in a
                   folder tree (always on if path leads to a fat partition).
                   {"folder/path": {"limit": 0, "use_folder_tree": False}}

        Example:
            storage = Storage(paths={
                "folder/path": {"limit": 0, "use_folder_tree": False}
            })
        """
        self.paths = {}
        paths = paths or DEFAULT_PATHS
        for path, attributes in paths.items():
            attributes = attributes or {}  # None allowed

            # check path
            path = os.path.realpath(path)
            util.ensure_path_exists(path)

            # check limit
            limit = attributes.get("limit", 0)
            assert(isinstance(limit, int))
            assert(limit >= 0)
            available = util.get_free_space(path)
            if limit > available:
                msg = "Invalid storage limit for {0}: {1} > available {2}"
                log.warning(msg.format(path, limit, available))
                limit = available  # set to available if to large
            limit = limit or available  # replace 0 with available

            # check use_folder_tree
            use_folder_tree = attributes.get("use_folder_tree", False)
            if not use_folder_tree and util.get_fs_type(path) == "vfat":
                use_folder_tree = True

            self.paths[path] = {
                "use_folder_tree": use_folder_tree, "limit": limit
            }
            log.info("Storing data in '{0}'!".format(path))
            log.info("Storage capacity {0}bytes!".format(self._path))

    def get(shard_id):
        """Retreives a shard from storage.

        Returns:
            A read only file like object for the shard, the caller is
            responsable for closing the file object.

        Raises:
            KeyError: If shard was not found.
        """
        for store_path, attributes in self.paths.items():
            use_folder_tree = attributes["use_folder_tree"]
            shard_path = self._get_shard_path(
                store_path, shard_id, use_folder_tree=use_folder_tree
            )
            if os.path.isfile(shard_path):
                return Shard(open(shard_path, "rb"))
        raise KeyError("Shard {0} not found!".format(shard_id))

    def remove(shard_id):
        """Remove a shard from the store."""
        pass  # TODO implement

    def import_file(source_path, redundancy_level=DEFAULT_REDUNDANCY_LEVEL,
                    max_shard_size=DEFAULT_SHARD_SIZE, shard_padding=True):
        """Import a file into the store.
        
        Args:
            source_path: The path of the file to import.
            redundancy_level: TODO doc string
            max_shard_size: The maximum shard size (must be a power of two).
            shard_padding: Padd shard to the next power of two.

        Returns: A mapping of root shard ids to child shards with one root
             shard for every redundancy level. If the file fit in a single
             shard the child shards will be empty.

        
        """
        # FIXME add encryption



        
        pass  # TODO implement

    def export_file(root_shard_id, dest_path):
        pass  # TODO implement

    def add(shard):
        """ Add a shard to the storage.

        """
        shard_id = shard.get_id()
        shard_size = shard.get_size()

        # shuffle store paths to spread shards somewhat evenly
        paths = self.paths.copy().items()
        random.shuffle(paths)
        for store_path, attributes in self.paths.items():

            # check if store path limit reached
            store_path_size = util.get_folder_size(store_path)
            free_store_path_space = attributes["limit"] - store_path_size
            if shard_size > free_store_path_space:
                msg = ("Not enough space in {3} to add {0}: "
                       "Required {1} > {2} available.")
                log.warning(msg.format(shard_id, shard_size,
                                       free_store_path_space, store_path))
                continue  # try next storepath

            # check enough free disc space
            free_space = get_free_space(store_path)
            if shard_size > free_space:
                msg = ("Not enough disc space to add {0}: "
                       "Required {1} > {2} available.")
                msg = msg.format(shard_id, shard_size, free_space)
                log.error(msg)
                raise MemoryError(msg)

            # save shard
            use_folder_tree = attributes["use_folder_tree"]
            shard_path = self._get_shard_path(
                store_path, shard_id, use_folder_tree=use_folder_tree,
                create_needed_folders=True
            )
            return shard.save(shard_path)

        raise MemoryError("Not enough space to add {0}!".format(shard_id))

    def _get_shard_path(self, store_path, shard_id, use_folder_tree=False,
                        create_needed_folders=False):
        if use_folder_tree:
            folders = os.path.join(*util.chunks(shard_id, 3))
            store_path = os.path.join(store_path, folders)
            if create_needed_folders:
                control.util.ensure_path_exists(store_path)
        return os.path.join(store_path, shard_id)


