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
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typing import NamedTuple
import collapse, draw

TOUCH = 1.0              # px: two blocks that share no more than this of x (or of y) do not touch
CANVAS_BOTTOM = 80       # px of page below the lowest frame or box (collapse.py keeps the same)
BOTTOM_PAD = 30          # px a frame keeps below its lowest box when it grows to hold one (add_nodes.py, move.py)
ATTACH = 3.0             # px: an arrow end this close to a box side is on that box (collapse.py's attach)


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


def _arrow_points(line):
    d = line.split('"')[1]
    return [(float(a), float(b)) for a, b in re.findall(r'(-?[\d.]+),(-?[\d.]+)', re.sub(r'A[^L]*', '', d))]


def _shift_path(line, dy):
    """The arrow line with every point of its path dy lower (the arc flags and radii have no comma, so they stay)."""
    d = line.split('"')[1]
    nd = re.sub(r'(-?[\d.]+),(-?[\d.]+)', lambda m: '%s,%s' % (m.group(1), collapse.fmt(float(m.group(2)) + dy)), d)
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


def grow(text, frame, dy, members=()):
    """Grow the frame whose rectangle is `frame` (x, y, w, h) by dy px at its bottom and push down what lies below (module
    docstring). members: boxes that belong to the frame although they lie below its bottom border (a box it grows to hold); they
    stay where they are. Returns a Push."""
    lines, box, pop, fr = collapse.parse(text)
    rects = [_rect(f) for f in fr]
    hit = [k for k, r in enumerate(rects) if all(abs(a - b) < .5 for a, b in zip(r, frame))]
    if not hit:
        raise ValueError('no frame at %s' % (frame,))
    boxes = {n: _rect(b) for n, b in box.items()}
    grow_k, move_k, move_b = cascade(rects, boxes, rects[hit[0]], members)
    out = list(lines)
    changes = []
    for k in grow_k | move_k:
        x, y, w, h = rects[k]
        new = (x, y + dy, w, h) if k in move_k else (x, y, w, h + dy)
        f = fr[k]
        out[f['rl']] = re.sub(r'\by="[\d.-]+"', 'y="%s"' % collapse.fmt(new[1]), out[f['rl']], count=1)
        out[f['rl']] = re.sub(r'\bheight="[\d.]+"', 'height="%s"' % collapse.fmt(new[3]), out[f['rl']], count=1)
        if k in move_k:
            out[f['tl']] = collapse.shift_y_line(out[f['tl']], dy)
        changes.append(((x, y, w, h), new))
    for n in move_b:
        b = box[n]
        for a, z in [(b['a'], b['b'])] + ([pop[n]] if n in pop else []):
            for i in range(a, z + 1):
                out[i] = collapse.shift_y_line(out[i], dy)
    # what changed place: old and new rectangles of the moved blocks, and the band each grown frame gained
    swept = [r for k in move_k for r in (rects[k], (rects[k][0], rects[k][1] + dy) + rects[k][2:])]
    swept += [r for n in move_b for r in (boxes[n], (boxes[n][0], boxes[n][1] + dy) + boxes[n][2:])]
    swept += [(rects[k][0], rects[k][1] + rects[k][3], rects[k][2], dy) for k in grow_k]
    cut, rigid = [], []
    for i, ln in enumerate(lines):
        if not (ln.startswith('<path d="M') and 'marker-end' in ln):
            continue
        pts = _arrow_points(ln)
        ends = {_end_box(pts[0], boxes), _end_box(pts[-1], boxes)}
        if None in ends:
            continue                                     # an arrow that ends on no box is the checker's to report
        if ends <= move_b:
            out[i] = _shift_path(ln, dy)
            rigid.append(i)
        elif ends & move_b or any(_meets(s, r) for s in _segments(pts) for r in swept):
            cut.append(i)
    for rng in labels_of(lines, rigid).values():
        for j in rng:
            out[j] = collapse.shift_y_line(out[j], dy)
    res = '\n'.join(out)
    lowest = max([y + h + (dy if k in grow_k | move_k else 0) for k, (x, y, w, h) in enumerate(rects)] +
                 [b[1] + b[3] + (dy if n in move_b else 0) for n, b in boxes.items()])
    res = set_canvas_height(res, lowest + CANVAS_BOTTOM)
    return Push(res, frozenset(move_b), tuple(changes), tuple(cut))


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


def selftest():
    """The cascade on fixed frames: a frame below moves, then the one below that; one beside does not; two that touch both move;
    a box under the grown frame moves, one inside it does not; nothing ends overlapping."""
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
    print('frames self-test: %s' % ('OK' if not bad else 'FAILED: ' + '; '.join(bad)))
    return not bad


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        sys.exit(0 if selftest() else 1)
    sys.exit(__doc__)
