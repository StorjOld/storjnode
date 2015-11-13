# import this first in scripts to init loggin

# make twisted use standard library logging module
from twisted.python import log as _log
_observer = _log.PythonLoggingObserver()
_observer.start()

# setup standard logging module
import sys  # NOQA
import logging  # NOQA

FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d: %(message)s"
if "--debug" in sys.argv:  # debug shows everything
    logging.basicConfig(format=FORMAT, level=logging.DEBUG)  # pragma: no cover
elif "--quiet" in sys.argv:  # quiet disables logging
    logging.basicConfig(format=FORMAT, level=60)  # pragma: no cover
else:  # default
    logging.basicConfig(format=FORMAT, level=logging.WARNING)
