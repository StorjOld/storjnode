# override storjnode log and set level to DEBUG for unittests
import logging  # NOQA
FORMAT = "%(asctime)s %(levelname)s %(name)s %(lineno)d: %(message)s"
logging.basicConfig(format=FORMAT, level=logging.DEBUG)


from . util import *  # NOQA
from . storage import *  # NOQA
from . network import *  # NOQA


if __name__ == "__main__":
    unittest.main()
