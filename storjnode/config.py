import os
import copy
import json
import storjnode
import jsonschema
from btctxstore import BtcTxStore
from jsonschema.exceptions import ValidationError


VERSION = "3.1.0"  # config version divorced from software version!
DEFAULT_CONFIG_PATH = os.path.join(storjnode.common.STORJ_HOME, "config.json")


SCHEMA = {
    "$schema": "http://json-schema.org/schema#",

    "definitions": {

        "wallet": {
            "type": "object",
            "properties": {
                "hwif": {
                    "type": "string",
                    "pattern": "^[a-km-zA-HJ-NP-Z0-9]+$"  # base58 encoded
                },
                "cold_storage": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "pattern": "^[13][a-km-zA-HJ-NP-Z0-9]{26,33}$"
                    }
                },
            },
            "additionalProperties": False,
            "required": ["hwif", "cold_storage"],
        },

        "storage": {
            "type": "object",
            "patternProperties": {
                "^.*$": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 0},
                        "use_folder_tree": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                    "required": ["limit", "use_folder_tree"],
                },
            },
            "minProperties": 1,
            "additionalProperties": False,
        },

        "bandwidth_limits": {
            "type": "object",
            "properties": {
                "upload": {"type": "integer", "minimum": 0},
                "download": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
            "required": ["upload", "download"],
        },

        "network": {
            "type": "object",
            "properties": {
                "bandwidth_limits": {
                    "type": "object",
                    "properties": {
                        "secondly": {"$ref": "#/definitions/bandwidth_limits"},
                        "monthly": {"$ref": "#/definitions/bandwidth_limits"},
                    },
                    "additionalProperties": False,
                    "required": ["secondly", "monthly"],
                },
                "port": {
                    "oneOf": [
                        {"type": "integer", "minimum": 1024, "maximum": 65535},
                        {"enum": ["random"]},
                    ]
                },
                "enable_monitor_responses": {"type": "boolean"},
                "disable_data_transfer": {"type": "boolean"},
            },
            "additionalProperties": False,
            "required": [
                "bandwidth_limits", "port",
                "enable_monitor_responses",
                "disable_data_transfer",
            ],
        },

    },

    "type": "object",
    "properties": {
        "version": {
            "type": "string",
            "pattern": "^[0-9]+\.[0-9]+\.[0-9]+$"
        },
        "wallet": {"$ref": "#/definitions/wallet"},
        "network": {"$ref": "#/definitions/network"},
        "storage": {"$ref": "#/definitions/storage"},
    },
    "additionalProperties": False,
    "required": ["version", "wallet", "network", "storage"]
}


def read(path, password=None):
    """ Read a json config and decript with the given passwork if encrypted.

    Args:
        path: The path to the config file.
        password: The password to decrypt if encrypted.

    Returns:
        The loaded config as json serializable data.
    """
    if password is None:  # unencrypted
        with open(path, 'r') as config_file:
            return json.loads(config_file.read())
    else:
        raise NotImplementedError("encryption not implemented")


def save(btctxstore, path, cfg, password=None):
    """Save a config as json and optionally encrypt.

    Args:
        btctxstore: btctxstore.BtcTxStore instance used to validate wallet.
        path: The path to save the config file at.
        cfg: The config to be saved.
        password: The password to encrypt with if, unencrypted if None.

    Returns:
        The loaded config as json serializable data.

    Raises:
        storjnode.config.Invalid: If config is not valid.
    """
    # always validate before saving
    validate(btctxstore, cfg)

    # Create root path if it doesn't already exist.
    storjnode.util.ensure_path_exists(os.path.dirname(path))

    # Write config to file.
    if password is None:  # unencrypted
        with open(path, 'w') as config_file:
            config_file.write(json.dumps(cfg, indent=2))
            return cfg
    else:
        raise NotImplementedError("encryption not implemented")


