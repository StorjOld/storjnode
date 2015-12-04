# import this first in scripts to init loggin
import sys  # NOQA
import logging as _logging
from twisted.python import log as _log


FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d: %(message)s"
LEVEL_DEFAULT = _logging.INFO
LEVEL_QUIET = 60
LEVEL_VERBOSE = _logging.DEBUG


# make twisted use standard library logging module
_observer = _log.PythonLoggingObserver()  # pragma: no cover
_observer.start()  # pragma: no cover


# silence global logger
_logging.basicConfig(format=FORMAT, level=LEVEL_QUIET)
_base_logger = _logging.getLogger()


def getLogger(*args, **kwargs):
    if not args and not kwargs:
        child = _base_logger.getChild("default")
    else:
        child = _base_logger.getChild(*args, **kwargs)

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


# XXX to maintain compatibility with a previous version
logging = getLogger()
logging.getLogger = getLogger
