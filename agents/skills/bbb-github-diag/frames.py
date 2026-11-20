#!/usr/bin/env python3
"""A frame grows downward, and what lies below it moves down by the same amount, like a row inserted in a table. This is the one
operation that makes room in a frame; model.route_arrows (used by add_nodes.py, move.py, reroute.py and build.py) and add_nodes.py's
placement call it.

    push = frames.grow(svg_text, frame_rect, dy)
    push.text       the diagram with the frame grown and everything below moved
    push.cut        line indexes of the arrows that must be routed again (model.route_arrows takes them out and routes them)

The rule (a cascade over the frames and the boxes, each a rigid block, everything moved by the same dy):
1. the frame grows dy at its bottom, and so does every frame that holds it;
2. a frame or a box moves down when its top is at or below the old bottom of a frame or box that grew or moved and the two overlap
   horizontally (they share more than TOUCH px of x); a frame that moves carries everything inside it; the boxes of the grown frame
   (members_of: its own boxes, one that sticks out at its bottom, one it grows to hold) never move;
3. repeat until nothing more moves.
Nothing moves sideways and nothing moves up, so the gaps between frames stay as they were and two frames that did not overlap before
do not overlap after. The canvas grows when the lowest thing moved needs it (CANVAS_BOTTOM px below it).

Arrows: one whose two ends are on moved boxes moves with them, jump arcs and label included. One with a single end on a moved box is
cut: it must be routed again. One with neither end moved is cut too when a stretch of it meets the old or the new place of anything
moved, or the band the frame grew by: its route ran through what moved, or now runs through what came. The others do not change.
Lines are edited in place, never added or removed, so line indexes the caller holds stay valid. No arrow is routed here.
"""
import math, os, re, sys, tempfile, time
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typing import NamedTuple
import collapse, draw

TOUCH = 1.0              # px: two blocks that share no more than this of x (or of y) do not touch
CANVAS_BOTTOM = 80       # px of page below the lowest frame or box (collapse.py keeps the same)
BOTTOM_PAD = 30          # px a frame keeps below its lowest box when it grows to hold one (add_nodes.py, move.py)
ATTACH = 3.0             # px: an arrow end this close to a box side is on that box (collapse.py's attach)
LEFT_EDGE = 30           # px: nothing is pushed further left than this; the picture moves right instead (translate)


class Push(NamedTuple):
    text: str
    moved: frozenset         # numbers of the boxes that moved down
    frames: tuple            # (old rect, new rect) of every frame that grew or moved
    cut: tuple               # line indexes of the arrows to route again


def _rect(u):
    return u['x'], u['y'], u['w'], u['h']


def _holds(f, r):
    return f[0] <= r[0] and r[0] + r[2] <= f[0] + f[2] and f[1] <= r[1] and r[1] + r[3] <= f[1] + f[3]


def _over_x(r, s):
    return r[0] < s[0] + s[2] - TOUCH and s[0] < r[0] + r[2] - TOUCH


def _below(r, s):
    """Is r at or below the bottom of s, and do they overlap horizontally?"""
    return r[1] >= s[1] + s[3] - TOUCH and _over_x(r, s)


def _meets(seg, r):
    """Does an orthogonal stretch (o, c, lo, hi) meet the inside of rectangle r?"""
    o, c, lo, hi = seg
    x, y, w, h = r
    if o == 'h':
        return y < c < y + h and lo < x + w and hi > x
    return x < c < x + w and lo < y + h and hi > y


def _segments(pts):
    out = []
    for p, q in zip(pts, pts[1:]):
        if abs(p[1] - q[1]) < .01 and abs(p[0] - q[0]) > .01:
            out.append(('h', p[1], min(p[0], q[0]), max(p[0], q[0])))
        elif abs(p[0] - q[0]) < .01 and abs(p[1] - q[1]) > .01:
            out.append(('v', p[0], min(p[1], q[1]), max(p[1], q[1])))
    return out


def _end_box(p, boxes):
    """The box whose side the point p lies on (ATTACH px), or None."""
    px, py = p
    for n, (x, y, w, h) in boxes.items():
        if (y - ATTACH <= py <= y + h + ATTACH and (abs(px - x) <= ATTACH or abs(px - x - w) <= ATTACH)) or \
                (x - ATTACH <= px <= x + w + ATTACH and (abs(py - y) <= ATTACH or abs(py - y - h) <= ATTACH)):
            return n
    return None


def members_of(frame, boxes, also=()):
    """The boxes that belong to `frame` and so never move when it grows: those in `also` (a box the frame grows to hold, below its
    bottom border) and every box whose top is inside the frame and whose sides are within it (one that sticks out at the bottom)."""
    x, y, w, h = frame
    return set(also) | {n for n, r in boxes.items() if x <= r[0] and r[0] + r[2] <= x + w and y <= r[1] < y + h}


def cascade(frames, boxes, grown_frame, members=()):
    """The blocks the rule moves when grown_frame grows (module docstring, steps 1 to 3): (indexes of the frames that grow, indexes
    of the frames that move, numbers of the boxes that move). frames: [rect]; boxes: {num: rect}; members: boxes of the grown frame
    (members_of), which never move."""
    grow = {k for k, f in enumerate(frames) if _holds(f, grown_frame)}
    move_f, move_b = set(), set(members_of(grown_frame, boxes, members))
    keep = set(move_b)
    pushers = [frames[k] for k in grow]
    changed = True
    while changed:
        changed = False
        for k, f in enumerate(frames):
            if k in grow or k in move_f:
                continue
            if any(_below(f, p) for p in pushers) or any(_holds(frames[m], f) for m in move_f):
                move_f.add(k)
                pushers.append(f)
                changed = True
        for n, r in boxes.items():
            if n in move_b:
                continue
            if any(_below(r, p) for p in pushers) or any(_holds(frames[m], r) for m in move_f):
                move_b.add(n)
                pushers.append(r)
                changed = True
    return grow, move_f, move_b - keep


