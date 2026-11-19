#!/usr/bin/env python3
"""Make room by pushing boxes apart: the end-of-run step (model.finish) that leaves no arrow without a label, and that shortens an
arrow which makes a long detour round a narrow gap. A box moves; it never stretches.

    t = push_box(text, n, side, d)       box n moves d px towards `side` (right, left, bottom, top): a Pushed
    text = make_room(text)               every arrow with no label (or a label that covers something) gets room for one
    text = straighten(text)              every long detour that a small push saves is routed short

push_box, the cascade. The picture is turned so that `side` is the bottom (frames._TURN), so one rule serves the four sides. The
blocks are the boxes and the frames that sit directly in the pushed box's frame (its container; the whole page when it has none);
a frame block carries what it holds. A moving block pushes every block after it on its way that overlaps it across the push
(more than frames.TOUCH px): that block keeps the gap it had, but no more than GAP px of it when no arrow runs through the gap
across the push (a lane), so a far block takes less of the push, and one past GAP + d not at all. When a block would come nearer
than BOTTOM_PAD px (or the pad it had, if less) to the container's border, the container grows on that side by frames.grow: what
lies beyond it moves rigidly, the frames that hold it grow. Arrows: one with both ends on boxes moved by the same amount moves
with them, label and jump arcs included; one with an end on a moved box keeps its shape: the end stretch grows or shrinks when
it runs along the push, it slides with the box (its neighbour stretch grows or shrinks) when it runs across; a stretch that would
reverse, or a straight arrow pushed across, is cut. A label that is no longer on its arrow is placed again. Cut arrows, and those
frames.grow cut, are routed again by the caller (settle()).

make_room, an arrow that has no place for its label: route.place_label_any already relaxed the soft rules (shaft, centring,
distance) as far as they go while the label covers nothing. So the arrow is made longer: the box at one end moves away along the
end stretch (a tip box along the arrow, a tail box against it; a straight arrow also both, half each), by the shortfall of the
label plus PUSH_STEPS. Candidates are tried cheapest first by total displacement (every box moved, by how much, frames grown);
the first whose arrow then has a place for its label, with no arrow invalid that was valid, is kept.

straighten, a crazy path (route.is_crazy: it goes far beyond the rectangle of its two ends, or less far with square curves). A
probe route with no clearance round the other boxes (route.BOXM 0) and little round the frame borders (PROBE_FPROX) shows where a
short path would go; the boxes nearer to it than route.BOXM + route.G, and the frames whose border a stretch runs beside, outside
them, nearer than route.FPROX + route.G (two frames whose gap holds no lane), are the blockers. Pushing them away from the probe path (both sides of a gap, or one side by
the whole need; a frame moves rigidly with all it holds, by the same cascade as a box) opens it; the cheapest push after which the
arrow, routed again, is no longer crazy (or at most DETOUR_GAIN of its old length) and has a label is kept. Pinned arrows are never
touched.

usage: push.py selftest
"""
import math, os, re, sys, tempfile, time
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typing import NamedTuple
import collapse, draw, frames, route

GAP = 28.0                  # px a pushed box keeps from the next one when no arrow runs between them (move.GAP)
PUSH_STEPS = (5, 20, 40)    # px over the label's shortfall: the pushes tried at one end
PUSH_MAX = 160              # px: no box is pushed further than this for one arrow
DETOUR_GAIN = 0.6           # a straightened path is kept only when it is at most this share of the old one
DETOUR_BENDS = 4            # the probe path may have at most this many bends (a short route, not another detour)
PROBE_FPROX = 2 * route.G   # px the probe keeps from a frame border (route.FPROX in the real search): it runs in a gap with no lane
SIDE_OF = {(1, 0): 'right', (-1, 0): 'left', (0, 1): 'bottom', (0, -1): 'top'}
LOG = []                    # one line per push kept: what moved, by how much, which frames grew (the scripts print it)
STATS = {'tried': 0, 'kept': 0, 'secs': 0.0}
DEPTH = {'n': 0}            # > 0 while a push routes what it cut: model.finish then makes no room again


