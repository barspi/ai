#!/usr/bin/env python3
"""Add new boxes and arrows to an existing lineage SVG (collapsed or not). Nothing else is redrawn or moved, but for one case: a frame
with no room grows down (frames.grow), and what lies below it moves down by as much, its cut arrows routed again.

usage: add_nodes.py IN.svg OUT.svg SPEC.json [--snapshot snap.json]

The file is the source of truth: a revision starts from the previous file (new_revision.py), is refreshed (refresh_meta.py --apply), gets
its new boxes and arrows from this script, then check_diag.py. The script finds free space for a box and routes every arrow in the
diagram as it is now (route.py reads the current boxes, frames, labels and arrows), then redoes the jump arcs (hops.py).
A box goes in free space beside `near` (rules.near_for when the spec has none). A box joined to `near` by a strong arrow
(ADJACENT_KINDS: a closing pull request and its issue above all) lands next to it (next_to_near): a free spot on its right, right
above or right under it; else the few boxes in the best such spot move a little along their column (push.push_box, the cascade in
the frame; the least displacement, push._best), first with no frame growth, then letting the frame grow from that row; landing
anywhere else is a PROBLEM. When its frame has no free spot, it goes at the frame's bottom, beside `near` where it can (bottom_spot;
a PROBLEM when that is not next to `near`), and the frame grows to hold it: frames.grow pushes down every frame and box
below that overlaps it horizontally, so the box never lands on the frame below. Arrows go through model.route_arrows: an arrow between
two boxes of one frame never leaves it (the frame grows when it has no room), and each path leaves room for its label where one of
the cheapest paths can.

SPEC.json:
{ "repo": "owner/name",
  "boxes":  [ {"num": 123, "state": "open|closed|handclosed|merged|waiting|draft|prclosed",
               "title": "...", "meta": "opened 2026-01-05 · still open", "notes": ["line", ...], "mono": "merge abc1234 (a, b)",
               "assignees": ["login"]      (an issue; empty or missing -> "?")
               "author": "login"           (a pull request: "by login")
               "umbrella": true            (an issue with sub-issues: the umbrella emoji, thick border, inner frame)
               "new": true                 (the red `new` pill)
               "near": 120                 (optional: the box it relates to; the new box goes beside it, right of it when the arrow leaves it.
                                            Left out: rules.near_for, the neighbour with the most important arrow, ties the lowest number)
               "frame": "guest checkout"   (optional: put it inside that dotted frame; the frame grows when needed. Left out: rules.frame_for
                                            votes with the arrows (printed); "" puts the box outside every frame)
               "x": 4825, "y": 4292        (optional: a place you decided yourself) } ],
  "arrows": [ {"from": 120, "to": 123, "kind": "follow-up"} ] }       (kinds: the vocabulary in SKILL.md; read A, kind, B)

An arrow may also give "points" [[x, y], ...] and "label" [x, y] to place it by hand; that is for a user who asked for a special shape.
Each new box gets data-frame (the full title of its frame) and, with --snapshot, data-github (its record); each arrow gets data-from,
data-to and data-kind; an arrow with NO PATH goes into the metadata block's "nopath" (svgmeta.py). A new box with no record yet gets one
at the next refresh_meta.py.
Prints every new box as `x y w h`, and a PROBLEM line for whatever it could not do (no free space, no path, no room for a label): say so
to the user; do not draw it worse by hand.
"""
import json, math, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import draw, hops, model, route, rules, svgmeta

STEP = 10
GAP_X = 205
ADJACENT_KINDS = ('closed by', 'work done by', 'child', 'revised by')   # a new box joined to `near` by one of these lands next to it
ROW_GAP = 30          # px between two boxes of a column (is_free keeps it)
NEXT_TO_ROWS = 2      # next to `near` on its right: its top within near's height plus this many ROW_GAPs of near's top
COLUMN_GAP = 80       # px between `near` and a new box right above or under it: a vertical arrow with its label fits between them
                      # (an 18px label, route.LABEL_SHAFT on each side, an 11px head); next to it in its column: no more than this


