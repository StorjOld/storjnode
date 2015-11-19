import os
import copy
import json
from .common import STORJ_HOME


VERSION = "3.0.0"  # config version divorced from software version!
DEFAULT_CONFIG_PATH = os.path.join(STORJ_HOME, "config")


class InvalidConfig(Exception):
    pass


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
    validate(btctxstore, cfg)  # always validate before saving
    if password is None:  # unencrypted
        with open(path, 'w') as config_file:
            config_file.write(json.dumps(cfg))
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
    wif = btctxstore.get_key(hwif)
    address = btctxstore.get_address(wif)
    cfg = {
        "version": VERSION,
        "wallet": hwif,
        "payout_address": address,  # default to wallet address
    }
    return cfg


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

    # is a dict
    if not isinstance(cfg, dict):
        raise InvalidConfig("Config must be a dict!")

    # correct version
    if cfg.get("version") != VERSION:
        msg = "Invalid version: {0} expected, got {1}"
        raise InvalidConfig(msg.format(VERSION, cfg.get("version")))

    # has valid payout address
    if not btctxstore.validate_address(cfg.get("payout_address")):
        raise InvalidConfig("Missing entry 'payout_address'!")

    # has valid wallet
    if not btctxstore.validate_wallet(cfg.get("wallet")):
        msg = "Invalid 'wallet' entry: {0}!"
        raise InvalidConfig(msg.format(cfg.get("wallet")))
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
        raise InvalidConfig()
    cfg['wallet'] = btctxstore.create_wallet(master_secret=master_secret)

    return cfg


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
    # TODO add smarter version ranges so no new line needed for every version
}


def migrate(btctxstore, cfg):
    if not isinstance(cfg, dict) or 'version' not in cfg:
        raise InvalidConfig()

    # migrate until we are at current version
    while cfg['version'] != VERSION:
        cfg = _MIGRATIONS[cfg['version']](btctxstore, cfg)

    return cfg