def create(btctxstore):
    """Create a config with required values.

    Args:
        btctxstore: btctxstore.BtcTxStore use to create wallet.

    Returns:
        The config as json serializable data.
    """
    hwif = btctxstore.create_wallet()
    default_storage_path = storjnode.storage.manager.DEFAULT_STORE_PATH
    fs_format = storjnode.util.get_fs_type(default_storage_path)
    return {
        "version": VERSION,
        "wallet": {
            "hwif": hwif,
            "cold_storage": [],
        },
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


def validate(btctxstore, cfg):
    """Validate that a config is correct.

    Args:
        btctxstore: btctxstore.BtcTxStore instance used to validate wallet.
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

    # has valid payout address
    for address in cfg["wallet"]["cold_storage"]:
        if not btctxstore.validate_address(address):
            raise ValidationError("Invalid address: {0}".format(address))

    # has valid wallet
    if not btctxstore.validate_wallet(cfg["wallet"]["hwif"]):
        msg = "Invalid hwif entry: {0}!"
        raise ValidationError(msg.format(cfg["wallet"]["hwif"]))

    return True


def get(btctxstore, path, password=None):
    """Load and migarte and existing config if needed, or save a default.

    Args:
        btctxstore: btctxstore.BtcTxStore used to create/validate the wallet.
        path: The path to the config file.
        password: The password for encryption, unencrypted if None.

    Returns:
        The loaded config as json serializable data.

    Raises:
        storjnode.config.Invalid: If loaded config is not valid.
    """

    # load existing config
    if os.path.exists(path):
        cfg = read(path, password=password)

    # create default config if none exists
    else:
        cfg = create(btctxstore)
        cfg = save(btctxstore, path, cfg, password=password)

    # migrate config if needed
    migrated_cfg = migrate(btctxstore, copy.deepcopy(cfg))
    if migrated_cfg["version"] != cfg["version"]:
        cfg = save(btctxstore, path, migrated_cfg, password=password)

    return cfg


def _set_version(btctxstore, cfg, new_version):
    cfg['version'] = new_version
    return cfg


def _migrate_200_to_201(btctxstore, cfg):
    _set_version(btctxstore, cfg, '2.0.1')

    # master_secret -> wallet
    master_secret = cfg['master_secret']
    if master_secret is None:
        raise ValidationError()
    cfg['wallet'] = btctxstore.create_wallet(master_secret=master_secret)

    return cfg


def _migrate_300_to_310(btctxstore, cfg):
    default_storage_path = storjnode.storage.manager.DEFAULT_STORE_PATH
    fs_format = storjnode.util.get_fs_type(default_storage_path)
    return {
        "version": "3.1.0",
        "wallet": {
            "hwif": cfg["wallet"],
            "cold_storage": [cfg["payout_address"]],
        },
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


_MIGRATIONS = {
    "2.0.0": _migrate_200_to_201,
    "2.0.1": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "2.0.2"),
    "2.0.2": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "2.0.3"),
    "2.0.3": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "2.1.0"),
    "2.1.0": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "2.1.1"),
    "2.1.1": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "2.1.2"),
    "2.1.2": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "2.1.3"),
    "2.1.3": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "2.1.4"),
    "2.1.4": lambda btctxstore, cfg: _set_version(btctxstore, cfg, '2.1.5'),
    "2.1.5": lambda btctxstore, cfg: _set_version(btctxstore, cfg, '2.1.6'),
    "2.1.6": lambda btctxstore, cfg: _set_version(btctxstore, cfg, '2.1.7'),
    "2.1.7": lambda btctxstore, cfg: _set_version(btctxstore, cfg, '2.1.8'),
    "2.1.8": lambda btctxstore, cfg: _set_version(btctxstore, cfg, '2.1.9'),
    "2.1.9": lambda btctxstore, cfg: _set_version(btctxstore, cfg, '2.1.10'),
    "2.1.10": lambda btctxstore, cfg: _set_version(btctxstore, cfg, '2.1.11'),
    "2.1.11": lambda btctxstore, cfg: _set_version(btctxstore, cfg, "3.0.0"),
    "3.0.0": _migrate_300_to_310,
}


def migrate(btctxstore, cfg):
    if not isinstance(cfg, dict) or 'version' not in cfg:
        raise ValidationError()

    # migrate until we are at current version
    while cfg['version'] != VERSION:
        cfg = _MIGRATIONS[cfg['version']](btctxstore, cfg)

    return cfg


class ConfigFile:

    def __init__(self, path=None, btctxstore=None, password=None):
        self.path = path or DEFAULT_CONFIG_PATH
        self.btctxstore = btctxstore or BtcTxStore()
        self.password = password
        self.cfg = get(self.btctxstore, self.path, self.password)

    def save(self):
        save(self.btctxstore, self.path, self.cfg, self.password)

    def __getitem__(self, key):
        return self.cfg[key]

    def __setitem__(self, key, value):
        self.cfg[key] = value
        self.save()
