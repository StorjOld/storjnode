import os
import copy
import json
import storjnode
import jsonschema
from jsonschema.exceptions import ValidationError


VERSION = 1
UNMIGRATED_CONFIG = {"version": 0}  # initial unmigrated config


def _migrate_0_to_1(cfg):
    return create()


_MIGRATIONS = {
    0: _migrate_0_to_1,
}


_dirname = os.path.dirname(storjnode.util.full_path(__file__))


# load schema
_schema_path = os.path.join(_dirname, "config.schema")
with open(_schema_path) as fp:
    SCHEMA = json.load(fp)


# load default
_default_path = os.path.join(_dirname, "config.default.json")
with open(_default_path) as fp:
    DEFAULT_CONFIG = json.load(fp)


def read(path):
    """ Read a json config and decript with the given passwork if encrypted.

    Args:
        path: The path to the config file.

    Returns:
        The loaded config as json serializable data.
    """
    with open(path, 'r') as config_file:
        return json.loads(config_file.read())


def save(path, cfg):
    """Save a config as json and optionally encrypt.

    Args:
        path: The path to save the config file at.
        cfg: The config to be saved.

    Returns:
        The loaded config as json serializable data.

    Raises:
        storjnode.config.Invalid: If config is not valid.
    """
    # always validate before saving
    validate(cfg)

    # Create root path if it doesn't already exist.
    storjnode.util.ensure_path_exists(os.path.dirname(path))

    # Write config to file.
    with open(path, 'w') as config_file:
        config_file.write(json.dumps(cfg, indent=2))
        return cfg


def create():
    """Create a config with required values.

    Args:

    Returns:
        The config as json serializable data.
    """
    default_storage_path = storjnode.storage.manager.DEFAULT_STORE_PATH
    fs_format = storjnode.util.get_fs_type(default_storage_path)
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["version"] = VERSION
    cfg["storage"] = {
        default_storage_path: {
            "limit": storjnode.storage.manager.DEFAULT_STORE_LIMIT,
            "use_folder_tree": fs_format == "vfat",
        },
    }
    return cfg


def validate(cfg):
    """Validate that a config is correct.

    Args:
        cfg: The config to validate.

    Returns:
        True if the config is valid.

    Raises:
        storjnode.config.Invalid: If config is not valid.
    """

    jsonschema.validate(cfg, SCHEMA)

    # correct version
    if cfg["version"] != VERSION:
        msg = "Invalid version: {0} expected, got {1}"
        raise ValidationError(msg.format(VERSION, cfg.get("version")))

    return True


def get(path):
    """Load and migarte and existing config if needed, or save a default.

    Args:
        path: The path to the config file.

    Returns:
        The loaded config as json serializable data.

    Raises:
        storjnode.config.Invalid: If loaded config is not valid.
    """

    # load existing config
    if os.path.exists(path):
        cfg = read(path)

    # create default config if none exists
    else:
        cfg = create()
        cfg = save(path, cfg)

    # migrate config if needed
    migrated_cfg = migrate(copy.deepcopy(cfg))
    if migrated_cfg["version"] != cfg["version"]:
        cfg = save(path, migrated_cfg)

    return cfg


def _set_version(cfg, new_version):
    cfg['version'] = new_version
    return cfg


def migrate(cfg):
    if not isinstance(cfg, dict) or 'version' not in cfg:
        raise ValidationError()

    # migrate until we are at current version
    while cfg['version'] != VERSION:
        cfg = _MIGRATIONS[cfg['version']](cfg)

    return cfg