class Pushed(NamedTuple):
    text: str
    moved: dict             # box -> (dx, dy); a pushed frame moves with all it holds, its boxes are here
    grown: list             # (frame title, side, px) of every frame grown
    cut: set                # (a, b, kind) of the arrows to route again
    disp: float             # total displacement: px moved summed over the boxes, plus the px every grown frame grew
    frames_moved: tuple = ()  # (frame title, dx, dy) of every frame moved


def _turn_pt(side, p):
    """A point turned like frames._TURN turns a rectangle, so that `side` is the bottom."""
    x, y = p
    return {'bottom': (x, y), 'top': (x, -y), 'right': (y, x), 'left': (y, -x)}[side]


def _innermost(rects, r, skip=None):
    """Index of the smallest frame that holds r (not `skip`), or None."""
    hold = [k for k, f in enumerate(rects) if k != skip and frames._holds(f, r)]
    return min(hold, key=lambda k: rects[k][2] * rects[k][3]) if hold else None


def cascade(blocks, start, d, lanes=()):
    """The shift of every block, in the turned picture (push down), when block `start` moves d down. blocks {key: (x, y, w, h)};
    lanes: horizontal stretches (y, x0, x1) of arrows. A moving block pushes each block below it that overlaps it horizontally: that
    block keeps its gap, but at most GAP px of it unless a lane runs through the gap. Returns {key: shift}."""
    shift, todo = {start: float(d)}, [start]
    while todo:
        k = todo.pop()
        r, s = blocks[k], shift[k]
        bottom = r[1] + r[3]
        for j, q in blocks.items():
            if j == k or not frames._over_x(q, r) or q[1] < bottom - frames.TOUCH:
                continue
            g0 = max(0.0, q[1] - bottom)
            lo, hi = max(r[0], q[0]), min(r[0] + r[2], q[0] + q[2])
            lane = any(bottom < y < q[1] and x0 < hi and x1 > lo for y, x0, x1 in lanes)
            need = s - max(0.0, g0 - (g0 if lane else min(g0, GAP)))
            if need > shift.get(j, 0.0) + .01:
                shift[j] = need
                todo.append(j)
    return shift


def _seg_ok(old, new):
    """Do the stretches of `new` run the same way as those of `old` (same count, none reversed or shorter than 1px)?"""
    if len(old) != len(new):
        return False
    for (p, q), (p2, q2) in zip(zip(old, old[1:]), zip(new, new[1:])):
        a, b = (q[0] - p[0], q[1] - p[1]), (q2[0] - p2[0], q2[1] - p2[1])
        if abs(b[0]) + abs(b[1]) < 1 or a[0] * b[0] < 0 or a[1] * b[1] < 0 or (abs(a[0]) < .01) != (abs(b[0]) < .01):
            return False
    return True


def reattach(pts, end, vec):
    """The path with its tail (end 0) or tip (end -1) moved by vec, keeping its shape: an end stretch along vec grows or shrinks;
    one across vec slides with its box and the stretch before it grows or shrinks. None when the shape cannot be kept."""
    pts = [tuple(p) for p in route.straight([tuple(p) for p in pts])]
    dx, dy = vec
    i, j = (0, 1) if end == 0 else (len(pts) - 1, len(pts) - 2)
    p, q = pts[i], pts[j]
    horiz = abs(p[1] - q[1]) < .01
    new = list(pts)
    new[i] = (p[0] + dx, p[1] + dy)
    if (horiz and dy) or (not horiz and dx):                 # across the stretch: it slides with its box
        if len(pts) < 3:
            return None
        new[j] = (q[0] + dx, q[1] + dy)
    return new if _seg_ok(pts, new) else None


def _path_line(line, pts):
    return re.sub(r'd="[^"]*"', 'd="M%s"' % ' L'.join('%s,%s' % (draw.fmt(x), draw.fmt(y)) for x, y in pts), line, count=1)