# What a push keeps between two blocks it brings closer (cascade_gap), by their kinds: f frame, b box, a arrow stretch (in a corridor),
# l label. A gap already smaller than this is kept as it is.
KEEP = {'ff': 34,        # layout.BAND_GAP: two frames of one column
        'bb': 28, 'bf': 28,  # push.GAP: a box and the next box, or a frame border
        'ab': 26,        # route.BOXM: an arrow and a box
        'aa': 22,        # route.HARD_H: two parallel arrows (and their labels)
        'af': 10, 'fl': 10, 'bl': 10, 'al': 10, 'll': 10}   # an arrow or a label and a frame border (_step_free's 10px), labels


def cascade_gap(frames, blocks, grown_frame, d, members=(), kind=lambda key: 'b'):
    """cascade() with free space: the grown frame's bottom moves d, and a block below something that moved moves only by what the gap
    between them does not absorb (the gap may shrink to KEEP[kinds], never below; a gap already smaller stays). So a frame far below
    does not move at all, and one a little below moves a little. A block inside a frame that moved moves with it (rigidly).
    blocks {key: rect}, kind(key) -> f, b, a or l (KEEP). Returns (indexes of the frames that grow, {frame index: px it moves},
    {block key: px it moves}); only blocks that move are in the dicts."""
    grow = {k for k, f in enumerate(frames) if _holds(f, grown_frame)}
    keep = set(members_of(grown_frame, {n: r for n, r in blocks.items() if kind(n) == 'b'}, members))
    pushers = [(frames[k], float(d), 'f') for k in grow]
    move_f, move_b = {}, {}
    todo = [(f[1], 0, ('f', k)) for k, f in enumerate(frames) if k not in grow] + \
           [(r[1], 1, ('x', n)) for n, r in blocks.items() if n not in keep]
    for _, _, (t, key) in sorted(todo, key=lambda u: (u[0], u[1])):        # top first: every pusher before what lies below it
        r, kd = (frames[key], 'f') if t == 'f' else (blocks[key], kind(key))
        amt = 0.0
        for p, pa, pk in pushers:
            if _below(r, p):
                gap = r[1] - p[1] - p[3]
                amt = max(amt, pa - max(0.0, gap - KEEP[''.join(sorted(kd + pk))]))
        carried = [a for m, a in move_f.items() if m != key and _holds(frames[m], r)]
        if carried:
            amt = max(amt, max(carried))
        if amt > 0:
            (move_f if t == 'f' else move_b)[key] = amt
            pushers.append((r, amt, kd))
    return grow, move_f, move_b


def _arrow_points(line):
    d = line.split('"')[1]
    return [(float(a), float(b)) for a, b in re.findall(r'(-?[\d.]+),(-?[\d.]+)', re.sub(r'A[^L]*', '', d))]


def _shift_path(line, dx, dy):
    """The arrow line with every point of its path moved by dx, dy (the arc flags and radii have no comma, so they stay)."""
    d = line.split('"')[1]
    nd = re.sub(r'(-?[\d.]+),(-?[\d.]+)', lambda m: '%s,%s' % (collapse.fmt(float(m.group(1)) + dx), collapse.fmt(float(m.group(2)) + dy)), d)
    return line.replace('d="%s"' % d, 'd="%s"' % nd, 1)


def labels_of(lines, idxs):
    """{arrow line index: range of the line indexes of its label} for the arrows on the lines idxs: a label of its word centred on one
    of its stretches (an arrow with none is left out). One pass over the labels for all the arrows."""
    import svgmeta
    labels = [(j, lab) for j, lab in ((j, draw.label_at(lines, j)) for j in range(len(lines)) if lines[j].startswith('<rect')) if lab]
    out, taken = {}, set()
    for i in idxs:
        at = svgmeta.arrow_of(lines[i])
        segs = _segments(_arrow_points(lines[i]))
        for j, lab in labels:
            if j in taken or (at is not None and lab[5] != at[2]):
                continue
            cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
            if any((o == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1)
                   for o, c, lo, hi in segs):
                out[i] = range(j, j + 1 + lab[4])
                taken.add(j)
                break
    return out


# A side, as a turn of the picture that makes it the bottom (so one cascade serves the four sides), and the way things move there.
_TURN = {'bottom': lambda r: r, 'top': lambda r: (r[0], -r[1] - r[3], r[2], r[3]),
         'right': lambda r: (r[1], r[0], r[3], r[2]), 'left': lambda r: (r[1], -r[0] - r[2], r[3], r[2])}
_WAY = {'bottom': (0, 1), 'top': (0, -1), 'right': (1, 0), 'left': (-1, 0)}


def _grown(r, side, d):
    """Rectangle r grown d px on `side`."""
    x, y, w, h = r
    return {'bottom': (x, y, w, h + d), 'top': (x, y - d, w, h + d), 'right': (x, y, w + d, h), 'left': (x - d, y, w + d, h)}[side]


def _set_rect(line, r):
    for k, v in zip(('x', 'y', 'width', 'height'), r):
        line = re.sub(r'\b%s="[\d.-]+"' % k, '%s="%s"' % (k, collapse.fmt(v)), line, count=1)
    return line


