
import bz2
from datetime import datetime
import logging
import os
import threading

from namedtuple_with_abc import namedtuple
from umsgpack import loads, dumps, packb, unpackb, Ext
import tzlocal

logger = logging.getLogger()


class MessagePackStorage(object):
    """Store the data in a MessagePack file."""

    def __init__(self, path):
        """Create a new instance.

        Also creates the storage file, if it doesn't exist.

        Args:
            path (str): Where to store the MessagePack data.
        """
        self.path = path
        self.read()

    @property
    def cache(self):
        if getattr(self, "_cache", None) is None:
            with open(self.path, "rb") as f:
                self._cache = loads(bz2.decompress(f.read()),
                                    ext_handlers=unpack_handlers)
            self.changed = False
        return self._cache

    @property
    def all(self):
        return self.cache

    def read(self):
        return self.cache

    def close(self):
        self.write()

    def write(self):
        if self.changed:
            lock = threading.Lock()
            lock.acquire()
            logger.warning("writing to disk...")
            bak_name = "%s.bak" % self.path
            try:
                os.rename(self.path, bak_name)
            except FileExistsError:
                tz = tzlocal.get_localzone()
                t = os.path.getmtime(bak_name)
                t = tz.localize(datetime.fromtimestamp(t))
                t_name = t.strftime("%Y_%m_%d_%Hh%Mm%Ss")
                os.rename(bak_name, t_name)
                os.rename(self.path, bak_name)
            with open(self.path, "wb") as f:
                f.write(bz2.compress(dumps(self.cache,
                                     ext_handlers=pack_handlers)))
            os.remove(bak_name)
            logger.warning("done writing to disk")
            lock.release()
        self.changed = False

    def insert(self, data):
        self.changed = True
        self.cache.add(data)


class Show(namedtuple.abc):

    _fields = ('name', 'id', 'season', 'episode', 'release', 'magnet',
               'torrents', 'size_mb')

    def __new__(
        cls, name, id, season=None, episode=None, release=None, magnet=None,
        torrents=None, size_mb=None
    ):
        obj = super().__new__(
            cls, name, id, season, episode, release, magnet, torrents, size_mb
        )
        return obj

    def __getitem__(self, key):
        for k, v in zip(self._fields, self):
            if k == key:
                return v
        raise KeyError(key)

Show_type = 1
set_type = 2


def pack_Show(obj):
    return Ext(Show_type,
               packb(obj._asdict()))


def pack_set(obj):
    return Ext(set_type,
               packb(list(obj)))


def unpack_Show(ext):
    data = unpackb(ext.data)
    return Show(**data)


def unpack_set(ext):
    data = (Show(*d) for d in unpackb(ext.data))
    return set(data)


def clean_torrents(d):
    torrents = d['torrents']
    d['torrents'] = torrents[0] if torrents else None
    return d


pack_handlers = {Show: pack_Show, set: pack_set}
unpack_handlers = {Show_type: unpack_Show, set_type: unpack_set}

if __name__ == '__main__':
    """
    db = MessagePackStorage('tiny.bz2msgpack')
    for item in db.all:
        print(item["name"])
        exit()
    """
    s = Show(name="Lost", id=666)
    print(s)
