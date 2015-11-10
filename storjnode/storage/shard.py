import hashlib


class Shard(object):

    def __init__(self, fobj):
        self._fobj = fobj
        self._cached_id = None

    def get_size(self):
        self._fobj.seek(0, 2)
        return self._fobj.tell()

    def get_id(self):
        if self._cached_id is not None:
            self._cached_id
        self._cached_id = self.get_hash()
        return self._cached_id

    def _get_chunks(self, limit):
        size = self.get_size()
        return [limit] * (size // limit) + [size % limit]

    def get_hash(self, seed=None):
        hasher = hashlib.sha256()

        # seed hash if requested
        if seed is not None:
            hasher.update(seed)

        # hash file
        chunks = self._get_chunks(1024 * 1024 * 8)  # hash in 8mb chunks
        self._fobj.seek(0)
        for chunk_size in chunks:
            hasher.update(self._fobj.read(chunk_size))
        return hasher.hexdigest()

    def write_to(self, fobj):
        chunks = self._get_chunks(1024 * 1024 * 8)  # write in 8mb chunks
        self._fobj.seek(0)
        for chunk_size in chunks:
            fobj.write(self._fobj.read(chunk_size))

    def save(self, path):
        with open(path, "wb") as fobj:
            self.write_to(fobj)

    def close(self):
        self._fobj.close()