def grow(text, frame, d, members=(), side='bottom'):
    """Grow the frame whose rectangle is `frame` (x, y, w, h) by d px on `side` (bottom, top, left, right) and push away what lies
    on that side (module docstring: the cascade, with the picture turned so that the side is the bottom). members: boxes that belong
    to the frame although they lie outside it (a box it grows to hold); they stay where they are. When the push would take something
    past the top or the left edge of the picture, the whole picture moves the other way instead (translate). Returns a Push."""
    lines, box, pop, fr = collapse.parse(text)
    rects = [_rect(f) for f in fr]
    hit = [k for k, r in enumerate(rects) if all(abs(a - b) < .5 for a, b in zip(r, frame))]
    if not hit:
        raise ValueError('no frame at %s' % (frame,))
    boxes = {n: _rect(b) for n, b in box.items()}
    turn = _TURN[side]
    grow_k, move_k, move_b = cascade([turn(r) for r in rects], {n: turn(r) for n, r in boxes.items()}, turn(rects[hit[0]]), members)
    dx, dy = (d * v for v in _WAY[side])
    out = list(lines)
    changes = []
    for k in grow_k | move_k:
        f, old = fr[k], rects[k]
        new = (old[0] + dx, old[1] + dy, old[2], old[3]) if k in move_k else _grown(old, side, d)
        out[f['rl']] = _set_rect(out[f['rl']], new)
        out[f['tl']] = collapse.shift_line(out[f['tl']], new[0] - old[0], new[1] - old[1])
        changes.append((old, new))
    for n in move_b:
        b = box[n]
        for a, z in [(b['a'], b['b'])] + ([pop[n]] if n in pop else []):
            for i in range(a, z + 1):
                out[i] = collapse.shift_line(out[i], dx, dy)
    # what changed place: old and new rectangles of the moved blocks, and the band each grown frame gained
    moved = [rects[k] for k in move_k] + [boxes[n] for n in move_b]
    swept = moved + [(r[0] + dx, r[1] + dy, r[2], r[3]) for r in moved]
    swept += [_band(rects[k], side, d) for k in grow_k]
    cut, rigid = [], []
    for i, ln in enumerate(lines):
        if not (ln.startswith('<path d="M') and 'marker-end' in ln):
            continue
        pts = _arrow_points(ln)
        ends = {_end_box(pts[0], boxes), _end_box(pts[-1], boxes)}
        if None in ends:
            continue                                     # an arrow that ends on no box is the checker's to report
        if ends <= move_b:
            out[i] = _shift_path(ln, dx, dy)
            rigid.append(i)
        elif ends & move_b or any(_meets(sg, r) for sg in _segments(pts) for r in swept):
            cut.append(i)
    for rng in labels_of(lines, rigid).values():
        for j in rng:
            out[j] = collapse.shift_line(out[j], dx, dy)
    res = '\n'.join(out)
    new_rects = [nw for _, nw in changes] + [r for k, r in enumerate(rects) if k not in grow_k | move_k]
    new_boxes = [(r[0] + dx, r[1] + dy, r[2], r[3]) if n in move_b else r for n, r in boxes.items()]
    top = min([r[1] for r in rects] + [r[1] for r in boxes.values()])          # the picture's top and left edges stay where they were
    left = min([r[0] for r in rects] + [r[0] for r in boxes.values()] + [LEFT_EDGE])
    ox = max(0.0, left - min(r[0] for r in new_rects + new_boxes))
    oy = max(0.0, top - min(r[1] for r in new_rects + new_boxes))
    if ox or oy:
        res = translate(res, ox, oy)
        changes = [(old, (nw[0] + ox, nw[1] + oy, nw[2], nw[3])) for old, nw in changes]
    lowest = max(r[1] + r[3] for r in new_rects + new_boxes) + oy
    rightest = max(r[0] + r[2] for r in new_rects + new_boxes) + ox
    res = set_canvas_height(res, lowest + CANVAS_BOTTOM)
    res = set_canvas_width(res, rightest + CANVAS_BOTTOM)
    return Push(res, frozenset(move_b), tuple(changes), tuple(cut))


def _band(r, side, d):
    """The band frame r gains when it grows d px on `side`."""
    x, y, w, h = r
    return {'bottom': (x, y + h, w, d), 'top': (x, y - d, w, d), 'right': (x + w, y, d, h), 'left': (x - d, y, d, h)}[side]


def translate(text, dx, dy):
    """Move the whole picture (frames, boxes, pop-ups, arrows, labels; the legend sideways only) by dx, dy and grow the canvas by
    as much: what a push does when it would go past the top or the left edge. The header stays."""
    lines, box, pop, fr = collapse.parse(text)
    out = list(lines)
    rows = {k for f in fr for k in (f['rl'], f['tl'])}
    rows |= {k for b in box.values() for k in range(b['a'], b['b'] + 1)}
    rows |= {k for a, z in pop.values() for k in range(a, z + 1)}
    for j in range(len(lines)):
        lab = draw.label_at(lines, j)
        if lab:
            rows |= set(range(j, j + 1 + lab[4]))
    for k in rows:
        out[k] = collapse.shift_line(out[k], dx, dy)
    for i, ln in enumerate(lines):
        if ln.startswith('<path d="M') and 'marker-end' in ln:
            out[i] = _shift_path(ln, dx, dy)
    a = next((i for i, l in enumerate(out) if l == '<!--legend-->'), None)
    if a is not None and dx:
        for i in range(a + 1, out.index('<!--/legend-->')):
            out[i] = collapse.shift_line(out[i], dx, 0)
    m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', text)
    res = '\n'.join(out)
    res = set_canvas_height(res, int(m.group(2)) + dy) if dy else res
    return set_canvas_width(res, int(m.group(1)) + dx) if dx else res


PROFILES = ('linear', 'graded', 'edge')


def axis_map(lo, hi, grow_lo, grow_hi, profile='linear'):
    """The map of one axis from [lo, hi] onto [lo - grow_lo, hi + grow_hi], as a function. With u = (x - lo) / (hi - lo):
    linear: x' = lo' + u * size' (an anchored stretch when one side does not grow, a balloon when both grow alike);
    graded ("inflation" toward the growing side), with k = size' / size - 1: x' = lo + (x - lo) * (1 + k * u) toward hi, or the
    mirror toward lo; the stretch is 1 at the fixed side and grows smoothly to 1 + 2k at the growing side (linear when both sides
    grow). Every such map is continuous and strictly increasing, and its stretch is 1 or more everywhere, so no gap shrinks."""
    lo2, size, size2 = lo - grow_lo, hi - lo, hi - lo + grow_lo + grow_hi
    k = size2 / size - 1
    if profile == 'linear' or grow_lo == grow_hi:
        g = lambda u: u * (1 + k)
    elif grow_hi > grow_lo:
        g = lambda u: u * (1 + k * u)
    else:
        g = lambda u: (1 + k) - (1 - u) * (1 + k * (1 - u))
    return lambda x: lo2 + size * g((x - lo) / size)