def intersects(a, b, pad=0):
    return a[0] - pad < b[0] + b[2] and a[0] + a[2] + pad > b[0] and a[1] - pad < b[1] + b[3] and a[1] + a[3] + pad > b[1]


def is_free(sc, r, frame=None):
    """Is the rectangle r free: no box within 30px, no label or pill, no arrow within 14px, and no frame border (inside `frame` it must fit)."""
    if any(intersects(r, b, 30) for b in sc.boxes.values()) or any(intersects(r, l, 4) for l in sc.labels + sc.pills):
        return False
    for pts in sc.arrows:
        for o, c, lo, hi in route.segments(pts):
            if (o == 'h' and r[1] - 14 < c < r[1] + r[3] + 14 and lo < r[0] + r[2] + 14 and hi > r[0] - 14) or \
               (o == 'v' and r[0] - 14 < c < r[0] + r[2] + 14 and lo < r[1] + r[3] + 14 and hi > r[1] - 14):
                return False
    for f in sc.frames:
        if frame is not None and f == frame:
            if not inside_frame(r, f):
                return False
        elif intersects(r, f, 10):
            return False
    return True


def inside_frame(r, f):
    """Does rectangle r sit inside frame f with the margins a box keeps (20px from the sides and the bottom, 40px under the title)?"""
    return f[0] + 20 <= r[0] and r[0] + r[2] <= f[0] + f[2] - 20 and f[1] + 40 <= r[1] and r[1] + r[3] <= f[1] + f[3] - 20


def next_to(spot, w, h, nr):
    """Is a w x h box at spot (x, y) next to the box nr (NEXT_TO_ROWS)?"""
    x, y = spot
    nx, ny, nw, nh = nr
    reach = NEXT_TO_ROWS * ROW_GAP
    right = 0 <= x - (nx + nw) <= GAP_X + ROW_GAP and abs(y - ny) <= nh + reach
    gap = max(ny - (y + h), y - (ny + nh))                     # between the two in one column (negative: they overlap)
    return right or (abs(x - nx) <= ROW_GAP and 0 <= gap <= COLUMN_GAP)


