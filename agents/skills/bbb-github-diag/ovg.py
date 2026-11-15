#!/usr/bin/env python3
"""Arrow search on an orthogonal visibility graph: the `vis` router of route.py (BBB_ROUTER=vis, the default).

The technique is the orthogonal visibility graph of Wybrow, Marriott and Stuckey ("Orthogonal Connector Routing", GD 2009), as in the
libavoid router of Adaptagrams: nodes only where a path may have to turn, edges along the free stretches between them, and A* over
(node, direction). The cost model and every rule are route.py's (see its docstring); only the search is different. Both searches work
on the same 5px lattice (route._window), so they find paths of the same cost and their points can be compared.

Why the sparse graph loses nothing. Slide one straight stretch of a path sideways by one lattice step: its two neighbours grow or
shrink by one step each, and the cost changes by the same amount at every step, until the stretch or one of its two bends meets the
edge of a feature (route.py's obstacle layers: a box or a label, a band beside another arrow or a frame border, a zone where a turn is
not allowed, a band where a vertical step costs NEAR_COST) or the window edge. Crossings and frame borders are not such edges: a bend
is never allowed near a line or a frame border (their no-turn bands), so a crossing appears or disappears only where a bend cannot be.
So some cheapest path has every stretch on a candidate line: just outside the edge of a feature (on both sides of a NEAR band, where
the cost per step changes), on a goal's line, or on the window edge; and the stretch lies in a run of free cells of that line that
meets the feature's extent (the stretch itself, or the bend at its end, touches the feature). The search stops at the points where a
candidate run meets the line it travels on (and where a turn is allowed), and nowhere else; it turns only there.

Structures. Index, one per Scene: the features of the scene's labels, pills and arrows, in canvas px, built on the first search and
kept in step with the scene (what a list gained is added; a list replaced or shortened is indexed again). Per call, _Lattice: the
window, the features on its lattice (with the call's own: its two boxes, which keep 3px instead of BOXM, the frames, whose border cost
depends on whether they hold an end, the no-turn zones round the two boxes, the outside of the frame for an `inside` search), and,
built when the search first reaches them, per row and per column: the cells a step may not enter, the crossing and frame costs, the
NEAR cells, the cells where no turn is allowed, and the candidate runs.

The heuristic: Manhattan steps to the nearest goal side, plus TURN_COST for each bend that any path from that point and direction to
that side must make, plus the side's cost. It never overestimates and it is consistent, so the first goal taken from the queue is a
cheapest one.
"""
import heapq, itertools, math, time
from bisect import bisect_left, bisect_right

import route as R

G = R.G
BLK, NOH, NOV, NT, NEAR, CRH, CRV, FRH, FRV = range(9)
# BLK: no step may enter the cell (a goal excepted); NOH, NOV: no horizontal, no vertical step may enter; NT: no turn there;
# NEAR: a vertical step into it costs NEAR_COST; CRH, CRV: a vertical (horizontal) step into it crosses a line, CROSS_COST;
# FRH, FRV: a vertical (horizontal) step into it crosses a frame border, at the border's cost.
RECT, HLINE, VLINE = range(3)
# A feature in canvas px is (kind, shape, p, q, r, s, value): a RECT (x0, y0, x1, y1) covers the lattice points strictly inside it;
# an HLINE (y, x0, x1, -) the points of the lattice row nearest y strictly between x0 and x1; a VLINE (x, y0, y1, -) likewise.
# On the lattice of one call it becomes (kind, i1, i2, j1, j2, value): the points i1..i2 across, j1..j2 down.
# A line along a row (axis 0) holds horizontal steps, a column (axis 1) vertical ones; per axis: the kind that stops a step along it,
# the kind of line it crosses, of frame border, and the kind that costs per step (none along a row).
STOP, CROSS, FRAME, PER_STEP = (NOH, NOV), (CRV, CRH), (FRV, FRH), (None, NEAR)
BUCKET = 16                                      # lattice lines per bucket of the per-call feature lists


