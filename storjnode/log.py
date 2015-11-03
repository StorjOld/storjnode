# import this first in scripts to init logging correctly

# make twisted use standard library logging module
from twisted.python import log as _log
_observer = _log.PythonLoggingObserver()
_observer.start()

# setup standard logging module
import sys
import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d: %(message)s"
if "--debug" in sys.argv:  # debug shows everything
    logging.basicConfig(format=_LOG_FORMAT, level=logging.DEBUG)
elif "--quiet" in sys.argv:  # quiet disables logging
    logging.basicConfig(format=_LOG_FORMAT, level=60)
else:  # default
    logging.basicConfig(format=_LOG_FORMAT, level=logging.WARNING)
