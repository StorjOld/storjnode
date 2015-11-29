# import this first in scripts to init loggin
import sys  # NOQA
import logging  # NOQA
from twisted.python import log as _log


FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d: %(message)s"
LEVEL_DEFAULT = logging.INFO
LEVEL_QUIET = 60
LEVEL_VERBOSE = logging.DEBUG


# make twisted use standard library logging module
observer = _log.PythonLoggingObserver()  # pragma: no cover
observer.start()  # pragma: no cover


# silence global logger
logging.basicConfig(format=FORMAT, level=LEVEL_QUIET)
base_logger = logging.getLogger()


def getLogger(*args, **kwargs):
    child = base_logger.getChild(*args, **kwargs)

    # full logging if --debug or --verbose arg given
    if "--debug" in sys.argv or "--verbose" in sys.argv:
        child.setLevel(LEVEL_VERBOSE)  # pragma: no cover

    # no logging if --quite arg given
    elif "--quiet" in sys.argv:
        child.setLevel(LEVEL_QUIET)  # pragma: no cover

    # default to info
    else:
        child.setLevel(LEVEL_DEFAULT)  # pragma: no cover

    return child