def push_box(text, n, side, d):
    """Box n, or the frame n = ('f', k) (k: its place among the frames of collapse.parse), moves d px towards `side`; what it would
    hit moves too (module docstring). Returns a Pushed."""
    import model
    lines, box, pop, fr = collapse.parse(text)
    rects = [frames._rect(f) for f in fr]
    boxes = {m: frames._rect(b) for m, b in box.items()}
    parent = {k: _innermost(rects, rects[k], skip=k) for k in range(len(rects))}
    start = n if isinstance(n, tuple) else ('b', n)
    home = parent[n[1]] if isinstance(n, tuple) else _innermost(rects, boxes[n])
    turn = frames._TURN[side]
    blocks = {('b', m): turn(r) for m, r in boxes.items() if _innermost(rects, r) == home}
    blocks.update({('f', k): turn(rects[k]) for k in range(len(rects)) if parent[k] == home})
    lanes = []
    for ln in lines:
        if ln.startswith('<path d="M') and 'marker-end' in ln:
            tp = [_turn_pt(side, p) for p in route.straight(model.arrow_points(ln))]
            lanes += [(p[1], min(p[0], q[0]), max(p[0], q[0])) for p, q in zip(tp, tp[1:]) if abs(p[1] - q[1]) < .01]
    shift = cascade(blocks, start, d, lanes)
    way = frames._WAY[side]
    moves, fmoves = {}, {}
    for (kind, key), s in shift.items():
        v = (s * way[0], s * way[1])
        if kind == 'b':
            moves[key] = v
        else:
            fmoves[key] = v
            moves.update({m: v for m, r in boxes.items() if frames._holds(rects[key], r)})
            fmoves.update({k: v for k in range(len(rects)) if k != key and frames._holds(rects[key], rects[k])})
    grown, cut = [], set()
    need = 0.0
    if home is not None:                                     # the container grows where a block would come too near its border
        c = turn(rects[home])
        for key, s in shift.items():
            q = blocks[key]
            pad = min(c[1] + c[3] - (q[1] + q[3]), frames.BOTTOM_PAD)
            need = max(need, q[1] + q[3] + s + pad - (c[1] + c[3]))
    disp = sum(abs(v[0]) + abs(v[1]) for v in moves.values())
    fnames = tuple((frames.name_of(text, rects[k]), v[0], v[1]) for k, v in sorted(fmoves.items()))
    if need > .01:
        need = math.ceil(need)
        name = frames.name_of(text, rects[home])
        g = frames.grow(text, rects[home], need, side=side)
        cut |= {tuple(model.arrow_at(g.text.split('\n')[i]) or ()) for i in g.cut}
        text = g.text
        grown.append((name, side, need))
        disp += need + sum(need for _ in g.moved)
        lines, box, pop, fr = collapse.parse(text)           # a growth past the top or left edge moved the whole picture: the
        boxes = {m: frames._rect(b) for m, b in box.items()}  # shifts are relative, so they hold in the moved picture as well
    old_boxes = dict(boxes)
    out = list(lines)
    for m, (dx, dy) in moves.items():
        b = box[m]
        for a, z in [(b['a'], b['b'])] + ([pop[m]] if m in pop else []):
            for i in range(a, z + 1):
                out[i] = collapse.shift_line(out[i], dx, dy)
    for k, (dx, dy) in fmoves.items():
        f = fr[k]
        out[f['rl']] = frames._set_rect(out[f['rl']], (f['x'] + dx, f['y'] + dy, f['w'], f['h']))
        out[f['tl']] = collapse.shift_line(out[f['tl']], dx, dy)
    # arrows on moved boxes
    arrow_idx = [i for i, ln in enumerate(lines) if ln.startswith('<path d="M') and 'marker-end' in ln]
    labs = frames.labels_of(lines, arrow_idx)
    relabel, drop = [], set()
    for i in arrow_idx:
        at = model.arrow_at(lines[i])
        pts = model.arrow_points(lines[i])
        ends = [frames._end_box(pts[0], old_boxes), frames._end_box(pts[-1], old_boxes)]
        if at in cut or not (set(ends) & set(moves)):
            continue
        va, vb = moves.get(ends[0], (0.0, 0.0)), moves.get(ends[1], (0.0, 0.0))
        if ends[0] in moves and ends[1] in moves and va == vb:
            out[i] = frames._shift_path(lines[i], *va)
            for j in labs.get(i, ()):
                out[j] = collapse.shift_line(out[j], *va)
            continue
        new = pts
        for end, v in ((0, va), (-1, vb)):
            if new is not None and v != (0.0, 0.0):
                new = reattach(new, end, v)
        if new is None:
            cut.add(at)
            continue
        out[i] = _path_line(lines[i], new)
        if i in labs:
            lab = draw.label_at(lines, labs[i][0])
            cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
            on = any((o == 'h' and abs(c - cy) < 1 and lo <= cx <= hi) or (o == 'v' and abs(c - cx) < 1 and lo <= cy <= hi)
                     for o, c, lo, hi in route.segments(new))
            if not on:
                relabel.append(labs[i][0])
    res = '\n'.join(out)
    if relabel:                                              # a label left off its arrow: placed again on it, else taken off
        sc, _ = model.read(res)
        rl = res.split('\n')
        for j in relabel:
            k = next(i for i, r in labs.items() if r[0] == j)
            at = model.arrow_at(rl[k])
            lab = draw.label_at(rl, j)
            rect = draw.label_box(rl, j)
            with sc.hide('labels', rect) as others:
                got = route.place_label_any(others, model.arrow_points(rl[k]), at.kind, lab[2], lab[3])
            if got:
                draw.move_label(rl, j, got[0], got[1], got[2])
            else:
                drop |= set(range(j, j + 1 + lab[4]))
        res = '\n'.join(ln for i, ln in enumerate(rl) if i not in drop)
    nb = [frames._rect(b) for b in collapse.parse(res)[1].values()]
    res = frames.set_canvas_height(res, max(r[1] + r[3] for r in nb) + frames.CANVAS_BOTTOM)
    res = frames.set_canvas_width(res, max(r[0] + r[2] for r in nb) + frames.CANVAS_BOTTOM)
    return Pushed(res, moves, grown, {tuple(c) for c in cut if c}, disp, fnames)


