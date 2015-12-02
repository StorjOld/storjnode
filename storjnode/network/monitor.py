import storjnode


_log = storjnode.log.getLogger(__name__)


class _Monitor(object):  # will not scale but good for now

    def __init__(self, storjnode, worker_num=32):
        pass


def run(storjnode, worker_num=32):
    return _Monitor(storjnode, worker_num=worker_num).crawl()
