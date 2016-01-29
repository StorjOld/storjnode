from __future__ import unicode_literals

import time

try:
    import itertools.izip as zip  # py2
except ImportError:
    pass

try:
    import itertools.imap as map  # py2
except ImportError:
    pass

import umsgpack
import operator
from itertools import takewhile
from collections import OrderedDict
from zope.interface import implementer
from storjkademlia.storage import IStorage
from threading import RLock


@implementer(IStorage)
class Storage(object):

    def __init__(self, ttl=604800, entry_limit=2048, max_entry_size=512):
        """ In memory forgetful key/value store for DHT.

        Args:
            ttl (int): Number of seconds after which an entry is deleted.
            entry_limit (int): Entries after which the oldest will be deleted.
            max_entry_size (int): Entries above this size are dropped.
        """
        self.mutex = RLock()
        self.data = OrderedDict()
        self.ttl = ttl
        self.entry_limit = entry_limit
        self.max_entry_size = max_entry_size

    def __setitem__(self, key, value):
        with self.mutex:

            # check max entry size
            if len(umsgpack.packb(value)) > self.max_entry_size:
                return

            # write only
            if key in self.data:
                return

            # save entry and cull
            self.data[key] = (time.time(), value)
            self.cull()

    def cull(self):
        with self.mutex:
            # remove entries older than ttl
            for k, v in self.iteritemsOlderThan(self.ttl):
                self.data.popitem(last=False)

            # remove oldest entries untl <= limit
            while len(self.data) > self.entry_limit:
                self.data.popitem(last=False)

    def get(self, key, default=None):
        with self.mutex:
            self.cull()
            if key in self.data:
                return self[key]
            return default

    def __getitem__(self, key):
        with self.mutex:
            self.cull()
            return self.data[key][1]

    def __iter__(self):
        with self.mutex:
            self.cull()
            return iter(self.data)

    def __repr__(self):
        with self.mutex:
            self.cull()
            return repr(self.data)

    def iteritemsOlderThan(self, secondsOld):
        with self.mutex:
            minBirthday = time.time() - secondsOld
            zipped = self._tripleIterable()
            matches = takewhile(lambda r: minBirthday >= r[1], zipped)
            return map(operator.itemgetter(0, 2), matches)

    def _tripleIterable(self):
        with self.mutex:
            ikeys = iter(self.data.keys())
            ibirthday = map(operator.itemgetter(0), iter(self.data.values()))
            ivalues = map(operator.itemgetter(1), iter(self.data.values()))
            return zip(ikeys, ibirthday, ivalues)

    def iteritems(self):
        with self.mutex:
            self.cull()
            ikeys = iter(self.data.keys())
            ivalues = map(operator.itemgetter(1), iter(self.data.values()))
            return zip(ikeys, ivalues)
