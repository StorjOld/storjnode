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


# load schema
dirname = os.path.dirname(storjnode.util.full_path(__file__))
schema_path = os.path.join(dirname, "config.schema")
with open(schema_path) as fp:
    SCHEMA = json.load(fp)


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
    return {
        "version": VERSION,
        "cold_storage": [],
        "network": {
            "port": "random",
            "enable_monitor_responses": True,
            "disable_data_transfer": False,
            "bandwidth_limits": {
                "secondly": {
                    "upload": 0,  # no limit
                    "download": 0  # no limit
                },
                "monthly": {
                    "upload": 10737418240,  # 10G
                    "download": 10737418240,  # 10G
                },
            },
        },
        "storage": {
            default_storage_path: {
                "limit": storjnode.storage.manager.DEFAULT_STORE_LIMIT,
                "use_folder_tree": fs_format == "vfat",
            },
        }
    }


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


class ConfigFile:

    def __init__(self, path=None):
        self.path = path or storjnode.common.CONFIG_PATH
        self.cfg = get(self.path)

    def save(self):
        save(self.path, self.cfg)

    def __getitem__(self, key):
        return self.cfg[key]

    def __setitem__(self, key, value):
        self.cfg[key] = value
        self.save()
