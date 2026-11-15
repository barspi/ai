#!/usr/bin/env python3
"""Arrow search on an orthogonal visibility graph: the `vis` router of route.py (BBB_ROUTER=vis, the default).

usage: ovg.py selftest      both routers on random scenes: the same cost for every arrow (selftest.py runs it)

The technique is the orthogonal visibility graph of Wybrow, Marriott and Stuckey ("Orthogonal Connector Routing", GD 2009), as in the
libavoid router of Adaptagrams: nodes only where a path may have to turn, edges along the free stretches between them, and A* over
(node, direction). The cost model and every rule are route.py's (see its docstring); only the search is different. Both searches work
on the same 5px lattice (route._window) and find paths of the same cost. Their points are the same too, except where two paths tie:
the heap order differs, so a tie can go the other way.

Why the sparse graph loses nothing. Slide one straight stretch of a path sideways by one lattice step: its two neighbours grow or
shrink by one step each, and the cost changes by the same amount at every step, until the stretch or one of its two bends meets the
edge of a feature (route.py's obstacle layers: a box or a label, a band beside another arrow or a frame border, a zone where a turn is
not allowed, a band where a vertical step costs NEAR_COST) or the window edge. Crossings and frame borders are not such edges. A
crossing appears or disappears in two ways only: a bend slides across the crossed line, but a bend is never allowed near a line or a
frame border (each has a no-turn band, at least 1.5 steps wide on either side); or the stretch slides past an end of the line, but
the END_CLEAR cells (for a frame, its blocked corners) stop it before. So some cheapest path has every stretch on a candidate line:
just outside the edge of a feature (on both sides of a NEAR band, where the cost per step changes), on a goal's line, or on the window
edge; and the stretch lies in a run of free cells of that line that meets the feature's extent (the stretch itself, or the bend at
its end, touches the feature). The search stops at the points where a candidate run meets the line it travels on (and where a turn is
allowed), and nowhere else; it turns only there. This needs the no-turn bands as wide as the assert below says, and a no-turn band
wherever a band forbids running along a line (the features below always come in such pairs).

Structures. The features of the scene's labels, pills and arrows, in canvas px, live in the scene's spatial index (spatial.py, one per
Scene, kept in step with it); a call asks only for those that fall in its window. Per call, _Lattice: the
window, the features on its lattice (with the call's own: its two boxes, which keep OWN_BOXM instead of BOXM, the frames, whose border
cost depends on whether they hold an end, the no-turn zones round the two boxes, the outside of the frame for an `inside` search),
and, built when the search first reaches them, per row and per column: the cells a step may not enter, the crossing and frame costs,
the NEAR cells, the cells where no turn is allowed, and the candidate runs. The lattice moves with the window, as the grid search's
does, so that the two can be compared: that is why nothing below the spatial index outlives a call.

The heuristic: Manhattan steps to the nearest goal side, plus TURN_COST for each bend that any path from that point and direction to
that side must make, plus the side's cost. It never overestimates and it is consistent, so the first goal taken from the queue is a
cheapest one.
"""
import heapq, itertools, math, os, random, sys, time
from bisect import bisect_left, bisect_right

import route as R

G = R.G
assert min(R.HARD_H, R.HARD_V, R.FPROX) > 1.5 * G and R.END_CLEAR >= G, 'the candidate lines (module docstring) need these'
BLK, NOH, NOV, NT, NEAR, CRH, CRV, FRH, FRV = range(9)
# BLK: no step may enter the cell; NOH, NOV: no horizontal, no vertical step may enter; NT: no turn there; NEAR: a vertical step into
# it costs NEAR_COST; CRH, CRV: a vertical (horizontal) step into it crosses a line, CROSS_COST; FRH, FRV: a vertical (horizontal)
# step into it crosses a frame border, at the border's cost.
RECT, HLINE, VLINE = range(3)
# A feature in canvas px is (kind, shape, p, q, r, s, value): a RECT (x0, y0, x1, y1) covers the lattice points strictly inside it;
# an HLINE (y, x0, x1, -) the points of the lattice row nearest y strictly between x0 and x1; a VLINE (x, y0, y1, -) likewise.
# On the lattice of one call it becomes (kind, i1, i2, j1, j2, value): the points i1..i2 across, j1..j2 down.
# A line along a row (axis 0) holds horizontal steps, a column (axis 1) vertical ones; per axis: the kind that stops a step along it
# (besides BLK), the kind of line it crosses, of frame border, and the kind that costs per step (none along a row).
STOP, CROSS, FRAME, PER_STEP = (NOH, NOV), (CRV, CRH), (FRV, FRH), (None, NEAR)
BUCKET = 16                                      # lattice lines per bucket of the per-call feature lists
MAX_ALTERNATIVES = 12                            # search_paths: at most this many searches (the first and the alternatives)
PEN_STEP = 2                                     # a step along a stretch of a path found before costs this much more
PEN_BAND = 4                                     # lattice lines (20px) each side of such a stretch: about a label's half height and gap


