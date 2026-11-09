#!/usr/bin/env python3
"""Arrow router: finds an orthogonal path for one arrow in the diagram AS IT IS NOW, and a place for its label.

The router reads the current obstacles (boxes, frame borders and frame titles, labels, `new` pills, every arrow already drawn) from a
Scene, so it adapts to the crossings and the free space of the current diagram. Nothing is hard-coded for one diagram.

    sc = Scene(boxes, frames, labels, pills, arrows)      boxes {num: (x, y, w, h)}; the others lists of (x, y, w, h) / point lists
    pts = route(sc, 101, 110, 'R', 'L')                   tail on the right side of #101, tip on the left side of #110; None if no path
    lab = place_label(sc, pts, 'closed by')               (cx, cy) of the label, or None
    sc.add(pts, 'closed by', lab)                         remember both, so the next arrow sees them

Rules it keeps (SKILL.md, "Hard arrows"): a path never goes under a box (26px clear) or a label (7px clear); two horizontal arrows are
never closer than 22px (HARD_H: their 18px labels then fit one above the other with a 4px gap); two vertical arrows never closer than
14px (HARD_V), and closer than 42px (LABEL_ROOM, room for a label between them) only at a cost per step; a frame border keeps 30px; a
line is crossed only at a right angle, 30px or more from either of its ends (END_CLEAR); never turns within 40px of a box edge (so it
leaves and enters straight). Costs: a step 1, a bend 30, a crossing 35, a side other than the facing one 20, a border of a frame that
holds neither end 60, of a frame that holds an end 75 (so leaving such a frame and coming back costs 150). An arrow whose two boxes are
in the same frame is searched inside that frame first and leaves it only when no path exists inside (route() then records the pair in
sc.left_frame). It picks the exit and entry points along the two sides itself, so full sides are avoided. hops.py draws the jump arcs.
The search is A* on a 5px grid inside a window around the two boxes (the window grows when nothing is found); place_label() keeps a
label 7px from every other arrow.
"""
import heapq, math
from array import array

import draw

G = 5
BOXM, LABM, FPROX, TURN_FREE, EDGE_MARGIN = 26, 7, 30, 40, 24
HARD_H = 22         # two horizontal arrows are never closer: their labels (18px tall) then fit one above the other with a 4px gap
HARD_V = 14         # two vertical arrows are never closer (check_diag.py asks 13.5px); their labels go at different heights
LABEL_ROOM = 42     # beside a vertical arrow closer than this there is no room for a label (half a 70px label plus LABM): it may, at
NEAR_COST = 1       # NEAR_COST per 5px step, so a tight but short way still wins over a long detour around the picture
END_CLEAR = 30      # no crossing closer than this to either end of a line (a bend, a tail, a tip): it would look like a touch
TURN_COST, CROSS_COST, SIDE_COST = 30, 35, 20
FRAME_COST = 60     # per border crossed of a frame that holds neither end: going through it costs 120
JOG_COST = 60       # path_cost() only: a middle stretch shorter than 30px (the search cannot see stretch lengths)
FRAME_OWN_COST = 75 # per border crossed of a frame that holds one end or both: leaving it and coming back costs 150
OUT = {'R': 0, 'L': 2, 'B': 1, 'T': 3}               # direction numbers: 0 east, 1 south, 2 west, 3 north
DX, DY = (1, 0, -1, 0), (0, 1, 0, -1)


class Scene:
    def __init__(self, boxes, frames=(), labels=(), pills=(), arrows=(), bounds=None):
        self.bounds = bounds                               # (x0, y0, x1, y1): the area arrows may use (not the header, not the legend)
        self.boxes, self.frames = dict(boxes), list(frames)
        self.labels, self.pills = list(labels), list(pills)
        self.arrows = [list(a) for a in arrows]
        self.hops = []                                     # jump arcs already in the picture: (x0, y0, x1, y1) of each; labels keep clear of them
        self.left_frame = []                               # (a, b) of arrows that had to leave their common frame (no path inside)

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