STATS = {'inflate': 0, 'inflate_secs': 0.0}             # inflate() calls and their seconds (scripts print them)
JOG_ROOM = (26, 14)      # px a corridor step keeps from a box (route.BOXM) and from a parallel arrow (route.HARD_V)


def inflate(text, frame, grow_by, profile='linear'):
    """Inflate a frame: frames.inflate, one transformation that grows the area a frame offers and routes nothing.

    grow_by {side: px} for any of left, right, top, bottom: one side, two, or all four (a balloon). The frame grows by those
    amounts. Inside it, one map per axis takes the old frame onto the new one (axis_map): profile linear (an anchored stretch, or
    a balloon), graded (the stretch grows toward the side that grows) or edge (no stretch: the content stays and the room opens at
    the border). Box centres and label centres follow the map, box sizes stay, every arrow point inside follows it.
    Everything else moves rigidly: a cascade with free space (cascade_gap) runs once per side that grows, with the picture turned so
    that the side is the bottom; each frame, box, corridor stretch and corridor label it reaches moves only by the part of that
    side's amount that its gap does not absorb (KEEP), so what lies far away does not move. A corridor stretch across the push moves
    whole, with its label (_corridor_groups), so it stays straight. So a neighbouring frame keeps its exact internal geometry: it is
    translated, or left alone.
    An arrow end snaps back onto its box side (its last stretch changes length; when its place along the side would fall outside the
    box, it and the point before it move together). Where a stretch joins two parts that moved differently (an arrow between two
    frames, or across the border), it is slid square with no new bend when one of its ends can move along its neighbour stretch
    (_slide), else it takes one step (a jog) at a free point of the stretch that lies in a corridor: JOG_ROOM from boxes and parallel
    arrows. Only an arrow with neither is cut (Push.cut), to be routed again.

    Invariants: inside the frame the map is continuous and strictly increasing per axis, with a stretch of 1 or more, so every
    horizontal stretch stays horizontal and every vertical one vertical, the same pairs of stretches cross, and no gap shrinks;
    outside, each part is translated as a whole; no box changes size. Jump arcs are dropped (hops.py redraws them). Push.frames:
    (old, new) of every frame that grew or moved; Push.moved: the boxes that moved; STATS['jogs']: the arrows of this call that got
    a corridor step. A frame inside the inflated one follows the map. Takes milliseconds."""
    t0 = time.perf_counter()
    lines, box, pop, fr = collapse.parse(text)
    rects = [_rect(f) for f in fr]
    k0 = next(k for k, r in enumerate(rects) if all(abs(a - b) < .5 for a, b in zip(r, frame)))
    boxes = {n: _rect(b) for n, b in box.items()}
    inside = {n for n, r in boxes.items() if _holds(frame, r)}
    g = {sd: max(0.0, float(math.ceil(grow_by.get(sd, 0)))) for sd in ('left', 'right', 'top', 'bottom')}
    arrows = [i for i, ln in enumerate(lines) if ln.startswith('<path d="M') and 'marker-end' in ln]
    paths = {i: _straight(_arrow_points(lines[i])) for i in arrows}
    labels = labels_of(lines, arrows)
    in_any = lambda p: any(_holds(r, (p[0], p[1], 0, 0)) for r in rects)
    corridor = {(i, j): (x, y, 0.0, 0.0) for i in arrows for j, (x, y) in enumerate(paths[i]) if not in_any((x, y))}
    centres = {}                                           # label line -> its centre; one in a corridor moves like a corridor point
    for j in range(len(lines)):
        lab = draw.label_at(lines, j)
        if lab:
            centres[j] = (lab[0] + lab[2] / 2, lab[1] + lab[3] / 2)
            if not in_any(centres[j]):
                corridor[('label', j)] = centres[j] + (0.0, 0.0)
    # the pushes: one cascade per side that grows; frames, boxes and corridor points as blocks, each moved by that side's amount
    # each block moves only by what its gap does not absorb (cascade_gap), and a corridor stretch across the push moves whole
    disp_f, disp_b, disp_p = {}, {}, {}
    grown = set()
    lab_rect = {j: draw.label_at(lines, j)[:4] for j in centres}
    owner0 = {j: i for i, rng in labels.items() for j in rng}
    add = lambda dic, key, a, way: dic.__setitem__(key, (dic.get(key, (0, 0))[0] + a * way[0], dic.get(key, (0, 0))[1] + a * way[1]))
    for side, d in g.items():
        if d <= 0:
            continue
        turn = _TURN[side]
        groups = _corridor_groups(paths, corridor, centres, lab_rect, owner0, side in ('top', 'bottom'))
        blocks = dict(boxes)
        blocks.update({('g', gi): rect for gi, (rect, _, _) in enumerate(groups)})
        kinds = {('g', gi): kd for gi, (_, _, kd) in enumerate(groups)}
        gk, mf, mb = cascade_gap([turn(r) for r in rects], {key: turn(r) for key, r in blocks.items()}, turn(frame), d, inside,
                                 kind=lambda key: kinds.get(key, 'b'))
        grown |= {(kk, side) for kk in gk}
        for kk, a in mf.items():
            add(disp_f, kk, a, _WAY[side])
        for key, a in mb.items():
            for member in (groups[key[1]][1] if key in kinds else [key]):
                add(disp_p if key in kinds else disp_b, member, a, _WAY[side])
    new_rects = []
    for kk, r in enumerate(rects):
        nr = r
        for side in ('left', 'right', 'top', 'bottom'):
            if (kk, side) in grown:
                nr = _grown(nr, side, g[side])
        dxy = disp_f.get(kk, (0, 0))
        new_rects.append((nr[0] + dxy[0], nr[1] + dxy[1], nr[2], nr[3]))
    flat = profile == 'edge'
    mx = (lambda v: v) if flat else axis_map(frame[0], frame[0] + frame[2], g['left'], g['right'], profile)
    my = (lambda v: v) if flat else axis_map(frame[1], frame[1] + frame[3], g['top'], g['bottom'], profile)
    for kk, r in enumerate(rects):                         # a frame inside the inflated one follows the map, like its boxes
        if kk != k0 and _holds(frame, r):
            new_rects[kk] = (mx(r[0]), my(r[1]), mx(r[0] + r[2]) - mx(r[0]), my(r[1] + r[3]) - my(r[1]))

    def where(x, y, key=None):
        """The new place of a point: the map inside the frame, else the move of the frame (or corridor block) it is in."""
        if _holds(frame, (x, y, 0, 0)):
            return mx(x), my(y)
        if key is not None and key in corridor:
            dxy = disp_p.get(key, (0, 0))
            return x + dxy[0], y + dxy[1]
        holders = [kk for kk, r in enumerate(rects) if _holds(r, (x, y, 0, 0))]
        kk = min(holders, key=lambda kk: rects[kk][2] * rects[kk][3]) if holders else None
        dxy = disp_f.get(kk, (0, 0)) if kk is not None else (0, 0)
        for anc in holders:                                # inside a frame that grew (one that holds the inflated frame)
            if anc in disp_f:
                dxy = disp_f[anc]
        return x + dxy[0], y + dxy[1]
    out = list(lines)
    news = {}
    for n, r in boxes.items():
        if n in inside:
            cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
            news[n] = (mx(cx) - r[2] / 2, my(cy) - r[3] / 2, r[2], r[3])
        else:
            holders = [kk for kk, fr_ in enumerate(rects) if _holds(fr_, r)]
            dxy = disp_b.get(n) or next((disp_f[kk] for kk in holders if kk in disp_f), (0, 0))
            news[n] = (r[0] + dxy[0], r[1] + dxy[1], r[2], r[3])
    # a push past the top or the left edge of the picture: the whole picture moves the other way instead (by ox, oy)
    top = min(r[1] for r in rects + list(boxes.values()))
    left = min([r[0] for r in rects + list(boxes.values())] + [LEFT_EDGE])
    ox = max(0.0, left - min(r[0] for r in new_rects + list(news.values())))
    oy = max(0.0, top - min(r[1] for r in new_rects + list(news.values())))
    new_rects = [(r[0] + ox, r[1] + oy, r[2], r[3]) for r in new_rects]
    news = {n: (r[0] + ox, r[1] + oy, r[2], r[3]) for n, r in news.items()}
    place = where
    where = lambda x, y, key=None: tuple(v + o for v, o in zip(place(x, y, key), (ox, oy)))
    for n, r in boxes.items():
        ddx, ddy = news[n][0] - r[0], news[n][1] - r[1]
        if ddx or ddy:
            b = box[n]
            for a, z in [(b['a'], b['b'])] + ([pop[n]] if n in pop else []):
                for i in range(a, z + 1):
                    out[i] = collapse.shift_line(out[i], ddx, ddy)
    changes = []
    for kk, f in enumerate(fr):
        old, new = rects[kk], new_rects[kk]
        if new != old:
            out[f['rl']] = _set_rect(out[f['rl']], new)
            out[f['tl']] = collapse.shift_line(out[f['tl']], new[0] - old[0], new[1] - old[1])
            changes.append((old, new))
    cut, jogged = [], []
    drawn_v = []                                           # vertical stretches already placed, for the step's room test
    new_paths = {}
    for i in arrows:
        pts = paths[i]
        ends = [_end_box(pts[0], boxes), _end_box(pts[-1], boxes)]
        moved = [where(x, y, (i, j)) for j, (x, y) in enumerate(pts)]
        if None not in ends:
            moved = _snap(moved, [boxes[e] for e in ends], [news[e] for e in ends], pts, strict=False)
        new_paths[i] = moved
    for i in arrows:
        res = _with_steps(new_paths[i], paths[i], list(news.values()), new_rects, new_paths, i)
        if res is None:
            cut.append(i)
            continue
        if len(res) > len(new_paths[i]):
            jogged.append(i)
        new_paths[i] = res
        d = lines[i].split('"')[1]
        out[i] = lines[i].replace('d="%s"' % d, 'd="M%s"' % ' L'.join('%s,%s' % (collapse.fmt(x), collapse.fmt(y)) for x, y in res), 1)
    del drawn_v
    left_alone = {j for i in cut for j in labels.get(i, ())}   # a cut arrow keeps its path and its label for take_out
    owner = {j: i for i, rng in labels.items() for j in rng}
    for j, (cx, cy) in centres.items():                    # every other label: its centre goes where its point goes
        lab = draw.label_at(lines, j)
        if lab and j not in left_alone:
            nx, ny = where(cx, cy, ('label', j))
            if owner.get(j) in jogged:                     # its stretch took a step: onto the nearest point of the new path
                nx, ny = _nearest(new_paths[owner[j]], nx, ny)
            for kk in range(j, j + 1 + lab[4]):
                out[kk] = collapse.shift_line(out[kk], nx - cx, ny - cy)
    res = '\n'.join(out)
    lowest = max(r[1] + r[3] for r in new_rects + list(news.values()))
    rightest = max(r[0] + r[2] for r in new_rects + list(news.values()))
    leg = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="14" fill="#fbfaf6"', res)
    if leg and float(leg.group(1)) < rightest + 25 and float(leg.group(2)) < 400:
        res = _shift_legend(res, rightest + 25 - float(leg.group(1)))
        rightest = max(rightest, rightest + 25 + float(leg.group(3)))
    if ox:
        res = _shift_legend(res, ox)
    res = set_canvas_width(set_canvas_height(res, lowest + CANVAS_BOTTOM), rightest + CANVAS_BOTTOM)
    STATS['inflate'] += 1
    STATS['inflate_secs'] += time.perf_counter() - t0
    STATS['jogs'] = len(jogged)
    return Push(res, frozenset(n for n in boxes if news[n] != boxes[n]), tuple(changes), tuple(cut))