def settle(before, pushed):
    """Route again what a push cut (model.route_arrows, the rest stays drawn), then every arrow the push left invalid (model.settle).
    Returns the text."""
    import model
    text = pushed.text
    lines = text.split('\n')
    idx = [i for i, ln in enumerate(lines) if model.svgmeta_arrow(ln) in pushed.cut]
    if idx:
        t, pend = model.take_out(text, idx, keep=set(idx))
        text = model.route_arrows(t, pend).text
    text, _, _ = model.settle(before, text)
    return text


def _arrow_line(text, key):
    import model
    return next((ln for ln in text.split('\n') if model.svgmeta_arrow(ln) == key), None)


def _labelled(text, key, mode='has'):
    """mode 'has': the arrow `key` carries a label that covers nothing (route.RELAX_GAP clear of everything). mode 'place': a place
    for its label exists (route.place_label_any, its own label left out of the picture)."""
    import model
    lines = text.split('\n')
    i = next((i for i, ln in enumerate(lines) if model.svgmeta_arrow(ln) == key), None)
    if i is None:
        return False
    j = frames.labels_of(lines, [i]).get(i)
    sc, _ = model.read(text)
    own = model.arrow_points(lines[i])
    if j is None:
        return mode == 'place' and route.place_label_any(sc, own, key[2]) is not None
    rect = draw.label_box(lines, j[0])
    with sc.hide('labels', rect) as others:
        if mode == 'place':
            return route.place_label_any(others, own, key[2]) is not None
        return not route._hit(rect, others, own=own, pad=route.RELAX_GAP, hop_pad=route.RELAX_GAP, g=route.RELAX_GAP)


def needing_room(text):
    """(a, b, kind) of every arrow with no label, or whose label covers a box, a label, a pill, a jump arc or another path."""
    import model, svgmeta
    lines = text.split('\n')
    idx = [i for i, ln in enumerate(lines) if svgmeta.is_arrow(ln)]
    labs = frames.labels_of(lines, idx)
    sc, _ = model.read(text)
    out = []
    for i in idx:
        at = model.svgmeta_arrow(lines[i])
        if not at or at[2] not in draw.EDGE:
            continue
        if i not in labs:
            out.append(at)
            continue
        rect = draw.label_box(lines, labs[i][0])
        with sc.hide('labels', rect) as others:
            if route._hit(rect, others, own=model.arrow_points(lines[i]), pad=route.RELAX_GAP, hop_pad=route.RELAX_GAP, g=0):
                out.append(at)
    return out