def _next_spots(sc, w, h, near, frame):
    """The spots next to `near`, as offsets from its top-left corner: on its right (on a column the frame has within ROW_GAP) from
    level with it outwards, then right under it, then right above it."""
    nx, ny, nw, nh = sc.boxes[near]
    xr = nx + nw + GAP_X
    if frame is not None:
        xr = next((b[0] for b in sc.boxes.values() if route.holds(frame, b) and abs(b[0] - xr) <= ROW_GAP), xr)
    out = [(xr - nx, s * k * STEP) for k in range(int((nh + NEXT_TO_ROWS * ROW_GAP) // STEP) + 1) for s in ((1, -1) if k else (1,))]
    return out + [(0, nh + COLUMN_GAP), (0, -h - COLUMN_GAP)]


def next_to_near(text, w, h, near, frame, fname, num):
    """A spot next to `near` (next_to) for a new w x h box in `frame` (found again by its title fname after a push), and the text:
    a free spot (is_free), else room made by pushing the boxes that sit in a spot (beside near level with it, right under it, right
    above it) along their column, away from near (beside it: those above the spot's middle up, the others down), each by what it
    lacks of ROW_GAP (push.push_box: what
    they would hit moves too, inside the frame). Each spot's push is settled (its cut arrows routed again) and scored by push._best:
    total displacement plus the growth of the arrows it cut, the least wins. First no push may grow the frame; then one may (the
    frame grows from the pushed boxes' row). Returns (text, (x, y) or None, description of the push or '')."""
    import frames, push
    sc, _ = model.read(text)
    nx, ny = sc.boxes[near][:2]
    for dx, dy in _next_spots(sc, w, h, near, frame):
        if is_free(sc, (nx + dx, ny + dy, w, h), frame):
            return text, (nx + dx, ny + dy), ''
    nh = sc.boxes[near][3]
    offsets = [(*_next_spots(sc, w, h, near, frame)[0], None), (0, nh + COLUMN_GAP, 'bottom'), (0, -h - COLUMN_GAP, 'top')]

    def spot_of(t):                                            # the frame and near as they are in t
        s2, _ = model.read(t)
        return s2, (frames.by_name(t, fname) if fname else None), s2.boxes[near][:2]
    for grow in (False, True):
        sets, where = [], {}
        for dx, dy, way in offsets:
            s = (nx + dx, ny + dy, w, h)
            if frame is not None and not inside_frame(s, frame):
                continue
            mine = {n: r for n, r in sc.boxes.items() if n != near and n >= 0 and (frame is None or route.holds(frame, r))}
            ways = {n: way or ('top' if r[1] + r[3] / 2 < s[1] + h / 2 else 'bottom') for n, r in mine.items() if intersects(s, r, ROW_GAP)}
            moves = [(n, sd, math.ceil(mine[n][1] + mine[n][3] + ROW_GAP - s[1] if sd == 'top' else s[1] + h + ROW_GAP - mine[n][1]))
                     for n, sd in ways.items()]
            if not moves or max(d for _, _, d in moves) > push.PUSH_MAX:
                continue
            p = push._apply(text, moves)
            if p is None or (p.grown and not grow):
                continue
            sets.append(p)
            where[id(p)] = (dx, dy)

        def judge(t, p):
            s2, fr2, (x2, y2) = spot_of(t)
            dx, dy = where[id(p)]
            r = (x2 + dx, y2 + dy, w, h)
            ok = not any(intersects(r, b, ROW_GAP) for n, b in s2.boxes.items()) and (fr2 is None or inside_frame(r, fr2))
            return t if ok else None
        t, p = push._best(text, None, sets, judge)
        if p:
            _, _, (x2, y2) = spot_of(t)
            dx, dy = where[id(p)]
            return t, (x2 + dx, y2 + dy), push._describe('room next to', (near, num, 'for'), p)
    return text, None, ''


def place(sc, w, h, near, going_right, frame, partners=()):
    """Top-left corner for a new box. partners: the boxes it has arrows to (in the diagram). With two or more, every candidate column
    (beside `near`, and every column of the frame) gives its nearest free spot above and below `near`'s top, and the spot with the least
    total distance to all partners wins (box centres, Manhattan; ties: the earlier candidate). Never the first spot that is free: that
    put a box with arrows to three boxes beside one of them and 900px from the others. With fewer partners: beside `near` (right of it
    when the arrow leaves it), the nearest free spot, scanning up and down."""
    rects = [sc.boxes[p] for p in partners if p in sc.boxes]
    if len(rects) >= 2 and near in sc.boxes:
        return _place_best(sc, w, h, near, going_right, frame, rects)
    if near in sc.boxes:
        nx, ny, nw, nh = sc.boxes[near]
        xs = [nx + nw + GAP_X, nx - w - GAP_X] if going_right else [nx - w - GAP_X, nx + nw + GAP_X]
        xs += [nx + nw + 2 * GAP_X + w, nx]
        y0 = ny
    else:
        xs = [80]
        y0 = max([b[1] + b[3] for b in sc.boxes.values()] + [190]) + 60
    if frame is not None:
        cols = sorted({b[0] for b in sc.boxes.values() if frame[0] <= b[0] < frame[0] + frame[2] and frame[1] <= b[1] < frame[1] + frame[3]})
        xs = ([c for c in xs if c in cols] or cols or [frame[0] + 60]) + xs
    for x in xs:
        for k in range(0, 300):
            for y in ((y0 + k * STEP, y0 - k * STEP) if k else (y0,)):
                if y < 190:
                    continue
                if is_free(sc, (x, y, w, h), frame):
                    return x, y
    return None


def _place_best(sc, w, h, near, going_right, frame, rects):
    nx, ny, nw, nh = sc.boxes[near]
    xs = [nx + nw + GAP_X, nx - w - GAP_X] if going_right else [nx - w - GAP_X, nx + nw + GAP_X]
    xs += [nx + nw + 2 * GAP_X + w, nx]
    if frame is not None:
        xs += sorted({b[0] for b in sc.boxes.values() if frame[0] <= b[0] < frame[0] + frame[2] and frame[1] <= b[1] < frame[1] + frame[3]})
    seen, cands = set(), []
    for x in xs:
        if round(x) in seen:
            continue
        seen.add(round(x))
        for sign in (1, -1):                                   # the nearest free spot below, then above, the top of `near`
            for k in range(0, 300):
                y = ny + sign * k * STEP
                if y < 190:
                    break
                if is_free(sc, (x, y, w, h), frame):
                    cands.append((x, y))
                    break

    def cost(c):
        cx, cy = c[0] + w / 2, c[1] + h / 2
        return sum(abs(cx - (r[0] + r[2] / 2)) + abs(cy - (r[1] + r[3] / 2)) for r in rects)
    return min(cands, key=cost) if cands else None


def bottom_spot(sc, w, h, near, frame):
    """When `frame` has no free spot: the place at its bottom, just under the lowest box of a column and clear of the arrows there.
    Returns (x, y, px the frame must grow by so the box keeps frames.BOTTOM_PAD above its bottom border). The columns of `near` come
    first (right of it, under it, left of it), the spot among them that needs the least growth; any other column of the frame only
    when `near` is not in it. Only what the frame holds counts as an obstacle: whatever lies below its bottom border is pushed down
    by the growth (frames.grow), and an arrow that reaches below it is cut and routed again."""
    import frames
    fx, fy, fw, fh = frame
    bottom = fy + fh
    members = {n: r for n, r in sc.boxes.items() if route.holds(frame, r)}
    xs = []
    if near in members:
        nx, _, nw, _ = members[near]
        xs = [nx + nw + GAP_X, nx, nx - w - GAP_X]
    cols = sorted({r[0] for r in members.values()})
    xs = [next((c for c in cols if abs(c - x) <= 30), x) for x in xs]   # beside `near`, but on a column the frame has when one is that close
    near_cols = set(xs)
    xs += cols
    xs = [x for x in dict.fromkeys(xs) if fx + 20 <= x and x + w <= fx + fw - 20]
    tall_frame = (fx, fy, fw, fh + 10 ** 5)                     # the frame as it will be once grown
    held = model.route.Scene(members, [tall_frame], [r for r in sc.labels if r[1] < bottom], [r for r in sc.pills if r[1] < bottom],
                             [[p for p in pts] for pts in sc.arrows if max(y for _, y in pts) < bottom], sc.bounds)
    best = None
    for k, x in enumerate(xs):
        y = max([r[1] + r[3] for r in members.values() if r[0] < x + w + 30 and x < r[0] + r[2] + 30] + [fy + 10]) + 30
        while not is_free(held, (x, y, w, h), tall_frame):
            y += STEP
        need = float(math.ceil(max(0.0, y + h + frames.BOTTOM_PAD - bottom)))
        key = (x not in near_cols, need, k)
        if best is None or key < best[0]:
            best = (key, (x, y, need))
    return best[1] if best else None


def make_room(text, frame, spot, h, near, rounds=3):
    """Grow `frame` for the spot bottom_spot chose and settle the push before the box goes in: the arrows the push cut are routed
    again at once (model.route_arrows; one with no path keeps its old markup). Then the spot is checked against the picture as it
    now is, every arrow included: when an arrow runs there, the spot moves down at most two box heights to a free place (the frame
    grows again when it must); else it stays, and main() routes again the arrows the box lands on (model.settle). The frame is
    found again by its title; when routing the cut arrows inflated it (frames.inflate moves things), the spot is chosen again.
    Returns (text, (x, y), px grown in all, [PROBLEM lines])."""
    import frames
    x, y, need = spot
    grown, problems = 0.0, []
    name = frames.name_of(text, frame)
    for _ in range(rounds):
        if need > 0:
            frame = frames.by_name(text, name)
            push = frames.grow(text, frame, need)
            text, cut = model.take_out(push.text, push.cut, keep=push.cut)
            res = model.route_arrows(text, cut)
            text, grown = res.text, grown + need
            problems += ['NO PATH for #%s %s #%s after a frame grew (%s): its old path stays, and check_diag.py fails it'
                         % (a, k, b, why) for a, b, k, why in res.failed]
        sc, _ = model.read(text)
        now = frames.by_name(text, name)
        if now[:2] != frame[:2] or now[2] != frame[2]:      # inflated while its cut arrows were routed: choose the spot again
            again = bottom_spot(sc, draw.BOX_W, h, near, now)
            x, y = again[:2] if again else (x, y)
        frame = now
        tall = (frame[0], frame[1], frame[2], frame[3] + 10 ** 5)
        probe = model.route.Scene(sc.boxes, [tall if f == frame else f for f in sc.frames], sc.labels, sc.pills, sc.arrows, sc.bounds)
        free = next((y2 for y2 in range(int(y), int(y + 2 * h) + 1, STEP) if is_free(probe, (x, y2, draw.BOX_W, h), tall)), y)
        y, need = free, float(math.ceil(max(0.0, free + h + frames.BOTTOM_PAD - (frame[1] + frame[3]))))
        if need == 0:
            break
    return text, (x, y), grown, problems


def insert_box(text, markup, before_boxes=False):
    """Insert lines of markup: a box after the last box (before the first label, which is drawn over the boxes); with before_boxes,
    an arrow before the first box (arrows are drawn under the boxes)."""
    ls = text.split('\n')
    if before_boxes:
        k = next(i for i, l in enumerate(ls) if l.startswith('<g id="n'))
    else:
        k = next((i for i, l in enumerate(ls) if re.match(r'<rect [^>]*fill="#fffdf7"', l)), None)
        if k is None:
            k = max(i for i, l in enumerate(ls) if l == '</g>' and any(x.startswith('<g id="n') for x in ls[max(0, i - 60):i])) + 1
    ls[k:k] = markup.split('\n') if isinstance(markup, str) else markup
    return '\n'.join(ls)


def move_legend(lines, dx):
    """Shift the legend block (between <!--legend--> markers, else from its background rectangle to the first line that is not part of it)."""
    a = next((i for i, l in enumerate(lines) if l == '<!--legend-->'), None)
    if a is not None:
        b = lines.index('<!--/legend-->')
        rng = range(a + 1, b)
    else:
        a = next(i for i, l in enumerate(lines) if 'fill="#fbfaf6"' in l and 'rx="14"' in l)
        b = a
        while b + 1 < len(lines) and re.match(r'<(text class="(lg|lgb|pill)"|line |rect )', lines[b + 1]):
            b += 1
        rng = range(a, b + 1)
    for i in rng:
        lines[i] = re.sub(r'\b(x|x1|x2)="(-?[\d.]+)"', lambda m: '%s="%s"' % (m.group(1), draw.fmt(float(m.group(2)) + dx)), lines[i])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    snap = None
    if '--snapshot' in sys.argv:
        snap = sys.argv[sys.argv.index('--snapshot') + 1]
        args = [a for a in args if a != snap]
    if len(args) != 3:
        sys.exit(__doc__)
    src, out, spec_path = args
    text = open(src, encoding='utf-8').read()
    spec = json.load(open(spec_path, encoding='utf-8'))
    if not spec.get('repo'):
        sys.exit('the spec needs "repo": "owner/name" (the links of the new boxes point there)')
    sc, info = model.read(text)
    lines = info['lines']
    titles = dict(info['titles'])
    records = {}
    if snap:
        records = {k: v for k, v in json.load(open(snap)).items() if isinstance(v, dict) and 'title' in v}
        titles.update({k: v['title'] for k, v in records.items()})
    for b in spec.get('boxes', []):
        titles[str(b['num'])] = b['title']
        if b['num'] in sc.boxes:
            sys.exit('#%s is already in %s' % (b['num'], src))
    prs = set(info['prs']) | {b['num'] for b in spec.get('boxes', []) if draw.STY[b['state']]['kind'] == 'PR'}
    ctx = draw.Ctx(spec['repo'], titles, prs)
    kept = svgmeta.boxes(text)
    placed_frame = {n: v['frame'] for n, v in kept.items()}         # the frame of every box, for the vote of rules.frame_for
    roots = (svgmeta.read(text) or {}).get('roots', ())
    spec_arrows = [(a['from'], a['to'], a['kind']) for a in spec.get('arrows', [])]

    import collapse, frames
    problems, nopath, pending = [], [], []
    for b in spec.get('boxes', []):
        lines = text.split('\n')
        _, _, _, frs = collapse.parse(text)

        def frame_by_name(name):
            """The frame whose visible title is `name`, else the first whose title contains it (case ignored)."""
            full = [f for f in frs if svgmeta.frame_name(lines[f['tl']]) == name]
            f = full[0] if full else next(f for f in frs if name.lower() in svgmeta.frame_name(lines[f['tl']]).lower())
            return (f['x'], f['y'], f['w'], f['h']), f
        h = draw.box_height(b)
        fr, fobj = (None, None)
        mine = [e for e in spec_arrows if b['num'] in e[:2]]
        if 'frame' not in b:                                          # decided by rule, never by guess
            f, _, why = rules.frame_for(b['num'], mine, placed_frame, roots)
            print('#%s: frame %s by rule (%s)' % (b['num'], repr(f) if f else 'none', why))
            if why.startswith('ASK'):
                problems.append('#%s: %s' % (b['num'], why))
            b = dict(b, frame=f)
        if 'near' not in b:
            b = dict(b, near=rules.near_for(b['num'], mine, set(sc.boxes)))
        placed_frame[b['num']] = b.get('frame') or None
        if b.get('frame'):
            try:
                fr, fobj = frame_by_name(b['frame'])
                fname = svgmeta.frame_name(lines[fobj['tl']])          # the frame is found by its title from here on
            except StopIteration:
                sys.exit('no frame with "%s" in its title' % b['frame'])
        if 'x' in b and 'y' in b:
            x, y = float(b['x']), float(b['y'])
        else:
            near = b.get('near')
            going_right = True
            for a in spec.get('arrows', []):
                if a.get('to') == b['num'] and a.get('from') == near:
                    going_right = True
                if a.get('from') == b['num'] and a.get('to') == near:
                    going_right = False
            partners = [a.get('to') if a.get('from') == b['num'] else a.get('from') for a in spec.get('arrows', []) if b['num'] in (a.get('from'), a.get('to'))]
            strong = near in sc.boxes and (fr is None or route.holds(fr, sc.boxes[near])) and any(
                {a.get('from'), a.get('to')} == {b['num'], near} and a.get('kind') in ADJACENT_KINDS for a in spec.get('arrows', []))
            spot, at_bottom = None, False
            if strong:                                                # next to `near`, making room there when it must
                text, spot, how = next_to_near(text, draw.BOX_W, h, near, fr, fname if fobj else None, b['num'])
                if how:
                    print('PUSH', how)
                sc, _ = model.read(text)
                fr = frames.by_name(text, fname) if fobj else None
            if spot is None:
                spot = place(sc, draw.BOX_W, h, near, going_right, fr, partners)
            if spot is None and fr is not None:                       # the frame is full: its bottom, beside `near`; the frame grows
                bs = bottom_spot(sc, draw.BOX_W, h, near, fr)
                if bs:
                    text, spot, px, lost = make_room(text, fr, bs, h, near)
                    print('frame "%s" grown %spx; what lies below moved down' % (fobj['name'], draw.fmt(px)))
                    problems += lost
                    sc, _ = model.read(text)
                    at_bottom = True
            if spot is not None and near in sc.boxes and (strong or at_bottom) and not next_to(spot, draw.BOX_W, h, sc.boxes[near]):
                problems.append('#%s landed at (%s, %s), not next to #%s: decide a place yourself ("x", "y" in the spec), or move boxes'
                                % (b['num'], draw.fmt(spot[0]), draw.fmt(spot[1]), near))
            if spot is None:
                problems.append('NO FREE SPACE for #%s: decide a place yourself ("x", "y" in the spec)' % b['num'])
                continue
            x, y = spot
        b = dict(b, frame=fname if fobj else None, github=records.get(str(b['num'])) or b.get('github'))
        markup, hh = draw.box(ctx, b, x, y)
        before_box = text
        text = insert_box(text, markup)
        text, n_moved, more = model.settle(before_box, text)   # an arrow the box landed on is routed again round it
        problems += more
        if n_moved:
            print('#%s: %d arrows it landed on routed again' % (b['num'], n_moved))
        print('#%s: x %s y %s w %s h %s  (bottom %s)' % (b['num'], draw.fmt(x), draw.fmt(y), draw.BOX_W, draw.fmt(hh), draw.fmt(y + hh)))
        if fr is not None:                                            # a box given by hand, lower than the frame: the frame grows
            cur = frames.by_name(text, fname)
            need = y + hh + frames.BOTTOM_PAD - (cur[1] + cur[3])
            if need > 0:
                push = frames.grow(text, cur, need, members={b['num']})
                text, cut = model.take_out(push.text, push.cut, keep=push.cut)
                pending += cut
        sc, _ = model.read(text)

    sc, info = model.read(text)
    leg = info['legend']
    maxx = max(r[0] + r[2] for r in sc.boxes.values())
    if leg and maxx + 60 > leg[0]:                       # the legend keeps its place right of the farthest box: move it with the new column
        dx = maxx + 60 - leg[0]
        lines = text.split('\n')
        move_legend(lines, dx)
        text = '\n'.join(lines)
        print('legend moved %s px to the right' % draw.fmt(dx))
    drawn = set()
    for a in spec.get('arrows', []):
        kind = a['kind']
        if kind not in draw.EDGE:
            sys.exit('unknown arrow word "%s": use one of %s' % (kind, ', '.join(draw.EDGE)))
        if 'points' in a:                                    # a shape the user asked for: drawn as given
            pts = [tuple(p) for p in a['points']]
            lab = tuple(a['label']) if 'label' in a else route.place_label(model.read(text)[0], pts, kind)
            text = insert_box(text, [draw.arrow(pts, kind, a['from'], a['to'])] + (draw.label(kind, *lab) if lab else []), before_boxes=True)
            drawn.add((a['from'], a['to']))
            continue
        if a['from'] not in sc.boxes or a['to'] not in sc.boxes:
            problems.append('arrow #%s -> #%s names a box that is not in the diagram' % (a['from'], a['to']))
            continue
        text, p = model.new_arrow(text, a['from'], a['to'], kind)
        pending.append(p)
    # the router picks the sides (every pair at once, the cheapest path); an arrow inside one frame never leaves it, and its frame
    # grows when it has no room (model.route_arrows, frames.grow); each path leaves room for its label where it can
    res = model.route_arrows(text, pending)
    s = res.text
    new_pairs = {(a['from'], a['to']) for a in spec.get('arrows', [])}
    for a_, b_, kind, why in res.failed:
        if (a_, b_) in new_pairs:
            problems.append('NO PATH for #%s %s #%s (%s): kept in the metadata ("nopath"); name it in the box note, and say what would '
                            'have to move' % (a_, kind, b_, why))
        else:
            problems.append('NO PATH for #%s %s #%s after a frame grew (%s): its old path stays, and check_diag.py fails it' % (a_, kind, b_, why))
            continue
        nopath.append((a_, b_, kind))
    problems += ['frame "%s" inflated (%s) to make room for an arrow' % g for g in res.grown]
    problems += ['NOT DRAWN #%s %s #%s: %s' % (a_, kind, b_, why) for a_, b_, kind, why in res.noted]
    problems += ['WARN: #%s -> #%s: no path of the cheapest had room for the full label' % (a_, b_) for a_, b_, _, room in res.routed if not room]
    problems += [model.no_label(x) for x in res.unlabelled]
    drawn |= {(a_, b_) for a_, b_, _, _ in res.routed}
    sc, _ = model.read(s)
    W = int(re.match(r'<svg [^>]*width="(\d+)"', s).group(1))
    nW = max([W] + [int(r[0] + r[2]) + 80 for r in sc.boxes.values()] + [int(x) + 80 for pts in sc.arrows for x, _ in pts])
    if nW != W:
        m = re.match(r'<svg [^>]*width="(\d+)" height="(\d+)" viewBox="0 0 \d+ \d+"', s)
        H = int(m.group(2))
        s = s.replace('width="%d" height="%d" viewBox="0 0 %d %d"' % (W, H, W, H), 'width="%d" height="%d" viewBox="0 0 %d %d"' % (nW, H, nW, H), 1)
        s = re.sub(r'<rect x="0" y="0" width="%d" height="%d" fill="(#[0-9a-f]{6})"/>' % (W, H),
                   lambda q: '<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (nW, H, q.group(1)), s, count=1)
        print('canvas width %d -> %d' % (W, nW))
    # second pass: each new arrow was routed before the boxes and arrows after it in the spec were placed, so a cheaper path may
    # exist now (route.path_cost); reroute.reroute keeps a new path only when it costs less
    import reroute
    s, better, _ = reroute.reroute(s, sorted(drawn & new_pairs), improve=True)
    if better:
        s, nolab = model.finish(s, [(d[0], d[1]) for d in better])
        for a_, b_, bends, _, old_bends in better:
            print('routed again: #%d -> #%d, %d bends (was %d)' % (a_, b_, bends, old_bends))
        problems += [model.no_label(x) for x in nolab]
    meta = svgmeta.read(s)
    if meta is None:
        problems.append('%s has no metadata block (drawn before svgmeta.py): run svgmeta.py migrate on it first' % src)
    else:
        meta['nopath'] = [x for x in meta['nopath'] if (x['from'], x['to']) not in drawn]      # drawn now: no longer "not drawn"
        for x, y, kind in nopath:
            svgmeta.add_nopath(meta, x, y, kind, 'no clean path when it was added')
        s = svgmeta.write(s, meta)
    open(out, 'w', encoding='utf-8').write(s)
    used = {a['kind'] for a in spec.get('arrows', [])}
    missing = [k for k in used if '>%s<' % draw.esc(k) not in s]
    if missing:
        problems.append('the legend has no line for: %s (add one)' % ', '.join(missing))
    print('wrote %s: %d boxes, %d arrows' % (out, len(spec.get('boxes', [])), len(drawn & new_pairs)))
    for p in dict.fromkeys(problems):
        print('PROBLEM', p)
    print('inflate: %d calls, %.3f s' % (frames.STATS['inflate'], frames.STATS['inflate_secs']))
    print(__import__('push').report(), end='')
    print('next: check_diag.py %s <previous revision>' % out)


if __name__ == '__main__':
    main()