def _corridor_groups(paths, corridor, centres, lab_rect, owner, across_y):
    """The corridor points and corridor labels of the arrows (inflate's `corridor` keys), in the groups a push moves as one block: the
    two ends of a stretch that lies across the push (horizontal when the push is vertical: across_y) belong together, so the stretch
    moves whole and stays straight (a stretch along the push may get longer or shorter), and a label on such a stretch goes with
    it. Returns [(bounding rect, [keys], kind: a, or l for a label alone)]."""
    parent = {k: k for k in corridor}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    ax = 1 if across_y else 0
    across = lambda pts, s: abs(pts[s][ax] - pts[s + 1][ax]) < .01
    for i, pts in paths.items():
        for s in range(len(pts) - 1):
            if (i, s) in corridor and (i, s + 1) in corridor and across(pts, s):
                parent[find((i, s))] = find((i, s + 1))
    for j, (cx, cy) in centres.items():
        i = owner.get(j)
        if ('label', j) not in corridor or i not in paths:
            continue
        pts = paths[i]
        for s in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[s], pts[s + 1]
            if (abs(y0 - y1) < .01 and abs(cy - y0) < 1 and min(x0, x1) - 1 <= cx <= max(x0, x1) + 1) or \
                    (abs(x0 - x1) < .01 and abs(cx - x0) < 1 and min(y0, y1) - 1 <= cy <= max(y0, y1) + 1):
                if (i, s) in corridor and (i, s + 1) in corridor and across(pts, s):
                    parent[find(('label', j))] = find((i, s))
                break
    members = {}
    for k in corridor:
        members.setdefault(find(k), []).append(k)
    out = []
    for ks in members.values():
        xs, ys = [], []
        for k in ks:
            if k[0] == 'label':
                x, y, w, h = lab_rect[k[1]]
                xs += [x, x + w]
                ys += [y, y + h]
            else:
                xs.append(paths[k[0]][k[1]][0])
                ys.append(paths[k[0]][k[1]][1])
        out.append(((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)), ks, 'l' if all(k[0] == 'label' for k in ks) else 'a'))
    return out