def _shortfall(sc, pts, end, kind):
    """px the end stretch (end 0: the first, -1: the last) lacks to carry the label relaxed: its length from the box to the first
    crossing (or its other end), against the label's length plus route.RELAX_SHAFT each side (and the arrowhead at the tip)."""
    p = route.straight([tuple(x) for x in pts])
    a, b = (p[0], p[1]) if end == 0 else (p[-1], p[-2])
    horiz = abs(a[1] - b[1]) < .01
    ext = draw.label_width(kind) if horiz else 18.0
    need = ext + 2 * (route.RELAX_SHAFT + route.RELAX_GAP) + (11 if end == -1 else 0)
    k, c = (0, a[1]) if horiz else (1, a[0])
    lo, hi = sorted((a[k], b[k]))
    free = abs(b[k] - a[k])
    mine = tuple(map(tuple, pts))
    q = (lo, c, hi, c) if horiz else (c, lo, c, hi)
    for other, (o, c2, lo2, hi2) in sc.near('arrows', q):
        if other != mine and o != ('h' if horiz else 'v') and lo < c2 < hi and lo2 < c < hi2:
            free = min(free, abs(c2 - a[k]) - route.HOP_R)
    return need - free


def _ceil5(v):
    return 5 * math.ceil(v / 5)


def _end_pushes(text, key):
    """Candidate pushes for an arrow with no room for its label: [[(box, side, d)]]."""
    import model
    line = _arrow_line(text, key)
    pts = route.straight([tuple(p) for p in model.arrow_points(line)])
    sc, _ = model.read(text)
    out = []
    ends = []
    for end, n in ((-1, key[1]), (0, key[0])):
        a, b = (pts[-2], pts[-1]) if end == -1 else (pts[1], pts[0])     # the way the box must go: away from the arrow's middle
        u = ((b[0] > a[0]) - (b[0] < a[0]), (b[1] > a[1]) - (b[1] < a[1]))
        if u not in SIDE_OF or n not in sc.boxes:
            continue
        short = max(0.0, _shortfall(sc, pts, end, key[2]))
        ends.append((n, SIDE_OF[u], short))
        out += [[(n, SIDE_OF[u], _ceil5(short) + s)] for s in PUSH_STEPS if _ceil5(short) + s <= PUSH_MAX]
    if len(pts) == 2 and len(ends) == 2:                     # a straight arrow: both ends, half each
        short = max(e[2] for e in ends)
        out += [[(n, sd, _ceil5(short / 2) + s) for n, sd, _ in ends] for s in PUSH_STEPS if _ceil5(short / 2) + s <= PUSH_MAX]
    return out


def _apply(text, pushes):
    """push_box for each (box, side, d) in turn. Returns a Pushed for all of them, or None when a box is not in the picture."""
    moved, grown, cut, disp, fmoved = {}, [], set(), 0.0, ()
    for n, side, d in pushes:
        _, box, _, fr = collapse.parse(text)
        if (n[1] >= len(fr)) if isinstance(n, tuple) else n not in box:
            return None
        p = push_box(text, n, side, d)
        text = p.text
        for m, v in p.moved.items():
            o = moved.get(m, (0.0, 0.0))
            moved[m] = (o[0] + v[0], o[1] + v[1])
        grown += p.grown
        cut |= p.cut
        disp += p.disp
        fmoved += p.frames_moved
    return Pushed(text, moved, grown, cut, disp, fmoved)


def _describe(why, key, p):
    mv = ', '.join('#%d %s' % (m, '(%+g, %+g)' % v if v[0] and v[1] else ('%+gx' % v[0] if v[0] else '%+gy' % v[1]))
                   for m, v in sorted(p.moved.items()))
    gr = '; frames grown: ' + ', '.join('"%s" %s %dpx' % g for g in p.grown) if p.grown else ''
    fm = '; frames moved: ' + ', '.join('"%s" (%+g, %+g)' % f for f in p.frames_moved) if p.frames_moved else ''
    return '%s #%d %s #%d: moved %s%s%s' % (why, key[0], key[2], key[1], mv, gr, fm)


