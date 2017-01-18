"""Namedtuple with ABC.

* named tuple mix-in + ABC (abstract base class) recipe,
* works under Python 3.x.

Original available at:
    https://code.activestate.com/
    recipes/577629-namedtupleabc-abstract-base-class-mix-in-for-named/
"""

import collections
from abc import ABCMeta, abstractproperty
from functools import wraps

__all__ = ('namedtuple', 'ntuple_from_dict',)
_namedtuple = collections.namedtuple


def ntuple_from_dict(d):
    """Create a named tuple from a dictionary."""
    return namedtuple('TupleFromDict', d.keys())(**d)


class _NamedTupleABCMeta(ABCMeta):
    """The metaclass for the abstract base class + mix-in for named tuples."""

    def __new__(cls, name, bases, namespace):
        """..."""
        fields = namespace.get('_fields')
        for base in bases:
            if fields is not None:
                break
            fields = getattr(base, '_fields', None)
        if not isinstance(fields, abstractproperty):
            basetuple = _namedtuple(name, fields)
            bases = (basetuple,) + bases
            namespace.pop('_fields', None)
            namespace.setdefault('__doc__', basetuple.__doc__)
            namespace.setdefault('__slots__', ())
        return ABCMeta.__new__(cls, name, bases, namespace)


class _NamedTupleABC(metaclass=_NamedTupleABCMeta):
    """The abstract base class + mix-in for named tuples."""

    _fields = abstractproperty()


_namedtuple.abc = _NamedTupleABC
# _NamedTupleABC.register(type(version_info))
# (and similar, in the future...)


@wraps(_namedtuple)
def namedtuple(*args, **kwargs):
    """Named tuple factory with namedtuple.abc subclass registration."""
    cls = _namedtuple(*args, **kwargs)
    _NamedTupleABC.register(cls)
    return cls

collections.namedtuple = namedtuple


class IndexableTuple(namedtuple.abc):

    def __getitem__(self, key):
        for k, v in zip(self._fields, self):
            if k == key:
                return v
        raise KeyError(key)

    def __getattr__(self, key):
        return self.__getitem__(key)

if __name__ == '__main__':
    class XX(namedtuple.abc):

        _fields = ("name", "id")

        def __getitem__(self, key):
            for k, v in zip(self._fields, self):
                if k == key:
                    return v
            raise KeyError(key)

    xx = XX("la", 25)
    # print(xx["name"])
    print(xx.name)
