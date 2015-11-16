# import this first in scripts to init loggin
import sys  # NOQA
import logging  # NOQA
from twisted.python import log as _log


# make twisted use standard library logging module
_observer = _log.PythonLoggingObserver()  # pragma: no cover
_observer.start()  # pragma: no cover


# setup standard logging module
FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d: %(message)s"
LEVEL_DEFAULT = logging.WARNING
LEVEL_QUIET = 60
LEVEL_VERBOSE = logging.DEBUG


# full logging if --debug or --verbose arg given
if "--debug" in sys.argv or "--verbose" in sys.argv:
    logging.basicConfig(format=FORMAT, level=LEVEL_VERBOSE)  # pragma: no cover

# no logging if --quite arg given
elif "--quiet" in sys.argv:
    logging.basicConfig(format=FORMAT, level=LEVEL_QUIET)  # pragma: no cover

# default to info
else:
    logging.basicConfig(format=FORMAT, level=LEVEL_DEFAULT)  # pragma: no cover
