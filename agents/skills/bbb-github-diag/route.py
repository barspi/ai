#!/usr/bin/env python3
"""Arrow router: finds an orthogonal path for one arrow in the diagram AS IT IS NOW, and a place for its label.

The router reads the current obstacles (boxes, frame borders and frame titles, labels, `new` pills, every arrow already drawn) from a
Scene, so it adapts to the crossings and the free space of the current diagram. Nothing is hard-coded for one diagram.

    sc = Scene(boxes, frames, labels, pills, arrows)      boxes {num: (x, y, w, h)}; the others lists of (x, y, w, h) / point lists
    pts = route(sc, 101, 110, 'R', 'L')                   tail on the right side of #101, tip on the left side of #110; None if no path
    lab = place_label(sc, pts, 'closed by')               (cx, cy) of the label, or None
    sc.add(pts, 'closed by', lab)                         remember both, so the next arrow sees them

Rules it keeps (SKILL.md, "Hard arrows"): a path never goes under a box (26px clear) or a label (10px clear); never runs parallel to another
arrow closer than 36px or to a frame border closer than 30px; crosses a line only at a right angle, on a long straight stretch (at least
36px from either line's bends and ends); never turns within 40px of a box edge (so it leaves and enters straight); has as few crossings and
bends as it can. It picks the exit and entry points along the two sides itself, so full sides are avoided. hops.py draws the jump arcs.
The search is Dijkstra/A* on a 5px grid inside a window around the two boxes (the window grows when nothing is found).
"""
import heapq, math

import draw

G = 5
BOXM, LABM, PROX, FPROX, TURN_FREE, EDGE_MARGIN = 26, 10, 36, 30, 40, 24
TURN_COST, CROSS_COST, SIDE_COST = 30, 50, 20
OUT = {'R': 0, 'L': 2, 'B': 1, 'T': 3}               # direction numbers: 0 east, 1 south, 2 west, 3 north
DX, DY = (1, 0, -1, 0), (0, 1, 0, -1)


class Scene:
    def __init__(self, boxes, frames=(), labels=(), pills=(), arrows=(), bounds=None):
        self.bounds = bounds                               # (x0, y0, x1, y1): the area arrows may use (not the header, not the legend)
        self.boxes, self.frames = dict(boxes), list(frames)
        self.labels, self.pills = list(labels), list(pills)
        self.arrows = [list(a) for a in arrows]
        self.hops = []                                     # jump arcs already in the picture: (x0, y0, x1, y1) of each; labels keep clear of them

    def add(self, pts, kind=None, lab=None):
        self.arrows.append(list(pts))
        if lab:
            w = draw.label_width(kind)
            self.labels.append((lab[0] - w / 2, lab[1] - 9, w, 18))


def segments(pts):
    out = []
    for p, q in zip(pts, pts[1:]):
        if abs(p[1] - q[1]) < .01 and abs(p[0] - q[0]) > .01:
            out.append(('h', p[1], min(p[0], q[0]), max(p[0], q[0])))
        elif abs(p[0] - q[0]) < .01 and abs(p[1] - q[1]) > .01:
            out.append(('v', p[0], min(p[1], q[1]), max(p[1], q[1])))
    return out


def _side_cells(r, side, lo_margin):
    """Positions along a side of a box where an arrow may attach (every 5px, keeping `lo_margin` from the corners)."""
    x, y, w, h = r
    if side in 'RL':
        a, b = y + lo_margin, y + h - lo_margin
        if b < a:
            a = b = y + h / 2
        return a, b
    a, b = x + 24, x + w - 24
    return a, b


