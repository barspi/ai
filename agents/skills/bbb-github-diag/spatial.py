#!/usr/bin/env python3
"""Spatial index of a route.Scene: a uniform grid of square tiles (a bucket grid, also called spatial hashing), so that a question
about one place (does a label here touch anything? which obstacles fall in this search window?) looks only at what is near it.

usage: spatial.py selftest

Every item goes into each tile its bounding box meets; a query collects the items of the tiles its box meets and keeps those whose box
really meets it. Tiles are TILE px square: about one label wide, so a label query reads one to four tiles.

Staying in step with the scene. A scene's lists are Tracked: a list that counts every change other than an append at its end (a
modification counter, like java.util.ArrayList.modCount). A Layer indexes one such list: on each use it adds the items appended since
its last use, and indexes the whole list again only when the counter moved (an item removed, replaced or inserted) or the scene was
given a new list. So the index never holds a stale entry, and the common change, an arrow or a label added, costs one insertion.
Items are frozen on the way in (a box or a label as a tuple, a path as a tuple of points), so nothing can change under the index.
"""
import itertools, sys

TILE = 128                                        # px; about one label wide


def freeze_rect(r):
    return tuple(float(v) for v in r)


def freeze_path(pts):
    return tuple((float(x), float(y)) for x, y in pts)


class Tracked(list):
    """A list whose `edits` counts every change but an append or extend at its end; items are frozen by `freeze` on the way in."""

    def __init__(self, items=(), freeze=freeze_rect):
        self.freeze, self.edits = freeze, 0
        super().__init__(map(freeze, items))

    def append(self, x):
        super().append(self.freeze(x))

    def extend(self, xs):
        super().extend(map(self.freeze, xs))

    def __iadd__(self, xs):
        self.extend(xs)
        return self

    def insert(self, i, x):
        self.edits += 1
        super().insert(i, self.freeze(x))

    def __setitem__(self, i, x):
        self.edits += 1
        super().__setitem__(i, [self.freeze(v) for v in x] if isinstance(i, slice) else self.freeze(x))

    def __delitem__(self, i):
        self.edits += 1
        super().__delitem__(i)

    def pop(self, i=-1):
        self.edits += 1
        return super().pop(i)

    def remove(self, x):
        self.edits += 1
        super().remove(self.freeze(x))

    def clear(self):
        self.edits += 1
        super().clear()

    def sort(self, *a, **k):
        self.edits += 1
        super().sort(*a, **k)

    def reverse(self):
        self.edits += 1
        super().reverse()


class TrackedDict(dict):
    """A dict whose `edits` counts every change (boxes change seldom: any change indexes them again); values frozen as rectangles."""

    def __init__(self, items=()):
        self.edits = 0
        super().__init__((k, freeze_rect(v)) for k, v in dict(items).items())

    def __setitem__(self, k, v):
        self.edits += 1
        super().__setitem__(k, freeze_rect(v))

    def __delitem__(self, k):
        self.edits += 1
        super().__delitem__(k)

    def pop(self, *a):
        self.edits += 1
        return super().pop(*a)

    def popitem(self):
        self.edits += 1
        return super().popitem()

    def clear(self):
        self.edits += 1
        super().clear()

    def update(self, *a, **k):
        self.edits += 1
        for key, v in dict(*a, **k).items():
            super().__setitem__(key, freeze_rect(v))

    def setdefault(self, k, v=None):
        if k not in self:
            self[k] = v
        return self[k]


class TrackedAttr:
    """A Scene attribute that always holds a Tracked list (or a TrackedDict): a plain list assigned to it is wrapped, so a caller
    that replaces the list (sc.labels = [...]) is seen by the index too."""

    def __init__(self, freeze=None):
        self.freeze = freeze                       # None: a TrackedDict

    def __set_name__(self, owner, name):
        self.slot = '_' + name

    def __get__(self, obj, owner=None):
        return self if obj is None else getattr(obj, self.slot)

    def __set__(self, obj, value):
        setattr(obj, self.slot, TrackedDict(value) if self.freeze is None else Tracked(value, self.freeze))