def _shift_legend(text, dx):
    lines = text.split('\n')
    a = next((i for i, l in enumerate(lines) if l == '<!--legend-->'), None)
    if a is None:
        return text
    for i in range(a + 1, lines.index('<!--/legend-->')):
        lines[i] = collapse.shift_line(lines[i], dx, 0)
    return '\n'.join(lines)


END_CLEAR = 30           # px: no crossing this close to the end of a stretch (route.END_CLEAR), so hops.py can mark it
MIN_JOG = 30             # px: no new stretch shorter than this (route.MIN_JOG)


def _with_steps(pts, orig, boxes, frames_now, paths, me):
    """The points of an arrow whose stretches the move left out of square, mended with the fewest new bends. A stretch that was
    horizontal and whose two ends moved to different heights (likewise across) is first slid whole (_slide): one of its ends moves
    along the stretch next to it, which only gets longer or shorter, so no bend is added. Only when neither slide is free does it
    take one step (a jog), at the first place along it where the three new stretches (the two halves and the step) are free
    (_step_free). None when a stretch has neither."""
    pts = [tuple(p) for p in pts]
    out = [pts[0]]
    for j in range(1, len(pts)):
        p, q = out[-1], pts[j]
        if abs(p[0] - q[0]) < .01 or abs(p[1] - q[1]) < .01:
            out.append(q)
            continue
        horiz = abs(orig[j - 1][1] - orig[j][1]) < .01
        slid = _slide(out, pts, j, horiz, boxes, paths, me)
        if slid is not None:
            out, pts = slid
            out.append(pts[j])
            continue
        lo, hi = sorted((p[0], q[0]) if horiz else (p[1], q[1]))
        step = next((c for c in _frange(lo + MIN_JOG, hi - MIN_JOG, 5) if _step_free(c, p, q, horiz, boxes, frames_now, paths, me)), None)
        if step is None:
            return None
        out += [(step, p[1]), (step, q[1])] if horiz else [(p[0], step), (q[0], step)]
        out.append(q)
    return _straight(out)


def _slide(out, pts, j, horiz, boxes, paths, me):
    """_with_steps' mend with no new bend for the stretch from out[-1] to pts[j]: put it back square by moving its first end along
    the stretch before it (out[-2] to out[-1]), or its second end along the stretch after it (pts[j] to pts[j + 1]). An arrow end
    (on its box) never moves; the stretch that changes keeps its direction (no turn back) and MIN_JOG of length; the two changed
    stretches pass the room test of a step's halves (_segs_free): the slid one whole, of the neighbour only the part it gains (what it
    kept was drawn before). The smaller move wins. Returns (out, pts) changed, or None."""
    p, q = out[-1], pts[j]
    tries = []
    if len(out) >= 2:                                      # the first end moves along the stretch before it
        o = out[-2]
        np_ = (p[0], q[1]) if horiz else (q[0], p[1])
        if _along(o, p, np_):
            tries.append((abs(np_[0] - p[0]) + abs(np_[1] - p[1]), 'first', np_, _grown_part(o, p, np_) + [(np_, q)]))
    if j + 1 < len(pts):                                   # the second end moves along the stretch after it
        r = pts[j + 1]
        nq = (q[0], p[1]) if horiz else (p[0], q[1])
        if _along(r, q, nq):
            tries.append((abs(nq[0] - q[0]) + abs(nq[1] - q[1]), 'second', nq, [(p, nq)] + _grown_part(r, q, nq)))
    for _, which, new, segs in sorted(tries, key=lambda t: t[0]):
        if not _segs_free([_seg(u, v) for u, v in segs], boxes, paths, me):
            continue
        if which == 'first':
            return out[:-1] + [new], pts
        return out, pts[:j] + [new] + pts[j + 1:]
    return None


