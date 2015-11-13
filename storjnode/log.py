# import this first in scripts to init loggin

# make twisted use standard library logging module
from twisted.python import log as _log
_observer = _log.PythonLoggingObserver()
_observer.start()

# setup standard logging module
import sys  # NOQA
import logging  # NOQA


FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d: %(message)s"


# full logging if --debug or --verbose arg given
if "--debug" in sys.argv or "--verbose" in sys.argv:
    logging.basicConfig(format=FORMAT, level=logging.DEBUG)  # pragma: no cover

# no logging if --quite arg given
elif "--quiet" in sys.argv:
    logging.basicConfig(format=FORMAT, level=60)  # pragma: no cover

# default to warning
else:
    logging.basicConfig(format=FORMAT, level=logging.WARNING)