def _feature_box(f):
    """The bounding box in px of a feature (kind, shape, p, q, r, s, value)."""
    _, shape, p, q, r, s, _ = f
    return (p, q, r, s) if shape == RECT else (q, p, r, p) if shape == HLINE else (p, q, p, r)


def scene_features(sc, box):
    """The features of the scene's labels, pills and arrows whose bounding box meets box (x0, y0, x1, y1), from the scene's spatial
    index (route.Scene.layer): built once per scene, brought up to date as arrows and labels are added."""
    return itertools.chain.from_iterable(
        sc.layer(('ovg', name), name, lambda item, make=make: [(_feature_box(f), f) for f in make(item)]).query(box)
        for name, make in _SOURCES.items())


def _label(r):
    x, y, w, h = r
    return [(BLK, RECT, x - R.LABM, y - R.LABM, x + w + R.LABM, y + h + R.LABM, 1)]


def _pill(r):
    x, y, w, h = r
    return [(BLK, RECT, x, y, x + w, y + h, 1)]


def _arrow(pts):
    """Another horizontal stretch keeps HARD_H, a vertical one HARD_V (and pays NEAR_COST closer than LABEL_ROOM); a step across the
    line pays CROSS_COST, and no crossing comes within END_CLEAR of either end of the line."""
    out = []
    for o, c, lo, hi in R.segments(pts):
        if o == 'h':
            band = (lo - R.HARD_H, c - R.HARD_H, hi + R.HARD_H, c + R.HARD_H)
            out += [(NOH, RECT) + band + (1,), (NT, RECT) + band + (1,), (CRH, HLINE, c, lo, hi, 0, 1)]
        else:
            band = (c - R.HARD_V, lo - R.HARD_V, c + R.HARD_V, hi + R.HARD_V)
            out += [(NOV, RECT) + band + (1,), (NT, RECT) + band + (1,), (NEAR, RECT, c - R.LABEL_ROOM, lo, c + R.LABEL_ROOM, hi, 1),
                    (CRV, VLINE, c, lo, hi, 0, 1)]
        shape = HLINE if o == 'h' else VLINE
        out += [(BLK, shape, c, end - R.END_CLEAR, end + R.END_CLEAR, 0, 1) for end in (lo, hi)]
    return out


_SOURCES = {'labels': _label, 'pills': _pill, 'arrows': _arrow}


def _call_features(sc, a, b, inside, window):
    """The features that depend on the arrow being routed: the boxes (its own two keep OWN_BOXM, the others BOXM), the frames (a
    border keeps FPROX and costs FRAME_OWN_COST when the frame holds an end, FRAME_COST otherwise; corners are blocked), the outside of
    the frame of an `inside` search, and the no-turn zones round its two boxes. Frames come in the grid search's order: where two
    borders share lattice points, the later one's cost holds, as there."""
    ra, rb = sc.boxes[a], sc.boxes[b]
    out = []
    for n, (x, y, w, h) in sc.boxes.items():
        m = R.OWN_BOXM if n in (a, b) else R.BOXM
        out.append((BLK, RECT, x - m, y - m, x + w + m, y + h + m, 1))
    f = R.FPROX
    for fr in sc.frames:
        x, y, w, h = fr
        fc = R.FRAME_OWN_COST if R.holds(fr, ra) or R.holds(fr, rb) else R.FRAME_COST
        for c in (y, y + h):
            out += [(NOH, RECT, x - f, c - f, x + w + f, c + f, 1), (NT, RECT, x - f, c - f, x + w + f, c + f, 1),
                    (FRH, HLINE, c, x, x + w, 0, fc)]
        for c in (x, x + w):
            out += [(NOV, RECT, c - f, y - f, c + f, y + h + f, 1), (NT, RECT, c - f, y - f, c + f, y + h + f, 1),
                    (FRV, VLINE, c, y, y + h, 0, fc)]
        out += [(BLK, RECT, cx - f, cy - f, cx + f, cy + f, 1) for cx in (x, x + w) for cy in (y, y + h)]
    if inside:                                   # stay in the common frame: everything outside it is blocked
        x0, y0, x1, y1 = window
        fx, fy, fw, fh = inside
        wall = R.FRAME_WALL
        out += [(BLK, RECT, x0 - G, y0 - G, fx + wall, y1 + G, 1), (BLK, RECT, fx + fw - wall, y0 - G, x1 + G, y1 + G, 1),
                (BLK, RECT, x0 - G, y0 - G, x1 + G, fy + wall, 1), (BLK, RECT, x0 - G, fy + fh - wall, x1 + G, y1 + G, 1)]
    t = R.TURN_FREE                              # leave and enter a box straight
    out += [(NT, RECT, x - t, y - t, x + w + t, y + h + t, 1) for x, y, w, h in (ra, rb)]
    return out