def lengths(text):
    """{(a, b, kind): path length} of every arrow."""
    import model
    out = {}
    for ln in text.split('\n'):
        key = model.svgmeta_arrow(ln)
        if key:
            out[key] = _length(route.straight(model.arrow_points(ln)))
    return out


def growth(before, after, skip):
    """px the other arrows grew in all (a push cuts arrows and they are routed again: a longer route is a cost of that push)."""
    a = lengths(after)
    return sum(max(0.0, a[k] - v) for k, v in lengths(before).items() if k in a and k != skip)


def _best(text, key, pushed, judge):
    """Of the pushes (Pushed, each applied to text), the one with the least score: its displacement plus growth() of the other
    arrows, among those that judge() passes after settle(). Tried the least displacement first, and only while that alone is
    less than the best score so far (branch and bound). judge(settled text) -> the final text, or None. Returns (text, Pushed)
    of the best, or (text, None)."""
    import model
    bad0, n0 = len(model.invalid(text)), model.count_arrows(text)
    best = None
    for p in sorted(pushed, key=lambda p: p.disp)[:MAX_CANDS]:
        if best is not None and p.disp >= best[0]:
            break
        STATS['tried'] += 1
        t = judge(settle(text, p))
        if t is None or len(model.invalid(t)) > bad0 or model.count_arrows(t) != n0:
            continue
        score = p.disp + growth(text, t, key)
        if best is None or score < best[0]:
            best = (score, t, p)
    if best is None:
        return text, None
    STATS['kept'] += 1
    return best[1], best[2]


def make_room(text):
    """Give a place for its label to every arrow that has none, or whose label covers something (needing_room), by pushing its end
    boxes apart (module docstring). Returns the text; LOG says what moved."""
    t0 = time.time()
    tried = set()
    while True:
        todo = [k for k in needing_room(text) if k not in tried]
        if not todo:
            break
        key = todo[0]
        tried.add(key)
        line = _arrow_line(text, key)
        if line is None or 'data-pinned="1"' in line or key[0] == key[1]:
            continue
        pushed = [p for p in (_apply(text, c) for c in _end_pushes(text, key)) if p is not None and _labelled(p.text, key, 'place')]
        text, p = _best(text, key, pushed, lambda t, key=key: t if _labelled(t, key) else None)
        if p:
            LOG.append(_describe('room for the label of', key, p))
    STATS['secs'] += time.time() - t0
    return text


def _length(pts):
    return sum(abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in zip(pts, pts[1:]))


def detours(text):
    """(key, length, Manhattan distance) of every arrow whose path is crazy (route.is_crazy) and is not pinned."""
    import model, svgmeta
    out = []
    for ln in text.split('\n'):
        if not svgmeta.is_arrow(ln) or 'data-pinned="1"' in ln:
            continue
        key = model.svgmeta_arrow(ln)
        pts = route.straight(model.arrow_points(ln))
        if key and route.is_crazy(pts):
            out.append((key, _length(pts), abs(pts[0][0] - pts[-1][0]) + abs(pts[0][1] - pts[-1][1])))
    return out


def _better(pts, L):
    """Does the path cure a crazy one of length L: not crazy itself, or at most DETOUR_GAIN of L?"""
    return not route.is_crazy(pts) or _length(route.straight([tuple(p) for p in pts])) <= DETOUR_GAIN * L


def _away(o, c, lo, hi, r):
    """(gap, side) of rectangle r from a stretch that runs beside it (o 'h' at y c, or 'v' at x c, from lo to hi), with the way
    away from the stretch; None when the stretch does not run beside it."""
    x, y, w, h = r
    if o == 'h' and lo < x + w and hi > x:
        return (y - c, 'bottom') if y + h / 2 > c else (c - (y + h), 'top')
    if o == 'v' and lo < y + h and hi > y:
        return (x - c, 'right') if x + w / 2 > c else (c - (x + w), 'left')
    return None