def _route(sc, a, b, sa, sb, pad, natural=None):
    ra, rb = sc.boxes[a], sc.boxes[b]
    bx0, by0, bx1, by1 = (int(v) for v in (sc.bounds or (0, 0, 10 ** 6, 10 ** 6)))
    x0 = max(bx0, int(min(ra[0], rb[0]) - pad))
    y0 = max(by0, int(min(ra[1], rb[1]) - pad))
    x1 = min(bx1, int(max(ra[0] + ra[2], rb[0] + rb[2]) + pad))
    y1 = min(by1, int(max(ra[1] + ra[3], rb[1] + rb[3]) + pad))
    NX, NY = (x1 - x0) // G + 1, (y1 - y0) // G + 1
    size = NX * NY
    blk, noh, nov, nt, crh, crv = (bytearray(size) for _ in range(6))

    def rng(lo, hi, o, n):                       # grid indices with lo < coordinate < hi
        i1 = max(0, int(math.floor((lo - o) / G)) + 1)
        i2 = min(n - 1, int(math.ceil((hi - o) / G)) - 1)
        return i1, i2

    def mark(arr, xa, ya, xb, yb):
        i1, i2 = rng(xa, xb, x0, NX)
        j1, j2 = rng(ya, yb, y0, NY)
        if i2 < i1:
            return
        ones = b'\x01' * (i2 - i1 + 1)
        for j in range(j1, j2 + 1):
            arr[j * NX + i1:j * NX + i2 + 1] = ones

    for n, (x, y, w, h) in sc.boxes.items():
        m = 3 if n in (a, b) else BOXM
        mark(blk, x - m, y - m, x + w + m, y + h + m)
    for (x, y, w, h) in sc.labels:
        mark(blk, x - LABM, y - LABM, x + w + LABM, y + h + LABM)
    for (x, y, w, h) in sc.pills:
        mark(blk, x, y, x + w, y + h)

    def add_seg(o, c, lo, hi, prox, cost):
        if o == 'h':
            mark(noh, lo - prox, c - prox, hi + prox, c + prox)
            mark(nt, lo - prox, c - prox, hi + prox, c + prox)
            mark(blk, lo - prox, c - prox, lo + prox, c + prox)          # near the ends no crossing is allowed
            mark(blk, hi - prox, c - prox, hi + prox, c + prox)
            if cost:
                mark(crh, lo, c - G / 2 - .01, hi, c + G / 2 + .01)
        else:
            mark(nov, c - prox, lo - prox, c + prox, hi + prox)
            mark(nt, c - prox, lo - prox, c + prox, hi + prox)
            mark(blk, c - prox, lo - prox, c + prox, lo + prox)
            mark(blk, c - prox, hi - prox, c + prox, hi + prox)
            if cost:
                mark(crv, c - G / 2 - .01, lo, c + G / 2 + .01, hi)

    for pts in sc.arrows:
        for o, c, lo, hi in segments(pts):
            add_seg(o, c, lo, hi, PROX, True)
    for (x, y, w, h) in sc.frames:
        for o, c, lo, hi in (('h', y, x, x + w), ('h', y + h, x, x + w), ('v', x, y, y + h), ('v', x + w, y, y + h)):
            add_seg(o, c, lo, hi, FPROX, False)
    for r in (ra, rb):                                         # leave and enter a box straight
        x, y, w, h = r
        mark(nt, x - TURN_FREE, y - TURN_FREE, x + w + TURN_FREE, y + h + TURN_FREE)

    def cell(i, j):
        return j * NX + i

    def side_set(r, side, outward):
        """Grid cells just outside one side of a box where a path may start or end."""
        x, y, w, h = r
        lo, hi = _side_cells(r, side, 20)
        out = []
        if side in 'RL':
            cx = (x + w + 4) if side == 'R' else (x - 4)
            i = int(math.ceil((cx - x0) / G)) if side == 'R' else int(math.floor((cx - x0) / G))
            for j in range(int(math.ceil((lo - y0) / G)), int(math.floor((hi - y0) / G)) + 1):
                if 0 <= i < NX and 0 <= j < NY and not blk[cell(i, j)]:
                    out.append((i, j, abs((y0 + j * G) - (y + h / 2))))
        else:
            cy = (y + h + 4) if side == 'B' else (y - 4)
            j = int(math.ceil((cy - y0) / G)) if side == 'B' else int(math.floor((cy - y0) / G))
            for i in range(int(math.ceil((lo - x0) / G)), int(math.floor((hi - x0) / G)) + 1):
                if 0 <= i < NX and 0 <= j < NY and not blk[cell(i, j)]:
                    out.append((i, j, abs((x0 + i * G) - (x + w / 2))))
        return out

    # sa and sb may name several sides ('RLTB'): one search then finds the best path over all of them. `natural` (the side pair that
    # faces the other box) costs nothing; another side costs SIDE_COST, so it wins only when it saves a bend or a crossing.
    nat = natural or (sa[0], sb[0])
    starts = [(i, j, off, s) for s in sa for i, j, off in side_set(ra, s, OUT[s])]
    goals = {}
    for s in sb:
        for i, j, _ in side_set(rb, s, OUT[s]):
            goals.setdefault((i, j), {})[(OUT[s] + 2) % 4] = 0 if s == nat[1] else SIDE_COST   # entered against the side's outward way
    if not starts or not goals:
        return None
    goalset = goals
    gis = [i for i, j in goals]
    gjs = [j for i, j in goals]
    gi_lo, gi_hi, gj_lo, gj_hi = min(gis), max(gis), min(gjs), max(gjs)

    def heur(i, j):
        return max(0, gi_lo - i, i - gi_hi) + max(0, gj_lo - j, j - gj_hi)

    dist, prev, pq = {}, {}, []
    for i, j, off, s in starts:
        st = (i, j, OUT[s])
        c0 = off * 0.15 + (0 if s == nat[0] else SIDE_COST)
        if c0 < dist.get(st, 1e18):
            dist[st] = c0
            heapq.heappush(pq, (c0 + heur(i, j), c0, st))
    end = None
    done_goal = {}                                               # a goal state's cost includes its side cost: settle it when popped
    while pq:
        f, cst, st = heapq.heappop(pq)
        if cst > dist.get(st, 1e18):
            continue
        i, j, d = st
        if (i, j) in goals and d in goals[(i, j)]:
            if st in done_goal:
                end = st
                break
            done_goal[st] = True
            extra = goals[(i, j)][d]
            if extra:
                heapq.heappush(pq, (cst + extra + heur(i, j), cst + extra, st))
                dist[st] = cst + extra
                continue
            end = st
            break
        for nd in range(4):
            if nd == (d + 2) % 4:
                continue
            if nd != d and nt[cell(i, j)]:
                continue
            ni, nj = i + DX[nd], j + DY[nd]
            if not (0 <= ni < NX and 0 <= nj < NY):
                continue
            k = cell(ni, nj)
            if blk[k] and (ni, nj) not in goalset:
                continue
            if nd in (0, 2) and noh[k] or nd in (1, 3) and nov[k]:
                continue
            c2 = cst + 1 + (TURN_COST if nd != d else 0)
            if nd in (1, 3) and crh[k] or nd in (0, 2) and crv[k]:
                c2 += CROSS_COST
            s2 = (ni, nj, nd)
            if c2 < dist.get(s2, 1e18):
                dist[s2] = c2
                prev[s2] = st
                heapq.heappush(pq, (c2 + heur(ni, nj), c2, s2))
    if end is None:
        return None
    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    pts = [(x0 + path[0][0] * G, y0 + path[0][1] * G)]
    for k in range(1, len(path) - 1):
        if path[k + 1][2] != path[k][2]:
            pts.append((x0 + path[k][0] * G, y0 + path[k][1] * G))
    pts.append((x0 + path[-1][0] * G, y0 + path[-1][1] * G))
    # put the first and the last point on the box edges (the sides the search chose)
    side_of = {v: k for k, v in OUT.items()}
    sa = side_of[path[0][2]]
    sb = side_of[(path[-1][2] + 2) % 4]
    px, py, w, h = ra
    if sa == 'R':
        pts[0] = (px + w, pts[0][1])
    elif sa == 'L':
        pts[0] = (px, pts[0][1])
    elif sa == 'B':
        pts[0] = (pts[0][0], py + h)
    else:
        pts[0] = (pts[0][0], py)
    px, py, w, h = rb
    if sb == 'L':
        pts[-1] = (px, pts[-1][1])
    elif sb == 'R':
        pts[-1] = (px + w, pts[-1][1])
    elif sb == 'T':
        pts[-1] = (pts[-1][0], py)
    else:
        pts[-1] = (pts[-1][0], py + h)
    return pts