class Index:
    """The features of a scene's labels, pills and arrows: the obstacles that do not depend on the arrow being routed."""
    SOURCES = ('labels', 'pills', 'arrows')

    def __init__(self):
        self.feats = {name: [] for name in self.SOURCES}
        self.seen = {}                           # name -> (the list, how many items are indexed, the last of them)

    def sync(self, sc):
        """Add the features of the items appended since the last call; index a list again when it was replaced or shortened, or its
        last indexed item is not the same object (a pop and an append)."""
        for name in self.SOURCES:
            items = getattr(sc, name)
            old = self.seen.get(name)
            if old and old[0] is items and len(items) >= old[1] and (old[1] == 0 or items[old[1] - 1] is old[2]):
                fresh = items[old[1]:]
            else:
                self.feats[name], fresh = [], items
            make = _FEATURES[name]
            for item in fresh:
                self.feats[name] += make(item)
            self.seen[name] = (items, len(items), items[-1] if items else None)

    def all(self):
        return itertools.chain.from_iterable(self.feats.values())


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


_FEATURES = {'labels': _label, 'pills': _pill, 'arrows': _arrow}


def _call_features(sc, a, b, inside, window):
    """The features that depend on the arrow being routed: the boxes (its own two keep 3px, the others BOXM), the frames (a border
    keeps FPROX and costs FRAME_OWN_COST when the frame holds an end, FRAME_COST otherwise; corners are blocked), the outside of the
    frame of an `inside` search, and the no-turn zones round its two boxes. Frames come in the grid search's order: where two borders
    share lattice points, the later one's cost holds, as there."""
    ra, rb = sc.boxes[a], sc.boxes[b]
    out = []
    for n, (x, y, w, h) in sc.boxes.items():
        m = 3 if n in (a, b) else R.BOXM
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
        out += [(BLK, RECT, x0 - G, y0 - G, fx + 2, y1 + G, 1), (BLK, RECT, fx + fw - 2, y0 - G, x1 + G, y1 + G, 1),
                (BLK, RECT, x0 - G, y0 - G, x1 + G, fy + 2, 1), (BLK, RECT, x0 - G, fy + fh - 2, x1 + G, y1 + G, 1)]
    t = R.TURN_FREE                              # leave and enter a box straight
    out += [(NT, RECT, x - t, y - t, x + w + t, y + h + t, 1) for x, y, w, h in (ra, rb)]
    return out