def _grown_part(fixed, old, new):
    """The part a stretch from `fixed` gains when its corner moves from `old` to `new` along it: [(old, new)], or [] when it gets
    shorter."""
    longer = abs(new[0] - fixed[0]) + abs(new[1] - fixed[1]) > abs(old[0] - fixed[0]) + abs(old[1] - fixed[1])
    return [(old, new)] if longer else []


def _along(fixed, old, new):
    """May the corner `old` of the stretch from `fixed` move to `new`, along that stretch? It stays on the same line, on the same side
    of `fixed` (no turn back), and the stretch keeps MIN_JOG of length."""
    same_x, same_y = abs(fixed[0] - old[0]) < .01 and abs(fixed[0] - new[0]) < .01, abs(fixed[1] - old[1]) < .01 and abs(fixed[1] - new[1]) < .01
    if not (same_x or same_y):
        return False
    ax = 1 if same_x else 0
    before, after = old[ax] - fixed[ax], new[ax] - fixed[ax]
    return before * after > 0 and abs(after) >= MIN_JOG


def _seg(u, v):
    """The orthogonal stretch from u to v as (o, c, lo, hi)."""
    if abs(u[1] - v[1]) < .01:
        return 'h', u[1], min(u[0], v[0]), max(u[0], v[0])
    return 'v', u[0], min(u[1], v[1]), max(u[1], v[1])


def _nearest(pts, x, y):
    """The point of the polyline pts nearest to (x, y)."""
    best = None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        px, py = min(max(x, min(x0, x1)), max(x0, x1)), min(max(y, min(y0, y1)), max(y0, y1))
        d = abs(px - x) + abs(py - y)
        if best is None or d < best[0]:
            best = (d, px, py)
    return best[1], best[2]


def _frange(lo, hi, step):
    v = lo
    while v <= hi:
        yield v
        v += step


def _step_free(c, p, q, horiz, boxes, frames_now, paths, me):
    """May the step of _with_steps sit at c (an x for a vertical step, a y for a horizontal one)? The step lies in a corridor (outside
    every frame, 10px clear of its border) and JOG_ROOM from boxes; the step and the two halves of the stretch keep JOG_ROOM[1]
    from parallel stretches of other arrows, run through no box, and cross other arrows only END_CLEAR or more from either end."""
    bm, vm = JOG_ROOM
    if horiz:
        step = ('v', c, min(p[1], q[1]), max(p[1], q[1]))
        halves = [('h', p[1], min(p[0], c), max(p[0], c)), ('h', q[1], min(q[0], c), max(q[0], c))]
    else:
        step = ('h', c, min(p[0], q[0]), max(p[0], q[0]))
        halves = [('v', p[0], min(p[1], c), max(p[1], c)), ('v', q[0], min(q[1], c), max(q[1], c))]
    if any(_meets(step, (x - 10, y - 10, w + 20, h + 20)) for x, y, w, h in frames_now):
        return False
    if any(_meets(step, (x - bm, y - bm, w + 2 * bm, h + 2 * bm)) for x, y, w, h in boxes):
        return False
    return _segs_free(halves, boxes, paths, me, extra=[step])


def _segs_free(segs, boxes, paths, me, extra=()):
    """The room test of new stretches (segs, and `extra` that already passed its own box test): none runs through a box, none keeps
    less than JOG_ROOM[1] from a parallel stretch of another arrow, and none crosses another arrow closer than END_CLEAR to either
    end of either stretch."""
    vm = JOG_ROOM[1]
    new = list(extra) + list(segs)
    if any(_meets(sg, (x + 1, y + 1, w - 2, h - 2)) for sg in segs for x, y, w, h in boxes):
        return False
    for k, pts in paths.items():
        if k == me:
            continue
        for o2, c2, lo2, hi2 in _segments(pts):
            for o, cc, lo, hi in new:
                if o2 == o and abs(c2 - cc) < vm and min(hi, hi2) - max(lo, lo2) > 0:
                    return False
                if o2 != o and lo < c2 < hi and lo2 < cc < hi2 and \
                        min(c2 - lo, hi - c2, cc - lo2, hi2 - cc) < END_CLEAR:
                    return False
    return True


def _straight(pts):
    out = [pts[0]]
    for p, q in zip(pts[1:], pts[2:]):
        o = out[-1]
        if (abs(o[0] - p[0]) < .01 and abs(p[0] - q[0]) < .01) or (abs(o[1] - p[1]) < .01 and abs(p[1] - q[1]) < .01):
            continue
        out.append(p)
    return out + [pts[-1]]


def _snap(pts, olds, news, orig, strict=True):
    """The mapped points of an arrow with each end put back on its box side (inflate's docstring), or None when that cannot keep
    every stretch orthogonal."""
    pts = [list(p) for p in pts]
    for end, (ob, nb) in zip((0, len(pts) - 1), zip(olds, news)):
        nxt = 1 if end == 0 else len(pts) - 2
        ox, oy = orig[end]
        x, y, w, h = nb
        if abs(ox - ob[0]) < ATTACH or abs(ox - ob[0] - ob[2]) < ATTACH:      # on the left or right side: x is the side, y along it
            pts[end][0] = x if abs(ox - ob[0]) < ATTACH else x + w
            along = min(max(pts[end][1], y + 8), y + h - 8)
            if along != pts[end][1]:
                pts[end][1] = pts[nxt][1] = along
        else:                                                                # on the top or bottom side
            pts[end][1] = y if abs(oy - ob[1]) < ATTACH else y + h
            along = min(max(pts[end][0], x + 8), x + w - 8)
            if along != pts[end][0]:
                pts[end][0] = pts[nxt][0] = along
    ok = all(abs(p[0] - q[0]) < .01 or abs(p[1] - q[1]) < .01 for p, q in zip(pts, pts[1:]))
    return [tuple(p) for p in pts] if ok or not strict else None