def _reachable(goals, starts, blk, noh, nov, nt, NX, NY):
    """Can the search reach a goal at all? A breadth-first walk BACK from the goal states (cell and direction) over the same moves the
    search makes (a cell it may enter, no step along a line it must keep away from, a bend only where bending is allowed), with no costs
    and no queue order. When it reaches no start state there is no path, and the A* search, which would visit every reachable state
    before it gives up, is skipped. A failure is usually local (no room to bend before a box), so the walk back ends quickly."""
    n = NX * NY
    goal_cells = {j * NX + i for i, j in goals}
    want = {(j * NX + i) * 4 + OUT[s] for i, j, _, s in starts}
    seen = bytearray(n * 4)
    todo = [(j * NX + i) * 4 + d for (i, j), ds in goals.items() for d in ds]
    for s in todo:
        seen[s] = 1
    back = (-1, -NX, 1, NX)                      # a step in direction d (east, south, west, north) came from k + back[d]
    while todo:
        s = todo.pop()
        if s in want:
            return True
        k, nd = s >> 2, s & 3
        if (blk[k] and k not in goal_cells) or (nov if nd & 1 else noh)[k]:
            continue                             # the search never steps into k this way
        k0 = k + back[nd]
        if k0 < 0 or k0 >= n or (not nd & 1 and k0 // NX != k // NX):
            continue
        for d in (0, 1, 2, 3):                   # the state before: at k0, going d; it turned to nd unless d == nd
            if d == (nd + 2) & 3 or (d != nd and nt[k0]):
                continue
            p = k0 * 4 + d
            if not seen[p]:
                seen[p] = 1
                todo.append(p)
    return False


def _route(sc, a, b, sa, sb, pad, natural=None, inside=None, prove_none=False):
    ra, rb = sc.boxes[a], sc.boxes[b]
    bx0, by0, bx1, by1 = (int(v) for v in (sc.bounds or (0, 0, 10 ** 6, 10 ** 6)))
    x0 = max(bx0, int(min(ra[0], rb[0]) - pad))
    y0 = max(by0, int(min(ra[1], rb[1]) - pad))
    x1 = min(bx1, int(max(ra[0] + ra[2], rb[0] + rb[2]) + pad))
    y1 = min(by1, int(max(ra[1] + ra[3], rb[1] + rb[3]) + pad))
    if inside:                                   # the window is the frame itself
        x0, y0, x1, y1 = int(inside[0]) - 2 * G, int(inside[1]) - 2 * G, int(inside[0] + inside[2]) + 2 * G, int(inside[1] + inside[3]) + 2 * G
    NX, NY = (x1 - x0) // G + 1, (y1 - y0) // G + 1
    size = NX * NY
    blk, noh, nov, nt, crh, crv, sv, frh, frv = (bytearray(size) for _ in range(9))

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

    def line(arr, o, c, lo, hi, v=1):
        """Mark the one row (o 'h') or column (o 'v') of cells nearest the line at c, from lo to hi: a step across it crosses it once."""
        if o == 'h':
            j = int(round((c - y0) / G))
            i1, i2 = rng(lo, hi, x0, NX)
            if 0 <= j < NY and i1 <= i2:
                arr[j * NX + i1:j * NX + i2 + 1] = bytes([v]) * (i2 - i1 + 1)
        else:
            i = int(round((c - x0) / G))
            j1, j2 = rng(lo, hi, y0, NY)
            if 0 <= i < NX:
                for j in range(max(j1, 0), j2 + 1):
                    arr[j * NX + i] = v

    for pts in sc.arrows:
        for o, c, lo, hi in segments(pts):
            if o == 'h':                         # another horizontal keeps HARD_H: two labels fit one above the other
                mark(noh, lo - HARD_H, c - HARD_H, hi + HARD_H, c + HARD_H)
                mark(nt, lo - HARD_H, c - HARD_H, hi + HARD_H, c + HARD_H)
            else:                                # another vertical keeps HARD_V; closer than LABEL_ROOM costs per step
                mark(nov, c - HARD_V, lo - HARD_V, c + HARD_V, hi + HARD_V)
                mark(nt, c - HARD_V, lo - HARD_V, c + HARD_V, hi + HARD_V)
                mark(sv, c - LABEL_ROOM, lo, c + LABEL_ROOM, hi)
            line(crh if o == 'h' else crv, o, c, lo, hi)
            line(blk, o, c, lo - END_CLEAR, lo + END_CLEAR)        # no crossing near either end of the line
            line(blk, o, c, hi - END_CLEAR, hi + END_CLEAR)

    def holds(f, r):
        return f[0] <= r[0] and r[0] + r[2] <= f[0] + f[2] and f[1] <= r[1] and r[1] + r[3] <= f[1] + f[3]

    for f in sc.frames:
        x, y, w, h = f
        # A frame that holds one end is crossed an odd number of times, one that holds both an even number: any extra crossings come in
        # pairs, so FRAME_OWN_COST per crossing makes each excursion out of such a frame and back cost 2 * FRAME_OWN_COST. The constant
        # part (the one crossing a path must make) is the same for every path and changes nothing.
        fc = FRAME_OWN_COST if holds(f, ra) or holds(f, rb) else FRAME_COST
        for o, c, lo, hi in (('h', y, x, x + w), ('h', y + h, x, x + w), ('v', x, y, y + h), ('v', x + w, y, y + h)):
            if o == 'h':                         # a frame border keeps its full 30px: no running along it, no turning near it
                mark(noh, lo - FPROX, c - FPROX, hi + FPROX, c + FPROX)
                mark(nt, lo - FPROX, c - FPROX, hi + FPROX, c + FPROX)
            else:
                mark(nov, c - FPROX, lo - FPROX, c + FPROX, hi + FPROX)
                mark(nt, c - FPROX, lo - FPROX, c + FPROX, hi + FPROX)
            line(frh if o == 'h' else frv, o, c, lo, hi, fc)
        for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
            mark(blk, cx - FPROX, cy - FPROX, cx + FPROX, cy + FPROX)
    if inside:                                                   # stay in the common frame: everything outside it is blocked
        fx, fy, fw, fh = inside
        mark(blk, x0 - G, y0 - G, fx + 2, y1 + G)
        mark(blk, fx + fw - 2, y0 - G, x1 + G, y1 + G)
        mark(blk, x0 - G, y0 - G, x1 + G, fy + 2)
        mark(blk, x0 - G, fy + fh - 2, x1 + G, y1 + G)
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
    if prove_none and not _reachable(goals, starts, blk, noh, nov, nt, NX, NY):
        return None
    gis = [i for i, j in goals]
    gjs = [j for i, j in goals]
    gi_lo, gi_hi, gj_lo, gj_hi = min(gis), max(gis), min(gjs), max(gjs)

    # The search state is one int, (i * NY + j) * 4 + direction (it sorts like the tuple (i, j, d), so ties break the same way), and the
    # costs and back links are flat arrays indexed by it: no tuple is built or hashed per step. The obstacle layers are flat bytearrays
    # indexed by the cell j * NX + i.
    heappush, heappop = heapq.heappush, heapq.heappop
    dist = array('d', [math.inf]) * (size * 4)
    prev = array('i', [-1]) * (size * 4)
    goal_extra = {(i * NY + j) * 4 + d: extra for (i, j), ds in goals.items() for d, extra in ds.items()}   # goal state -> side cost
    goal_cells = {j * NX + i for i, j in goals}
    pq = []
    for i, j, off, s in starts:
        st = (i * NY + j) * 4 + OUT[s]
        c0 = off * 0.15 + (0 if s == nat[0] else SIDE_COST)
        if c0 < dist[st]:
            dist[st] = c0
            heappush(pq, (c0 + max(0, gi_lo - i, i - gi_hi) + max(0, gj_lo - j, j - gj_hi), c0, st))
    end = None
    done_goal = set()                                            # a goal state's cost includes its side cost: settle it when popped
    while pq:
        f, cst, st = heappop(pq)
        if cst > dist[st]:
            continue
        if st in goal_extra:
            if st in done_goal:
                end = st
                break
            done_goal.add(st)
            extra = goal_extra[st]
            if extra:
                heappush(pq, (f + extra, cst + extra, st))
                dist[st] = cst + extra
                continue
            end = st
            break
        d = st & 3
        i, j = divmod(st >> 2, NY)
        k0 = j * NX + i
        may_turn = not nt[k0]
        for nd in (0, 1, 2, 3):
            if nd == (d + 2) & 3 or (nd != d and not may_turn):
                continue
            ni, nj = i + DX[nd], j + DY[nd]
            if ni < 0 or nj < 0 or ni >= NX or nj >= NY:
                continue
            k = nj * NX + ni
            if blk[k] and k not in goal_cells:
                continue
            c2 = cst + 1
            if nd & 1:                                           # a vertical step (south, north)
                if nov[k]:
                    continue
                if crh[k]:
                    c2 += CROSS_COST
                if sv[k]:
                    c2 += NEAR_COST
                c2 += frh[k]                                     # the cost of the horizontal frame border it crosses here (0: none)
            else:                                                # a horizontal step (east, west)
                if noh[k]:
                    continue
                if crv[k]:
                    c2 += CROSS_COST
                c2 += frv[k]
            if nd != d:
                c2 += TURN_COST
            s2 = (ni * NY + nj) * 4 + nd
            if c2 < dist[s2]:
                dist[s2] = c2
                prev[s2] = st
                heappush(pq, (c2 + max(0, gi_lo - ni, ni - gi_hi) + max(0, gj_lo - nj, nj - gj_hi), c2, s2))
    if end is None:
        return None
    path = [end]
    while prev[path[-1]] >= 0:
        path.append(prev[path[-1]])
    path = [((s >> 2) // NY, (s >> 2) % NY, s & 3) for s in reversed(path)]
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
    return unjog(pts, ra, rb, sa, sb)


def unjog(pts, ra, rb, sa, sb, short=2 * G):
    """Remove a jog shorter than `short` next to either end (the grid can leave a 5px step before a goal cell): the end point moves onto
    the line of the stretch before the jog, when that point is still on the same side of its box, 20px from its corners."""
    def on_side(r, side, v):
        lo, hi = _side_cells(r, side, 20)
        return lo - .01 <= v <= hi + .01
    for end in (-1, 0):
        if len(pts) < 4:
            break
        k = len(pts) - 1 if end == -1 else 0
        j, i = (k - 1, k - 2) if end == -1 else (k + 1, k + 2)       # the jog runs from pts[i] to pts[j]; pts[j] to pts[k] enters the box
        side, r = (sb, rb) if end == -1 else (sa, ra)
        if side in 'LR' and abs(pts[j][0] - pts[i][0]) < .01 and 0 < abs(pts[j][1] - pts[i][1]) < short and on_side(r, side, pts[i][1]):
            pts[k] = (pts[k][0], pts[i][1])
            del pts[j]
            if end == -1:
                del pts[-2]
            else:
                del pts[1]
        elif side in 'TB' and abs(pts[j][1] - pts[i][1]) < .01 and 0 < abs(pts[j][0] - pts[i][0]) < short and on_side(r, side, pts[i][0]):
            pts[k] = (pts[i][0], pts[k][1])
            del pts[j]
            if end == -1:
                del pts[-2]
            else:
                del pts[1]
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


def common_frame(sc, a, b):
    """The smallest frame that holds both boxes, or None."""
    def holds(f, r):
        return f[0] <= r[0] and r[0] + r[2] <= f[0] + f[2] and f[1] <= r[1] and r[1] + r[3] <= f[1] + f[3]
    ra, rb = sc.boxes[a], sc.boxes[b]
    both = [f for f in sc.frames if holds(f, ra) and holds(f, rb)]
    return min(both, key=lambda f: f[2] * f[3]) if both else None


def route(sc, a, b, sa='R', sb='L', pad=260):
    """Path from side `sa` of box a to side `sb` of box b (sides R, L, T, B), or None when there is no path that keeps the rules.
    sa='*' and sb='*' let the search pick the sides: the pair that faces the other box is preferred, any other side is taken when it
    saves a bend or a crossing (an arrow to a box up and to the right leaves from the top, not from the bottom and around)."""
    natural = None
    if sa == '*' or sb == '*':
        natural = sides_for(sc.boxes[a], sc.boxes[b])[0]
        sa, sb = ('RLTB' if sa == '*' else sa), ('RLTB' if sb == '*' else sb)
    fr = common_frame(sc, a, b)
    if fr:                                       # both boxes in one frame: the arrow stays inside it (an almost hard rule)
        pts = _route(sc, a, b, sa, sb, 10 ** 6, natural, inside=fr)
        if pts:
            return pts
        if hasattr(sc, 'left_frame'):
            sc.left_frame.append((a, b))
    for _ in range(3):
        pts = _route(sc, a, b, sa, sb, pad, natural)
        if pts:
            return pts
        pad *= 2
    # Last try: the whole canvas. A long detour (around a fork, over a frame) can leave even the largest window above; NO PATH is
    # reported only when there is truly no path that keeps the rules.
    return _route(sc, a, b, sa, sb, 10 ** 6, natural, prove_none=True)


def _hit(rect, sc, own=None, pad=2, hop_pad=20, g=LABM):
    """Does a label at rect touch a box, a label, a pill (pad), a jump arc (hop_pad) or come closer than g to another arrow?"""
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
            if (o == 'h' and y - g < c < y + h + g and lo < x + w + g and hi > x - g) or \
                (o == 'v' and x - g < c < x + w + g and lo < y + h + g and hi > y - g):
                return True
    return False                                                 # (a label is opaque: it may sit over the dotted border of a frame)


def place_label(sc, pts, kind, w=None, h=18.0, strict=True):
    """Centre of the label for an arrow: the middle of a straight stretch where the label touches nothing. The stretch that ends in the
    arrowhead counts up to the base of the head (11px). Returns None when no stretch is long enough. A new label has the width of its word
    and 18px; an existing label of another size (a two-line one is 30px tall) passes its own w and h."""
    w = w if w is not None else draw.label_width(kind)
    best = None
    own_pts = pts
    pts = straight([tuple(x) for x in pts])                     # the points a removed jump arc left inside a straight run go
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
        whole = n == 1                                           # a straight arrow: its label belongs in the middle of the shaft
        for plo, phi in pieces:
            if phi - plo < ext + 2 * margin:
                continue
            mid = (plo + phi) / 2
            near = min(max((lo + hi) / 2, plo + ext / 2 + margin), phi - ext / 2 - margin)   # the place in this piece nearest that middle
            slide = [mid, near]
            if not (whole and not cuts):
                t = plo + ext / 2 + margin
                while t <= phi - ext / 2 - margin:
                    slide.append(t)
                    t += 10
            for pos in slide:
                cx, cy = (pos, p[1]) if horiz else (p[0], pos)
                rect = (cx - w / 2, cy - h / 2, w, h)
                if _hit(rect, sc, own=own_pts, hop_pad=20 if strict else 8):
                    continue
                if whole:                                        # check_diag.py fails a straight arrow's label off its middle
                    score = -abs(pos - (lo + hi) / 2)
                else:
                    score = (phi - plo) + (30 if k == n - 1 else 0) - abs(pos - mid) * 0.5
                if best is None or score > best[0]:
                    best = (score, (cx, cy))
    return best[1] if best else None


def straight(pts):
    """The corners of a path: points inside a straight run (the ends of a removed jump arc) are dropped."""
    out = [pts[0]]
    for p, q in zip(pts[1:], pts[2:]):
        o = out[-1]
        if (abs(o[0] - p[0]) < .01 and abs(p[0] - q[0]) < .01) or (abs(o[1] - p[1]) < .01 and abs(p[1] - q[1]) < .01):
            continue
        out.append(p)
    return out + [pts[-1]] if len(pts) > 1 else out


def _crossings(segs, other):
    n = 0
    for o, c, lo, hi in segs:
        for o2, c2, lo2, hi2 in other:
            if o != o2 and lo + .5 < c2 < hi - .5 and lo2 + .5 < c < hi2 - .5:
                n += 1
    return n


def path_cost(sc, pts, a, b):
    """What the search charges for a drawn path, without the per-step closeness and side costs: 1 per 5px, TURN_COST per bend,
    CROSS_COST per crossing with another arrow of sc, and the frame border costs; and JOG_COST per jog shorter than 30px. Used to compare an old path with a new one."""
    p = straight([tuple(x) for x in pts])
    segs = segments(p)
    cost = sum(hi - lo for _, _, lo, hi in segs) / G + TURN_COST * (len(p) - 2)
    cost += JOG_COST * sum(1 for _, _, lo, hi in segs[1:-1] if hi - lo < 30)      # a jog shorter than 30px (SKILL.md: never leave one)
    for q in sc.arrows:
        if straight([tuple(x) for x in q]) != p:
            cost += CROSS_COST * _crossings(segs, segments(straight([tuple(x) for x in q])))
    ra, rb = sc.boxes[a], sc.boxes[b]
    for f in sc.frames:
        x, y, w, h = f
        own = any(f[0] <= r[0] and r[0] + r[2] <= f[0] + f[2] and f[1] <= r[1] and r[1] + r[3] <= f[1] + f[3] for r in (ra, rb))
        border = [('h', y, x, x + w), ('h', y + h, x, x + w), ('v', x, y, y + h), ('v', x + w, y, y + h)]
        cost += (FRAME_OWN_COST if own else FRAME_COST) * _crossings(segs, border)
    return cost