def _span(lo, hi, o, n):
    """Lattice indices k, 0 <= k < n, with lo < o + k * G < hi (rng() of route._route_grid)."""
    return max(0, int(math.floor((lo - o) / G)) + 1), min(n - 1, int(math.ceil((hi - o) / G)) - 1)


def _merge(ivs):
    """Sorted, disjoint (starts, ends) of the union of closed integer intervals."""
    starts, ends = [], []
    for s, e in sorted(ivs):
        if ends and s <= ends[-1] + 1:
            ends[-1] = max(ends[-1], e)
        else:
            starts.append(s)
            ends.append(e)
    return starts, ends


def _holds_at(ivs, p):
    k = bisect_right(ivs[0], p) - 1
    return k >= 0 and ivs[1][k] >= p


class _Line:
    """One lattice row (axis 0) or column (axis 1) of a call, seen by a step along it: positions are columns on a row, rows on a column.
    stop, turnless, near, runs: (starts, ends) of disjoint intervals; cross: sorted positions; frame_at: sorted positions of frame
    border cells and frame_sum the running sum of their costs."""
    __slots__ = ('stop', 'turnless', 'cross', 'frame_at', 'frame_sum', 'near', 'runs')

    def __init__(self, stop, turnless, cross, frame_at, frame_sum, near, runs):
        self.stop, self.turnless, self.cross, self.near, self.runs = stop, turnless, cross, near, runs
        self.frame_at, self.frame_sum = frame_at, frame_sum

    def reach(self, p, step, n):
        """The farthest position from p, going `step` (1 or -1), that a stretch reaches with no stopped cell entered."""
        s, e = self.stop
        if step > 0:
            k = bisect_left(e, p + 1)
            return p if k < len(s) and s[k] <= p + 1 else (s[k] - 1 if k < len(s) else n - 1)
        k = bisect_right(s, p - 1) - 1
        return p if k >= 0 and e[k] >= p - 1 else (e[k] + 1 if k >= 0 else 0)

    def cost(self, lo, hi):
        """The cost of entering the cells lo..hi: a step each, the crossings, the frame borders and the NEAR cells."""
        c = hi - lo + 1 + R.CROSS_COST * (bisect_right(self.cross, hi) - bisect_left(self.cross, lo))
        c += self.frame_sum[bisect_right(self.frame_at, hi)] - self.frame_sum[bisect_left(self.frame_at, lo)]
        s, e = self.near
        for k in range(max(0, bisect_right(s, lo) - 1), bisect_right(s, hi)):
            c += R.NEAR_COST * max(0, min(e[k], hi) - max(s[k], lo) + 1)
        return c