def blockers(sc, pts, a, b, frame_keys=None):
    """[(stretch index, box, side, px)]: each box nearer to a stretch of the path pts than route.BOXM + route.G (its own two aside),
    with the way away from that stretch and the px it must go so that the stretch keeps route.BOXM. With frame_keys (the key of each
    frame of sc.frames for push_box, ('f', k)): also each frame that a stretch runs beside, outside it, nearer than route.FPROX +
    route.G, as (stretch index, its key, side, px) so that the stretch keeps route.FPROX. A box that such a frame holds is not a
    blocker of its own: the frame moves with it."""
    out = []
    m, mf = route.BOXM + route.G, route.FPROX + route.G
    for k, (o, c, lo, hi) in enumerate(route.segments(route.straight([tuple(p) for p in pts]))):
        walls = []
        for key, r in zip(frame_keys or (), sc.frames):
            got = _away(o, c, lo, hi, r)
            if got and 0 <= got[0] < mf:              # beside it, outside: a stretch inside a frame is no matter for a push
                out.append((k, key, got[1], _ceil5(mf - got[0])))
                walls.append(r)
        for n, r in sc.boxes.items():
            if n in (a, b) or n < 0 or any(route.holds(f, r) for f in walls):
                continue
            got = _away(o, c, lo, hi, r)
            if got and got[0] < m:
                out.append((k, n, got[1], _ceil5(m - got[0])))
    return out


OPPOSITE = {'top': 'bottom', 'bottom': 'top', 'left': 'right', 'right': 'left'}
MAX_CANDS = 6               # straighten: at most this many push sets are routed and judged per arrow


def detour_pushes(bl):
    """The push sets to try for the blockers of a probe path: [[(box, side, px)]]. A stretch with blockers on both sides runs
    through a gap too narrow for it: push one side by the whole need of the gap (its own px plus the other side's), or each side
    by its own. A stretch with blockers on one side only can move off them (the real route will), so it pushes nothing, unless no
    stretch is a gap: then every blocker moves by its own px. Sets from several gaps are combined; a box asked to go two ways
    drops that set."""
    by_k = {}
    for k, n, side, d in bl:
        by_k.setdefault(k, []).append((n, side, d))
    gaps = [v for v in by_k.values() if len({OPPOSITE[sd] for _, sd, _ in v} & {sd for _, sd, _ in v}) > 0]
    if not gaps:                                           # every blocker by its own px, each the way it needs least
        least = {}
        for _, n, sd, d in bl:
            if n not in least or d < least[n][1]:
                least[n] = (sd, d)
        return [sorted(((n, sd, d) for n, (sd, d) in least.items()), key=str)] if least else []
    options = []
    for v in gaps:
        sides = sorted({sd for _, sd, _ in v})
        need = {sd: max(d for _, s2, d in v if s2 == sd) for sd in sides}
        opts = [[(n, sd, d) for n, sd, d in v]]            # each side by its own need
        for sd in sides:                                   # one side by the whole need
            far = OPPOSITE[sd]
            if far in need:
                opts.append([(n, sd, d + need[far]) for n, s2, d in v if s2 == sd])
        options.append(opts)
    combos = [[]]
    for opts in options:
        combos = [c + o for c in combos for o in opts][:3 ** 3]
    out = []
    for c in combos:
        merged, ok = {}, True
        for n, sd, d in c:
            if n in merged and merged[n][0] != sd:
                ok = False
                break
            merged[n] = (sd, max(d, merged.get(n, (sd, 0))[1]))
        if ok:
            out.append(sorted(((n, sd, d) for n, (sd, d) in merged.items()), key=str))
    return [c for k, c in enumerate(out) if c not in out[:k]]


def _probe(text, key):
    """The path the arrow would take with no clearance round the other boxes (route.BOXM 0) and PROBE_FPROX round the frame
    borders, in the picture without it."""
    import model
    lines = text.split('\n')
    i = next(i for i, ln in enumerate(lines) if model.svgmeta_arrow(ln) == key)
    t, _ = model.take_out(text, [i])
    sc = model.scene(t)
    keep = route.BOXM, route.FPROX
    route.BOXM, route.FPROX = 0, PROBE_FPROX
    try:
        pts = route.route(sc, key[0], key[1], '*', '*')
    finally:
        route.BOXM, route.FPROX = keep
    return sc, pts