def sides_for(ra, rb):
    """Sides to try for an arrow from box ra to box rb: the natural pair first, then the others."""
    if rb[0] >= ra[0] + ra[2]:
        first = ('R', 'L')
    elif rb[0] + rb[2] <= ra[0]:
        first = ('L', 'R')
    else:
        first = ('B', 'T') if rb[1] > ra[1] else ('T', 'B')
    rest = [('R', 'L'), ('L', 'R'), ('B', 'T'), ('T', 'B'), ('R', 'T'), ('R', 'B'), ('L', 'T'), ('L', 'B'), ('B', 'L'), ('T', 'L')]
    return [first] + [s for s in rest if s != first]


def route(sc, a, b, sa='R', sb='L', pad=260):
    """Path from side `sa` of box a to side `sb` of box b (sides R, L, T, B), or None when there is no path that keeps the rules.
    sa='*' and sb='*' let the search pick the sides: the pair that faces the other box is preferred, any other side is taken when it
    saves a bend or a crossing (an arrow to a box up and to the right leaves from the top, not from the bottom and around)."""
    natural = None
    if sa == '*' or sb == '*':
        natural = sides_for(sc.boxes[a], sc.boxes[b])[0]
        sa, sb = ('RLTB' if sa == '*' else sa), ('RLTB' if sb == '*' else sb)
    for _ in range(3):
        pts = _route(sc, a, b, sa, sb, pad, natural)
        if pts:
            return pts
        pad *= 2
    # Last try: the whole canvas. A long detour (around a fork, over a frame) can leave even the largest window above; NO PATH is
    # reported only when there is truly no path that keeps the rules.
    return _route(sc, a, b, sa, sb, 10 ** 6, natural)