def _meets(a, b):
    """Do the closed boxes a and b (x0, y0, x1, y1) meet?"""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


class Grid:
    """Items with a bounding box (x0, y0, x1, y1) in square tiles. query() returns the payloads of the items whose box meets the
    query box, in the order they were added."""

    def __init__(self, tile=TILE):
        self.tile, self.cells, self.items = tile, {}, []

    def _tiles(self, box):
        t = self.tile
        return itertools.product(range(int(box[0] // t), int(box[2] // t) + 1), range(int(box[1] // t), int(box[3] // t) + 1))

    def add(self, box, payload):
        k = len(self.items)
        self.items.append((box, payload))
        for cell in self._tiles(box):
            self.cells.setdefault(cell, []).append(k)

    def query(self, box):
        ks = set()
        for cell in self._tiles(box):
            ks.update(self.cells.get(cell, ()))
        return [self.items[k][1] for k in sorted(ks) if _meets(self.items[k][0], box)]


class Layer:
    """One Tracked source (a list, or a TrackedDict's items) in a Grid, kept in step with it (module docstring). entries(item) gives
    the [(box, payload)] of one item."""

    def __init__(self, entries):
        self.entries, self.src, self.edits, self.n, self.grid = entries, None, -1, 0, Grid()
        self.rebuilds = 0                          # how often the whole source was indexed again (selftest reads it)

    def sync(self, src):
        if src is not self.src or src.edits != self.edits or len(src) < self.n:
            self.src, self.edits, self.n, self.grid = src, src.edits, 0, Grid()
            self.rebuilds += 1
        items = list(src.items()) if isinstance(src, dict) else src
        for item in items[self.n:]:
            for box, payload in self.entries(item):
                self.grid.add(box, payload)
        self.n = len(items)
        return self.grid


def selftest():
    """The index answers like a full scan, after appends, in-place edits and a replaced list; an append never re-indexes."""
    import random
    bad = []
    rnd = random.Random(1)

    def rects(n):
        return [(rnd.uniform(0, 3000), rnd.uniform(0, 3000), rnd.uniform(5, 400), rnd.uniform(5, 60)) for _ in range(n)]

    def entries(r):
        return [((r[0], r[1], r[0] + r[2], r[1] + r[3]), r)]

    src = Tracked(rects(300))
    layer = Layer(entries)

    def agree(what):
        for _ in range(200):
            x, y = rnd.uniform(-100, 3100), rnd.uniform(-100, 3100)
            q = (x, y, x + rnd.uniform(0, 300), y + rnd.uniform(0, 300))
            want = [r for r in src if _meets((r[0], r[1], r[0] + r[2], r[1] + r[3]), q)]
            if layer.sync(src).query(q) != want:
                bad.append(what)
                return
    agree('first build')
    src.append((10, 10, 50, 18))
    src.extend(rects(5))
    agree('after appends')
    if layer.rebuilds != 1:
        bad.append('an append indexed the list again (%d builds)' % layer.rebuilds)
    src[3] = (2000, 2000, 70, 18)
    agree('after an item was replaced')
    src.pop(7)
    agree('after a pop')
    src2 = Tracked(rects(50))
    src = src2
    agree('a new list')
    d = TrackedDict({1: (0, 0, 10, 10)})
    dl = Layer(lambda kv: [((kv[1][0], kv[1][1], kv[1][0] + kv[1][2], kv[1][1] + kv[1][3]), kv[0])])
    d[2] = (100, 100, 10, 10)
    if dl.sync(d).query((95, 95, 105, 105)) != [2]:
        bad.append('a box added to a TrackedDict')
    del d[2]
    if dl.sync(d).query((95, 95, 105, 105)) != []:
        bad.append('a box deleted from a TrackedDict')
    print('spatial self-test: %s' % ('OK' if not bad else 'FAILED: ' + '; '.join(bad)))
    return not bad


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        sys.exit(0 if selftest() else 1)
    sys.exit(__doc__)