def straighten(text):
    """Route short every detour (detours()) that pushing the boxes next to its probe path opens (module docstring): the push sets
    (detour_pushes) are tried the least total displacement first; the first after which the arrow, routed again, is at most
    DETOUR_GAIN of its old length, with a label and no arrow invalid that was valid, is kept. Returns the text; LOG says what
    moved."""
    import model
    t0 = time.time()
    for key, L, M in detours(text):
        sc, probe = _probe(text, key)
        if not probe or not _better(probe, L) or len(route.straight(probe)) - 2 > DETOUR_BENDS:
            continue
        fkeys = [('f', k) for k in range(len(sc.frames))]            # model.read keeps collapse.parse's order of the frames
        cands = [c for c in detour_pushes(blockers(sc, probe, key[0], key[1], fkeys)) if c and max(d for _, _, d in c) <= PUSH_MAX]
        pushed = [p for p in (_apply(text, c) for c in cands) if p is not None]

        def judge(t, key=key, L=L):
            line = _arrow_line(t, key)
            if line is None:
                return None
            i = t.split('\n').index(line)
            t2, pend = model.take_out(t, [i], keep={i})
            r = model.route_arrows(t2, pend, keep_old=True).text
            line = _arrow_line(r, key)
            ok = line is not None and _better(model.arrow_points(line), L) and _labelled(r, key)
            return r if ok else None

        text, p = _best(text, key, pushed, judge)
        if p:
            new = _length(route.straight(model.arrow_points(_arrow_line(text, key))))
            LOG.append(_describe('straightened (%d -> %dpx)' % (L, new), key, p))
    STATS['secs'] += time.time() - t0
    return text


def report():
    """The lines a script prints after its run: each push kept (LOG), and the time the room pass took. Empty when nothing moved."""
    out = ''.join('PUSH %s\n' % ln for ln in LOG)
    return out + ('push: %d push sets tried, %d kept, %.1f s\n' % (STATS['tried'], STATS['kept'], STATS['secs']) if STATS['tried'] else '')


def selftest():
    """The cascade on a column: a near box takes the whole push, a far one part of it, a box past GAP + d none; a gap with a lane is
    kept whole. reattach keeps the shape. Prints one line per check; returns True when all pass."""
    bad = []

    def check(name, ok, detail=''):
        print('%s %s%s' % ('ok  ' if ok else 'FAIL', name, (': ' + str(detail)) if not ok else ''))
        if not ok:
            bad.append(name)

    col = {1: (0, 0, 100, 60), 2: (0, 90, 100, 60), 3: (0, 200, 100, 60), 4: (0, 400, 100, 60), 5: (300, 90, 100, 60)}
    s = cascade(col, 1, 40)
    check('a near box takes the push less its gap over GAP', abs(s.get(2, 0) - 38) < .01, s)
    check('a box beyond takes what is left (gap 50: 40 - 2 - 22 = 16)', abs(s.get(3, 0) - 16) < .01, s)
    check('a box far below, or beside, does not move', 4 not in s and 5 not in s, s)
    s = cascade(col, 1, 40, lanes=[(75, 0, 100)])
    check('a gap an arrow runs through is kept whole', abs(s.get(2, 0) - 40) < .01, s)
    p = reattach([(0, 0), (100, 0), (100, 200), (300, 200)], -1, (40, 0))
    check('a tip pushed along its stretch: the stretch grows', p == [(0, 0), (100, 0), (100, 200), (340, 200)], p)
    p = reattach([(0, 0), (100, 0), (100, 200)], -1, (30, 0))
    check('a tip pushed across its stretch: it slides, the stretch before grows', p == [(0, 0), (130, 0), (130, 200)], p)
    check('a straight arrow pushed across: cut', reattach([(0, 0), (0, 200)], -1, (30, 0)) is None)
    check('a stretch that would reverse: cut', reattach([(0, 0), (20, 0), (20, 100), (40, 100)], 0, (30, 0)) is None)
    return not bad


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        sys.exit(0 if selftest() else 1)
    sys.exit(__doc__)