class _Lattice:
    """The window of one call, its lattice and its features (module docstring). Use: free() while the ends are chosen, then
    set_goals() once, then go(); rows and columns are built when first asked for."""

    def __init__(self, sc, a, b, pad, inside):
        ra, rb = sc.boxes[a], sc.boxes[b]
        self.x0, self.y0, x1, y1, self.NX, self.NY = R._window(sc, ra, rb, pad, inside)
        self.px = (self.x0, self.y0, self.x0 + (self.NX - 1) * G, self.y0 + (self.NY - 1) * G)   # the lattice's extent in px
        near = scene_features(sc, (self.px[0] - G, self.px[1] - G, self.px[2] + G, self.px[3] + G))
        feats = [f for f in map(self._on_lattice, itertools.chain(near, _call_features(sc, a, b, inside, (self.x0, self.y0, x1, y1)))) if f]
        self.n = (self.NX, self.NY)              # positions along a row, along a column
        self.buckets = ({}, {})                  # per axis: bucket of BUCKET rows (columns) -> the features that reach into it
        for f in feats:
            for axis, (lo, hi) in enumerate(((f[3], f[4]), (f[1], f[2]))):
                for k in range(lo // BUCKET, hi // BUCKET + 1):
                    self.buckets[axis].setdefault(k, []).append(f)
        self.gen = self._generators(feats)
        self.goals = {}
        self.covering, self.blocked, self.lines = ({}, {}), ({}, {}), ({}, {})   # per axis, line -> its features, BLK, _Line
        self.edges = {}                          # search state -> go()
        self.build_secs = self.search_secs = 0.0  # seconds spent building rows and columns, and in _astar less those

    def _on_lattice(self, f):
        """The feature on this call's lattice, or None when it covers no lattice point. A quick test in px comes first: most features
        of a scene lie outside a small window."""
        kind, shape, p, q, r, s, value = f
        x0, y0, x1, y1 = self.px
        if shape == RECT:
            if r <= x0 or p >= x1 or s <= y0 or q >= y1:
                return None
            (i1, i2), (j1, j2) = _span(p, r, x0, self.NX), _span(q, s, y0, self.NY)
        elif shape == HLINE:                     # the row nearest the line; round() as route.py, half to even
            if r <= x0 or q >= x1 or not y0 - G <= p <= y1 + G:
                return None
            j1 = j2 = int(round((p - y0) / G))
            i1, i2 = _span(q, r, x0, self.NX)
        else:
            if r <= y0 or q >= y1 or not x0 - G <= p <= x1 + G:
                return None
            i1 = i2 = int(round((p - x0) / G))
            j1, j2 = _span(q, r, y0, self.NY)
        if 0 <= i1 <= i2 < self.NX and 0 <= j1 <= j2 < self.NY:
            return kind, i1, i2, j1, j2, value
        return None

    def _generators(self, feats):
        """Per axis, {line: [extent]}: the candidate lines (module docstring) and the extent each must meet, across that line.
        A row next to a feature's top or bottom edge must meet the feature's columns, and the reverse; the window edges are candidates
        everywhere. A NEAR band adds the lines just inside its edges too (its cost per step changes there, not its feasibility)."""
        rows, cols = {}, {}
        for kind, i1, i2, j1, j2, _ in feats:
            if kind in (BLK, NOH, NOV, NT):
                across, down = (i1 - 1, i2 + 1), (j1 - 1, j2 + 1)
            elif kind == NEAR:
                across, down = (i1 - 1, i1, i2, i2 + 1), (j1 - 1, j1, j2, j2 + 1)
            else:
                continue
            for i in across:
                if 0 <= i < self.NX:
                    cols.setdefault(i, []).append((j1, j2))
            for j in down:
                if 0 <= j < self.NY:
                    rows.setdefault(j, []).append((i1, i2))
        for i in (0, self.NX - 1):
            cols.setdefault(i, []).append((0, self.NY - 1))
        for j in (0, self.NY - 1):
            rows.setdefault(j, []).append((0, self.NX - 1))
        return rows, cols

    def set_goals(self, goals):
        """Goals {(i, j): {direction: side cost}}: a goal point is a stop for a stretch that enters the box from it, and its last
        stretch's line is a candidate. (Goal points are never blocked: route._ends picks free ones. The grid search's exception for
        a blocked goal cell never applies, and there is none here.)"""
        self.goals = goals
        for (i, j), ds in goals.items():
            for d in ds:
                if d & 1:                        # entered going down or up: the last stretch is on column i
                    self.gen[1].setdefault(i, []).append((j, j))
                    self.gen[0].setdefault(j, [])
                else:
                    self.gen[0].setdefault(j, []).append((i, i))
                    self.gen[1].setdefault(i, [])
        self.cands = tuple(sorted(g) for g in self.gen)    # per axis, the candidate lines in order

    def _features_on(self, axis, k):
        """(kind, start, end, value) of every feature on line k of axis, start..end along it."""
        out = self.covering[axis].get(k)
        if out is None:
            bucket = self.buckets[axis].get(k // BUCKET, ())
            if axis == 0:
                out = [(kind, i1, i2, v) for kind, i1, i2, j1, j2, v in bucket if j1 <= k <= j2]
            else:
                out = [(kind, j1, j2, v) for kind, i1, i2, j1, j2, v in bucket if i1 <= k <= i2]
            self.covering[axis][k] = out
        return out

    def free(self, i, j):
        """May a path start or end at (i, j)? (route._ends asks it.)"""
        ivs = self.blocked[0].get(j)
        if ivs is None:
            ivs = self.blocked[0][j] = _merge([(s, e) for kind, s, e, _ in self._features_on(0, j) if kind == BLK])
        return not _holds_at(ivs, i)

    def line(self, axis, k):
        """The _Line of row k (axis 0) or column k (axis 1), built on the first call."""
        ln = self.lines[axis].get(k)
        if ln is None:
            t = time.perf_counter()
            ln = self.lines[axis][k] = self._make_line(axis, k)
            self.build_secs += time.perf_counter() - t
        return ln

    def _make_line(self, axis, k):
        feats = self._features_on(axis, k)
        stop = _merge([(s, e) for kind, s, e, _ in feats if kind == BLK or kind == STOP[axis]])
        border = {}
        for kind, s, _, value in feats:          # in feature order: a later frame border on the same points holds
            if kind == FRAME[axis]:
                border[s] = value
        frame_at = sorted(border)
        return _Line(stop, _merge([(s, e) for kind, s, e, _ in feats if kind == NT]),
                     sorted({s for kind, s, _, _ in feats if kind == CROSS[axis]}),
                     frame_at, list(itertools.accumulate((border[p] for p in frame_at), initial=0)),
                     _merge([(s, e) for kind, s, e, _ in feats if kind == PER_STEP[axis]]),
                     self._runs(stop, self.n[axis], self.gen[axis].get(k, ())))

    @staticmethod
    def _runs(stop, n, extents):
        """The runs of free cells (not in stop) that meet one of the extents: the candidate runs of the line."""
        if not extents:
            return [], []
        ext = sorted(extents)
        firsts = [e[0] for e in ext]
        reach = list(itertools.accumulate((e[1] for e in ext), max))
        runs_s, runs_e, p = [], [], 0
        for s, e in itertools.chain(zip(*stop), ((n, n),)):
            if p <= s - 1:
                k = bisect_right(firsts, s - 1) - 1
                if k >= 0 and reach[k] >= p:
                    runs_s.append(p)
                    runs_e.append(s - 1)
            p = e + 1
        return runs_s, runs_e

    def go(self, i, j, d):
        """The next stop from (i, j) going d, and the cost of the stretch to it: (i2, j2, cost), or None. A stop is a point where a
        candidate run of the crossing line meets this one and a turn is allowed, or a goal entered going d. Kept: the search asks
        again for each way it arrives at (i, j)."""
        key = ((i * self.NY + j) << 2) + d
        if key not in self.edges:
            self.edges[key] = self._go(i, j, d)
        return self.edges[key]

    def _go(self, i, j, d):
        axis, step = d & 1, (1 if d < 2 else -1)
        p, k = (i, j) if axis == 0 else (j, i)
        ln = self.line(axis, k)
        far = ln.reach(p, step, self.n[axis])
        if far == p:
            return None
        other = 1 - axis
        cands, crossing, goals = self.cands[other], self.lines[other], self.goals
        ahead = (range(bisect_right(cands, p), bisect_right(cands, far)) if step > 0 else
                 range(bisect_left(cands, p) - 1, bisect_left(cands, far) - 1, -1))      # the candidate lines up to `far`, in order
        for x in ahead:
            q = cands[x]
            at = (q, k) if axis == 0 else (k, q)
            if d in goals.get(at, ()) or (_holds_at((crossing.get(q) or self.line(other, q)).runs, k) and not _holds_at(ln.turnless, q)):
                return at[0], at[1], ln.cost(p + 1, q) if step > 0 else ln.cost(q, p - 1)
        return None

    def walk_back(self, starts, goals):
        """route._reachable on this lattice, one cell per next(): a walk BACK from the goal states, cell by cell, over the moves the
        search allows (a cell entered only when its line does not stop that step, a turn only where one is allowed), with no costs.
        Yields None while it walks, then True when it reaches a start state, or False when it runs out of cells: then no path
        exists. It pays when the goal is walled in; when the start is, the search itself runs out of nodes first."""
        want = {(i, j, R.OUT[s]) for i, j, _, s in starts}
        todo = [(i, j, d) for (i, j), ds in goals.items() for d in ds]
        seen = set(todo)
        while todo:
            yield None
            i, j, d = todo.pop()
            if (i, j, d) in want:
                yield True
                return
            axis = d & 1
            if _holds_at(self.line(axis, (j, i)[axis]).stop, (i, j)[axis]):
                continue                         # no step going d enters (i, j)
            i0, j0 = i - R.DX[d], j - R.DY[d]    # the step came from here
            if not (0 <= i0 < self.NX and 0 <= j0 < self.NY):
                continue
            may_turn = not _holds_at(self.line(0, j0).turnless, i0)
            for d0 in (d, (d + 1) & 3, (d + 3) & 3):
                if (d0 == d or may_turn) and (i0, j0, d0) not in seen:
                    seen.add((i0, j0, d0))
                    todo.append((i0, j0, d0))
        yield False


def _bends(dx, dy, d, gd):
    """The fewest bends of a path that leaves a point going d and arrives going gd at a point dx, dy lattice steps away, with nothing
    in the way. The picture is turned so that d points east; then gd is r quarter turns from it."""
    for _ in range(d):
        dx, dy = dy, -dx
    r = (gd - d) % 4
    if r == 0:
        return 0 if dy == 0 and dx >= 0 else 2 if dx > 0 else 4
    if r == 2:
        return 2 if dy else 4
    return 1 if dx >= 0 and (dy > 0 if r == 1 else dy < 0) else 3


# FEWEST[d][gd][xs][ys]: the fewest bends from a point going d to any point of a box, arriving going gd. xs (ys) are the signs that
# column (row) differences to the box take, as bits: 1 negative, 2 zero, 4 positive (_bends depends only on the signs).
FEWEST = [[[[min((_bends(sx, sy, d, gd) for sx in (-1, 0, 1) if xs >> (sx + 1) & 1 for sy in (-1, 0, 1) if ys >> (sy + 1) & 1),
                 default=0) for ys in range(8)] for xs in range(8)] for gd in range(4)] for d in range(4)]


def _heuristic(goals):
    """h(i, j, d): a lower bound of the cost from (i, j) going d to a goal: per goal side (its goal points lie on one column or one
    row), the Manhattan steps to it, TURN_COST per bend that any path must make, and the side's cost; the least of the sides."""
    group = {}
    for (i, j), ds in goals.items():
        for d, extra in ds.items():
            group.setdefault((d, extra), []).append((i, j))
    sides = [(gd, min(p[0] for p in ps), max(p[0] for p in ps), min(p[1] for p in ps), max(p[1] for p in ps), extra)
             for (gd, extra), ps in group.items()]
    turn = R.TURN_COST

    def h(i, j, d):
        best, fewest = math.inf, FEWEST[d]
        for gd, i1, i2, j1, j2, extra in sides:
            xs = (i1 < i) | (i1 <= i <= i2) << 1 | (i2 > i) << 2          # the signs of i1 - i .. i2 - i, as FEWEST wants them
            ys = (j1 < j) | (j1 <= j <= j2) << 1 | (j2 > j) << 2
            c = max(0, i1 - i, i - i2) + max(0, j1 - j, j - j2) + turn * fewest[gd][xs][ys] + extra
            if c < best:
                best = c
        return best
    return h


def search(sc, a, b, sa, sb, pad, natural=None, inside=None, prove_none=False, span_a=None, span_b=None):
    """route._route for BBB_ROUTER=vis: same arguments, (points, cost) or None. prove_none: the search walks back from the goals
    at the same time (_Lattice.walk_back), a cell per node it takes from the queue, and gives up as soon as the walk finds no start."""
    return next(search_paths(sc, a, b, sa, sb, pad, natural, inside, prove_none, span_a, span_b), None)


def search_paths(sc, a, b, sa, sb, pad, natural=None, inside=None, prove_none=False, span_a=None, span_b=None):
    """The paths of search() as a generator of (points, cost): the cheapest first, then alternatives that differ from all before
    them, by the iterative penalty method for dissimilar paths (P. Akguen, E. Erkut and R. Batta, "On finding dissimilar paths",
    European Journal of Operational Research 121, 2000): after each path, every step along a stretch within PEN_BAND lattice lines of
    one of its stretches costs PEN_STEP more, and the search runs again on the same lattice. (Yen's k shortest paths were tried
    first: on this lattice its next paths are the first one shifted by 5px, one start cell or one jog at a time, so even 1000 of them
    hold no other route.) The cost yielded is the path's own cost, without penalties. The next path is searched only when the caller
    asks for it, so a caller that takes the first pays for one search. A polyline is yielded once; at most MAX_ALTERNATIVES
    searches."""
    t0 = time.perf_counter()
    ra, rb = sc.boxes[a], sc.boxes[b]
    lat = _Lattice(sc, a, b, pad, inside)
    nat = natural or (sa[0], sb[0])
    starts, goals = R._ends(ra, rb, sa, sb, nat, span_a, span_b, lat.x0, lat.y0, lat.NX, lat.NY, lat.free)
    R.STATS['build'] += time.perf_counter() - t0
    if not starts or not goals:
        return
    lat.set_goals(goals)
    NY = lat.NY
    sources = {}
    for i, j, off, s in starts:
        st, c0 = (i * NY + j) * 4 + R.OUT[s], off * 0.15 + (0 if s == nat[0] else R.SIDE_COST)
        sources[st] = min(c0, sources.get(st, math.inf))
    goal_cost = {(i * NY + j) * 4 + d: extra for (i, j), ds in goals.items() for d, extra in ds.items()}
    h = _heuristic(goals)
    walk = lat.walk_back(starts, goals) if prove_none else None
    penalised = ({}, {})                                  # per axis: line -> [(lo, hi)] of the stretches of the paths found
    drawn, repeats = set(), 0
    for _ in range(MAX_ALTERNATIVES):
        found = _astar(lat, sorted(sources.items()), goal_cost, h, walk, penalised)
        walk = None
        R.STATS['search'] += lat.search_secs
        R.STATS['build'] += lat.build_secs
        lat.search_secs = lat.build_secs = 0.0
        if found is None:
            return
        states, cost = found
        for (i, j, d), (i2, j2, _) in zip(_decode(states, NY), _decode(states[1:], NY)):
            axis = d & 1 if (i, j) == (i2, j2) else (0 if j == j2 else 1)
            line, lo, hi = (j, min(i, i2), max(i, i2)) if axis == 0 else (i, min(j, j2), max(j, j2))
            penalised[axis].setdefault(line, []).append((lo, hi))
        pts = R._finish(states, NY, lat.x0, lat.y0, ra, rb)
        if tuple(pts) in drawn:                           # R.unjog can make two state paths one polyline: yield it once; and when
            repeats += 1                                  # the penalties no longer move the search, there is no other route
            if repeats >= 2:
                return
            continue
        drawn.add(tuple(pts))
        yield pts, cost


def _decode(states, NY):
    return [((st >> 2) // NY, (st >> 2) % NY, st & 3) for st in states]


def _penalty(penalised, axis, line, lo, hi):
    """What a stretch on `line` of `axis` from position lo to hi pays for running along the stretches of the paths found before."""
    near = penalised[axis]
    return PEN_STEP * sum(max(0, min(hi, h2) - max(lo, l2)) for k in range(line - PEN_BAND, line + PEN_BAND + 1) for l2, h2 in near.get(k, ()))


def _astar(lat, sources, goal_cost, h, walk=None, penalised=({}, {})):
    """A* over (node, direction) from the source states [(state, cost)] to the goal states (goal_cost: state -> side cost):
    (the states of the cheapest path, its cost without penalties) or None. walk: a _Lattice.walk_back to advance one step per node
    taken; the search stops when it says False. penalised: the stretches of the paths found before (search_paths); a step along
    them pays _penalty on top of its cost, and the heuristic, which counts no penalty, stays a lower bound.
    Heap entries (f, g, state), the state packed as (i * NY + j) * 4 + direction: the grid search's order, so ties break alike where
    the two visit the same states. Adds to lat.search_secs (the time of the search less the rows and columns built on the way)."""
    t0, built0 = time.perf_counter(), lat.build_secs
    NY = lat.NY
    dist, real, prev, pq = {}, {}, {}, []
    for st, c0 in sources:
        if c0 < dist.get(st, math.inf):
            dist[st] = real[st] = c0
            heapq.heappush(pq, (c0 + h(*divmod(st >> 2, NY), st & 3), c0, st))
    end = None
    while pq:
        if walk is not None:
            verdict = next(walk)
            if verdict is False:
                break
            if verdict:
                walk = None
        _, cost, st = heapq.heappop(pq)
        if cost > dist[st]:
            continue
        if st in goal_cost:
            end = st
            break
        d = st & 3
        i, j = divmod(st >> 2, NY)
        may_turn = not _holds_at(lat.line(0, j).turnless, i)
        for nd in (d, (d + 1) & 3, (d + 3) & 3):
            if nd != d and not may_turn:
                continue
            nxt = lat.go(i, j, nd)
            if nxt is None:
                continue
            i2, j2, c = nxt
            s2 = (i2 * NY + j2) * 4 + nd
            step = c + (R.TURN_COST if nd != d else 0) + goal_cost.get(s2, 0)
            pen = _penalty(penalised, nd & 1, *((j, min(i, i2), max(i, i2)) if nd & 1 == 0 else (i, min(j, j2), max(j, j2)))) \
                if penalised[nd & 1] else 0
            c2 = cost + step + pen
            # s2 ^ 1 and s2 ^ 3 are the same node going the two perpendicular ways; a turn is allowed at every stop but a goal. When one
            # of them is cheaper by more than a turn, it can do all that s2 can for less (but turn back the way it came, which only
            # retraces a path its own predecessors cover more cheaply), so s2 is on no cheapest path.
            if s2 not in goal_cost and min(dist.get(s2 ^ 1, math.inf), dist.get(s2 ^ 3, math.inf)) + R.TURN_COST < c2:
                continue
            if c2 < dist.get(s2, math.inf):
                dist[s2], real[s2] = c2, real[st] + step
                prev[s2] = st
                heapq.heappush(pq, (c2 + (0 if s2 in goal_cost else h(i2, j2, nd)), c2, s2))
    lat.search_secs += time.perf_counter() - t0 - (lat.build_secs - built0)
    if end is None:
        return None
    states = [end]
    while states[-1] in prev:
        states.append(prev[states[-1]])
    states.reverse()
    return states, real[end]


def selftest(seeds=20):
    """Both routers on random scenes (boxes off the lattice, frames, labels, pills, side choices, spans), each arrow routed by both
    in the same scene: the costs must be equal. The grid's path then joins the scene. Prints one line; returns True when all agree."""
    router = os.environ.get('BBB_ROUTER')
    try:
        bad, n = _compare(seeds)
    finally:
        if router is None:
            os.environ.pop('BBB_ROUTER', None)
        else:
            os.environ['BBB_ROUTER'] = router
    print('ovg self-test: %d arrows, %d with another cost%s' % (n, len(bad), ''.join('\n  ' + x for x in bad)))
    return not bad


def _compare(seeds):
    """selftest()'s scenes: ([one line per arrow where the searches disagree], arrows tried). Each arrow: route.route with each
    router, the same cost; and one vis search of a 260px window, with prove_none and without, the same result (most such windows
    hold a path, so the walk back must find a start)."""
    bad, n = [], 0
    for seed in range(seeds):
        rnd = random.Random(seed)
        W, H = rnd.choice([(900, 700), (1400, 1000)])
        boxes = {}
        for _ in range(300):
            if len(boxes) >= 10:
                break
            w, h = rnd.randrange(100, 300, 10) + rnd.choice([0, 0.5, 2.3]), rnd.randrange(60, 140, 10) + rnd.choice([0, 1.5, 3.7])
            x, y = round(rnd.uniform(60, W - w - 60), 1), round(rnd.uniform(200, H - h - 60), 1)
            if all(x + w + 70 < bx or bx + bw + 70 < x or y + h + 70 < by or by + bh + 70 < y for bx, by, bw, bh in boxes.values()):
                boxes[100 + len(boxes)] = (x, y, w, h)
        frames = []
        for _ in range(rnd.randint(0, 2)):       # a frame round some boxes, when it cuts no other box
            pick = [boxes[k] for k in rnd.sample(sorted(boxes), max(1, len(boxes) // 3))]
            fr = (min(r[0] for r in pick) - 40, min(r[1] for r in pick) - 50,
                  max(r[0] + r[2] for r in pick) - min(r[0] for r in pick) + 80, max(r[1] + r[3] for r in pick) - min(r[1] for r in pick) + 90)
            if all(R.holds(fr, r) or fr[0] + fr[2] < r[0] or r[0] + r[2] < fr[0] or fr[1] + fr[3] < r[1] or r[1] + r[3] < fr[1]
                   for r in boxes.values()):
                frames.append(fr)
        sc = R.Scene(boxes, frames, [(rnd.uniform(0, W), rnd.uniform(200, H), 70, 18) for _ in range(rnd.randint(0, 3))],
                     [(rnd.uniform(0, W), rnd.uniform(200, H), 52, 52) for _ in range(rnd.randint(0, 1))], bounds=(30, 165, W, H))
        for _ in range(rnd.randint(3, 8)):
            a, b = rnd.sample(sorted(boxes), 2)
            sa, sb, span = '*', '*', None
            if rnd.random() < .3:
                sa, sb = rnd.choice(R.sides_for(boxes[a], boxes[b]))
                lo, hi = R._side_cells(boxes[a], sa, 20)
                span = (lo, (lo + hi) / 2) if rnd.random() < .5 else None
            cost = {}
            for which in ('grid', 'vis'):
                os.environ['BBB_ROUTER'] = which
                R.LAST_COST = None
                pts = R.route(sc, a, b, sa, sb, span_a=span)
                cost[which] = R.LAST_COST if pts else None
                if which == 'grid':
                    path = pts
            # the walk back must never say "no path" where there is one: one window searched with it and without it
            natural = R.sides_for(boxes[a], boxes[b])[0] if sa == '*' else None
            sides = ('RLTB', 'RLTB') if sa == '*' else (sa, sb)
            for proved in (False, True):
                found = search(sc, a, b, *sides, 260, natural, None, proved, span)
                cost['vis, 260px' + (', walk back' if proved else '')] = found and found[1]
            n += 1
            if len({None if c is None else round(c, 6) for c in (cost['grid'], cost['vis'])}) > 1 or \
                    cost['vis, 260px'] != cost['vis, 260px, walk back']:
                bad.append('seed %d #%d -> #%d %s %s: %s' % (seed, a, b, sa, sb, cost))
            if path:
                sc.arrows.append(list(path))
    return bad, n


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        import importlib                         # run the module that route.py imports, so that this file loads once
        sys.exit(0 if importlib.import_module('ovg').selftest() else 1)
    sys.exit('usage: ovg.py selftest   (as a module: route.py uses it)')