def set_canvas_height(text, need):
    """Make the canvas (the root size, its viewBox and the page rectangle) at least `need` px tall; never shorter."""
    m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)" viewBox="0 0 (\d+) (\d+)"', text)
    if not m or int(need) <= int(m.group(2)):
        return text
    H = int(need) + (1 if need > int(need) else 0)
    text = text.replace('height="%s" viewBox="0 0 %s %s"' % (m.group(2), m.group(3), m.group(4)),
                        'height="%d" viewBox="0 0 %s %d"' % (H, m.group(3), H), 1)
    return re.sub(r'(<rect x="0" y="0" width="[\d.]+" height=")%s(" fill="#[0-9a-f]{6}"/>)' % m.group(2),
                  lambda q: q.group(1) + str(H) + q.group(2), text, count=1)


def by_name(text, name):
    """The rectangle of the frame whose title is `name` now (a frame keeps its title when inflate or grow move it), or None."""
    import svgmeta
    lines, _, _, fr = collapse.parse(text)
    return next((_rect(f) for f in fr if svgmeta.frame_name(lines[f['tl']]) == name), None)


def name_of(text, rect):
    """The title of the frame at `rect`, or None."""
    import svgmeta
    lines, _, _, fr = collapse.parse(text)
    return next((svgmeta.frame_name(lines[f['tl']]) for f in fr if all(abs(a - b) < .5 for a, b in zip(_rect(f), rect))), None)


def set_canvas_width(text, need):
    """Make the canvas at least `need` px wide; never narrower."""
    m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)" viewBox="0 0 (\d+) (\d+)"', text)
    if not m or int(need) <= int(m.group(1)):
        return text
    W = int(need) + (1 if need > int(need) else 0)
    text = text.replace('width="%s" height="%s" viewBox="0 0 %s %s"' % m.groups(), 'width="%d" height="%s" viewBox="0 0 %d %s"'
                        % (W, m.group(2), W, m.group(4)), 1)
    return re.sub(r'(<rect x="0" y="0" width=")%s(" height="[\d.]+" fill="#[0-9a-f]{6}"/>)' % m.group(1),
                  lambda q: q.group(1) + str(W) + q.group(2), text, count=1)


def selftest():
    """The cascade on fixed frames: a frame below moves, then the one below that; one beside does not; two that touch both move;
    a box under the grown frame moves, one inside it does not; nothing ends overlapping. cascade_gap: a frame far below stays.
    _with_steps: a stretch out of square slides back with no new bend."""
    bad = []
    F = [(0, 0, 400, 300),          # 0: grows
         (0, 340, 300, 200),        # 1: below 0, overlaps: moves
         (200, 560, 400, 100),      # 2: below 1 (overlaps it, not 0's x? it does): moves
         (450, 0, 300, 600),        # 3: beside 0: stays
         (0, 540, 150, 10),         # 4: touches 1's bottom: moves
         (700, 700, 100, 100)]      # 5: below 3 only: stays (3 does not move)
    boxes = {1: (20, 40, 260, 62), 2: (20, 320, 100, 10), 3: (500, 700, 50, 50), 4: (900, 0, 50, 50)}   # 3: under frame 2
    g, mf, mb = cascade(F, boxes, F[0])
    if g != {0}:
        bad.append('grows %s' % g)
    if mf != {1, 2, 4}:
        bad.append('frames moved %s, want {1, 2, 4}' % sorted(mf))
    if mb != {2, 3}:
        bad.append('boxes moved %s, want {2, 3}' % sorted(mb))
    g2, mf2, mb2 = cascade(F, dict(boxes, m=(20, 310, 100, 40)), F[0], members={'m'})
    if 'm' in mb2 or 2 not in mb2:
        bad.append('a box the frame grows to hold moved, or a box below it did not (%s)' % sorted(map(str, mb2)))
    dy = 40
    after = [(x, y + dy, w, h) if k in mf else (x, y, w, h + dy) if k in g else (x, y, w, h) for k, (x, y, w, h) in enumerate(F)]
    for k, r in enumerate(after):
        for m, s in enumerate(after[k + 1:], k + 1):
            if r[0] < s[0] + s[2] - TOUCH and s[0] < r[0] + r[2] - TOUCH and r[1] < s[1] + s[3] - TOUCH and s[1] < r[1] + r[3] - TOUCH:
                bad.append('frames %d and %d overlap after the push' % (k, m))
    # cascade_gap: a frame far below does not move, one close below moves only what its gap cannot absorb
    G = [(0, 0, 400, 300), (0, 334, 400, 100), (500, 600, 100, 100), (0, 900, 400, 100)]
    _, mf3, _ = cascade_gap(G, {}, G[0], 40)
    if mf3 != {1: 40.0}:
        bad.append('cascade_gap moved %s, want {1: 40} (frame 3 is 466px below 1: its gap absorbs the push)' % mf3)
    # _with_steps: a stretch the move put out of square slides back with no new bend when its neighbour can get shorter
    orig = [(0, 0), (100, 0), (100, 200), (300, 200)]
    mended = _with_steps([(0, 0), (100, 0), (60, 200), (300, 200)], orig, [], [], {}, 0)
    if mended != [(0, 0), (60, 0), (60, 200), (300, 200)]:
        bad.append('_with_steps did not slide the stretch square: %s' % mended)
    print('frames self-test: %s' % ('OK' if not bad else 'FAILED: ' + '; '.join(bad)))
    return not bad


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        sys.exit(0 if selftest() else 1)
    sys.exit(__doc__)