def _span(lo, hi, o, n):
    """Lattice indices k, 0 <= k < n, with lo < o + k * G < hi (route.py's rng)."""
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
    stop, turnless, near, runs: (starts, ends) of disjoint intervals; cross: sorted positions; frame: sorted positions and the
    running sum of their costs."""
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
        k1, k2 = bisect_left(self.frame_at, lo), bisect_right(self.frame_at, hi)
        c += self.frame_sum[k2] - self.frame_sum[k1]
        s, e = self.near
        for k in range(max(0, bisect_right(s, lo) - 1), bisect_right(s, hi)):
            c += R.NEAR_COST * max(0, min(e[k], hi) - max(s[k], lo) + 1)
        return c


class _Lattice:
    """The window of one call, its lattice and its features (module docstring); rows and columns are built when first asked for."""

    def __init__(self, sc, a, b, pad, inside):
        ra, rb = sc.boxes[a], sc.boxes[b]
        self.x0, self.y0, x1, y1, self.NX, self.NY = R._window(sc, ra, rb, pad, inside)
        if getattr(sc, 'index', None) is None:
            sc.index = Index()
        sc.index.sync(sc)
        self.px = (self.x0, self.y0, self.x0 + (self.NX - 1) * G, self.y0 + (self.NY - 1) * G)   # the lattice's extent in px
        self.goals, self.goal_at = {}, ({}, {})
        self.feats = [f for f in map(self._on_lattice, itertools.chain(sc.index.all(),
                      _call_features(sc, a, b, inside, (self.x0, self.y0, x1, y1)))) if f]
        self.n = (self.NX, self.NY)              # positions along a row, along a column
        self.buckets = ({}, {})                  # per axis: bucket of BUCKET rows (columns) -> the features that reach into it
        for f in self.feats:
            for axis, (lo, hi) in enumerate(((f[3], f[4]), (f[1], f[2]))):
                for k in range(lo // BUCKET, hi // BUCKET + 1):
                    self.buckets[axis].setdefault(k, []).append(f)
        self.gen = self._generators()
        self.blocked, self.lines = {}, {}        # (axis, k) -> BLK intervals of that line, its _Line
        self.edges = {}                          # search state -> go()
        self.build_secs = 0.0

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

    def _generators(self):
        """Per axis, {line: [extent]}: the candidate lines (module docstring) and the extent each must meet, across that line.
        A row next to a feature's top or bottom edge must meet the feature's columns, and the reverse; the window edges are candidates
        everywhere. A NEAR band adds the lines just inside its edges too (its cost per step changes there, not its feasibility)."""
        rows, cols = {}, {}
        for kind, i1, i2, j1, j2, _ in self.feats:
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
        """Goals {(i, j): {direction: side cost}}: a goal point may be entered even when blocked, it is a stop for a stretch that
        enters the box from it, and its last stretch's line is a candidate."""
        self.goals = goals
        self.goal_at = ({}, {})                  # per axis, line -> the goal positions along it
        for (i, j), ds in goals.items():
            self.goal_at[0].setdefault(j, []).append(i)
            self.goal_at[1].setdefault(i, []).append(j)
            for d in ds:
                if d & 1:                        # entered going down or up: the last stretch is on column i
                    self.gen[1].setdefault(i, []).append((j, j))
                    self.gen[0].setdefault(j, [])
                else:
                    self.gen[0].setdefault(j, []).append((i, i))
                    self.gen[1].setdefault(i, [])
        self.cands = tuple(sorted(g) for g in self.gen)    # per axis, the candidate lines in order

    def _covering(self, axis, k):
        """(kind, start, end, value) of every feature on line k of axis, start..end along it."""
        out = []
        for f in self.buckets[axis].get(k // BUCKET, ()):
            if axis == 0 and f[3] <= k <= f[4]:
                out.append((f[0], f[1], f[2], f[5]))
            elif axis == 1 and f[1] <= k <= f[2]:
                out.append((f[0], f[3], f[4], f[5]))
        return out

    def blocked_on(self, axis, k):
        """BLK intervals of a line, goals not excepted (the ends are chosen with it)."""
        ivs = self.blocked.get((axis, k))
        if ivs is None:
            ivs = self.blocked[axis, k] = _merge([(s, e) for kind, s, e, _ in self._covering(axis, k) if kind == BLK])
        return ivs

    def free(self, i, j):
        """May a path start or end at (i, j)? (route._ends asks it.)"""
        return not _holds_at(self.blocked_on(0, j), i)

    def line(self, axis, k):
        """The _Line of row k (axis 0) or column k (axis 1), built on the first call."""
        ln = self.lines.get((axis, k))
        if ln is None:
            t = time.perf_counter()
            ln = self.lines[axis, k] = self._make_line(axis, k)
            self.build_secs += time.perf_counter() - t
        return ln

    def _make_line(self, axis, k):
        feats = self._covering(axis, k)
        goal_at = sorted(self.goal_at[axis].get(k, ()))
        stop = [(s, e) for kind, s, e, _ in feats if kind == STOP[axis]]
        for s, e in zip(*self.blocked_on(axis, k)):        # a blocked cell stops a step, a goal excepted
            for g in goal_at:
                if s <= g <= e:
                    stop.append((s, g - 1))
                    s = g + 1
            stop.append((s, e))
        stop = _merge([iv for iv in stop if iv[0] <= iv[1]])
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
        cands, lines, goals = self.cands[other], self.lines, self.goals
        ahead = (range(bisect_right(cands, p), bisect_right(cands, far)) if step > 0 else
                 range(bisect_left(cands, p) - 1, bisect_left(cands, far) - 1, -1))      # the candidate lines up to `far`, in order
        for x in ahead:
            q = cands[x]
            at = (q, k) if axis == 0 else (k, q)
            crossing = lines.get((other, q)) or self.line(other, q)
            if d in goals.get(at, ()) or (_holds_at(crossing.runs, k) and not _holds_at(ln.turnless, q)):
                return at[0], at[1], ln.cost(p + 1, q) if step > 0 else ln.cost(q, p - 1)
        return None


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


def _signs(lo, hi, p):
    """Which signs q - p takes for q in lo..hi, as bits: 1 negative, 2 zero, 4 positive."""
    return (lo < p) | (lo <= p <= hi) << 1 | (hi > p) << 2


# FEWEST[d][gd][xs][ys]: the fewest bends from a point going d to any point of a box, arriving going gd, where xs and ys are the
# _signs of the box's columns and rows seen from the point (_bends depends only on the signs of dx and dy).
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
            xs = (i1 < i) | (i1 <= i <= i2) << 1 | (i2 > i) << 2          # _signs(i1, i2, i), written out: h runs for every push
            ys = (j1 < j) | (j1 <= j <= j2) << 1 | (j2 > j) << 2
            c = max(0, i1 - i, i - i2) + max(0, j1 - j, j - j2) + turn * fewest[gd][xs][ys] + extra
            if c < best:
                best = c
        return best
    return h


def search(sc, a, b, sa, sb, pad, natural=None, inside=None, prove_none=False, span_a=None, span_b=None):
    """route._route for BBB_ROUTER=vis: same arguments, (points, cost) or None. prove_none needs no walk back here: when there is no
    path, the search runs out of the few nodes it can reach."""
    t0 = time.perf_counter()
    ra, rb = sc.boxes[a], sc.boxes[b]
    lat = _Lattice(sc, a, b, pad, inside)
    nat = natural or (sa[0], sb[0])
    starts, goals = R._ends(ra, rb, sa, sb, nat, span_a, span_b, lat.x0, lat.y0, lat.NX, lat.NY, lat.free)
    if not starts or not goals:
        R.STATS['build'] += time.perf_counter() - t0
        return None
    lat.set_goals(goals)
    t1 = time.perf_counter()
    NY = lat.NY
    h = _heuristic(goals)
    goal_cost = {(i * NY + j) * 4 + d: extra for (i, j), ds in goals.items() for d, extra in ds.items()}
    dist, prev, pq = {}, {}, []
    for i, j, off, s in starts:
        st, c0 = (i * NY + j) * 4 + R.OUT[s], off * 0.15 + (0 if s == nat[0] else R.SIDE_COST)
        if c0 < dist.get(st, math.inf):
            dist[st] = c0
            heapq.heappush(pq, (c0 + h(i, j, R.OUT[s]), c0, st))
    end = None
    while pq:
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
            c2 = cost + c + (R.TURN_COST if nd != d else 0) + goal_cost.get(s2, 0)
            # s2 ^ 1 and s2 ^ 3 are the same node going the two perpendicular ways. A turn is allowed at every stop but a goal; when
            # one of them is cheaper by more than a turn, it does all that s2 could do for less, so s2 is on no cheapest path.
            if s2 not in goal_cost and min(dist.get(s2 ^ 1, math.inf), dist.get(s2 ^ 3, math.inf)) + R.TURN_COST < c2:
                continue
            if c2 < dist.get(s2, math.inf):
                dist[s2] = c2
                prev[s2] = st
                heapq.heappush(pq, (c2 + (0 if s2 in goal_cost else h(i2, j2, nd)), c2, s2))
    t2 = time.perf_counter()
    R.STATS['build'] += t1 - t0 + lat.build_secs
    R.STATS['search'] += t2 - t1 - lat.build_secs
    if end is None:
        return None
    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path = [((s >> 2) // NY, (s >> 2) % NY, s & 3) for s in reversed(path)]
    return R._finish(path, lat.x0, lat.y0, ra, rb), dist[end]