def _hit(rect, sc, own=None, pad=2, hop_pad=20):
    x, y, w, h = rect
    for (bx, by, bw, bh) in list(sc.boxes.values()) + sc.labels + sc.pills:
        if bx - pad < x + w and bx + bw + pad > x and by - pad < y + h and by + bh + pad > y:
            return True
    for (x0, y0, x1, y1) in getattr(sc, 'hops', ()):             # a jump arc breaks the straight stretch: keep hop_pad px clear of it
        if min(x0, x1) - hop_pad < x + w and max(x0, x1) + hop_pad > x and min(y0, y1) - hop_pad < y + h and max(y0, y1) + hop_pad > y:
            return True
    for k, pts in enumerate(sc.arrows):
        if own is not None and pts == list(own):
            continue
        for o, c, lo, hi in segments(pts):
            if (o == 'h' and y < c < y + h and lo < x + w and hi > x) or (o == 'v' and x < c < x + w and lo < y + h and hi > y):
                return True
    return False                                                 # (a label is opaque: it may sit over the dotted border of a frame)


def place_label(sc, pts, kind, w=None, h=18.0, strict=True):
    """Centre of the label for an arrow: the middle of a straight stretch where the label touches nothing. The stretch that ends in the
    arrowhead counts up to the base of the head (11px). Returns None when no stretch is long enough. A new label has the width of its word
    and 18px; an existing label of another size (a two-line one is 30px tall) passes its own w and h."""
    w = w if w is not None else draw.label_width(kind)
    best = None
    n = len(pts) - 1
    for k in range(n):
        p, q = pts[k], pts[k + 1]
        horiz = abs(p[1] - q[1]) < .01
        a, b = (p[0], q[0]) if horiz else (p[1], q[1])
        if k == n - 1:
            b -= 11 * (1 if b > a else -1)                       # the shaft ends at the base of the arrowhead
        lo, hi = min(a, b), max(a, b)
        ext = w if horiz else h
        # a jump arc on this stretch breaks it in two, like a bend: the label goes on one piece, never over the arc
        on = lambda hp: (abs(hp[1] - p[1]) < 1 and abs(hp[3] - p[1]) < 1) if horiz else (abs(hp[0] - p[0]) < 1 and abs(hp[2] - p[0]) < 1)
        cuts = sorted((min(hp[0], hp[2]), max(hp[0], hp[2])) if horiz else (min(hp[1], hp[3]), max(hp[1], hp[3]))
                      for hp in getattr(sc, 'hops', ()) if on(hp))
        cuts = [c for c in cuts if c[1] > lo and c[0] < hi]
        pieces, s = [], lo
        for c0, c1 in cuts:
            pieces.append((s, c0))
            s = c1
        pieces.append((s, hi))
        edge_seg = k in (0, n - 1) or bool(cuts)                 # a stretch at the tail, the tip or a jump needs 20px of shaft each side
        margin = (20 if strict else 8) if edge_seg else 8
        for plo, phi in pieces:
            if phi - plo < ext + 2 * margin:
                continue
            mid = (plo + phi) / 2
            slide = [mid]
            if not (k == 0 and k == n - 1 and not cuts):         # a straight arrow keeps its label in the middle
                t = plo + ext / 2 + margin
                while t <= phi - ext / 2 - margin:
                    slide.append(t)
                    t += 10
            for pos in slide:
                cx, cy = (pos, p[1]) if horiz else (p[0], pos)
                rect = (cx - w / 2, cy - h / 2, w, h)
                if _hit(rect, sc, own=pts, hop_pad=20 if strict else 8):
                    continue
                score = (phi - plo) + (30 if k == n - 1 else 0) - abs(pos - mid) * 0.5
                if best is None or score > best[0]:
                    best = (score, (cx, cy))
    return best[1] if best else None
