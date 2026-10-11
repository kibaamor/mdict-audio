from pathlib import Path


class RecordStore:
    def __init__(self, path):
        self.path = Path(path)
        self._f = None

    def __enter__(self):
        if self._f is None:
            self._f = self.path.open("rb")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        if self._f is not None:
            self._f.close()
            self._f = None

    def read(self, offset, length):
        if self._f is not None:
            return self._read_from(self._f, offset, length)
        with self.path.open("rb") as f:
            return self._read_from(f, offset, length)

    def _read_from(self, f, offset, length):
        f.seek(offset)
        data = f.read(length)
        if len(data) != length:
            raise RuntimeError("record store truncated at offset %d" % offset)
        return data


class RecordStoreWriter:
    def __init__(self, path):
        self.path = Path(path)
        self._f = self.path.open("wb")
        self._offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def append(self, data):
        if self._f is None:
            raise RuntimeError("record store writer is closed")
        offset = self._offset
        self._f.write(data)
        self._offset += len(data)
        return offset, len(data)

    def close(self):
        if self._f is not None:
            self._f.close()
            self._f = None
