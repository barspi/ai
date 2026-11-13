#!/usr/bin/env python3
"""Add new boxes and arrows to an existing lineage SVG (collapsed or not). Nothing else is redrawn or moved.

usage: add_nodes.py IN.svg OUT.svg SPEC.json [--snapshot snap.json]

The file is the source of truth: a revision starts from the previous file (new_revision.py), is refreshed (refresh_meta.py --apply), gets
its new boxes and arrows from this script, then check_diag.py. The script finds free space for a box and routes every arrow in the
diagram as it is now (route.py reads the current boxes, frames, labels and arrows), then redoes the jump arcs (hops.py).

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
import json, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import draw, hops, model, route, rules, svgmeta

STEP = 10
GAP_X = 205


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
        inside = f[0] + 20 <= r[0] and r[0] + r[2] <= f[0] + f[2] - 20 and f[1] + 40 <= r[1] and r[1] + r[3] <= f[1] + f[3] - 20
        if frame is not None and f == frame:
            if not inside:
                return False
        elif intersects(r, f, 10):
            return False
    return True


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
    _, boxg, _, frames = __import__('collapse').parse(text)
    def frame_by_name(name):
        """The frame whose visible title is `name`, else the first whose title contains it (case ignored)."""
        full = [f for f in frames if svgmeta.frame_name(lines[f['tl']]) == name]
        f = full[0] if full else next(f for f in frames if name.lower() in svgmeta.frame_name(lines[f['tl']]).lower())
        return (f['x'], f['y'], f['w'], f['h']), f
    kept = svgmeta.boxes(text)
    placed_frame = {n: v['frame'] for n, v in kept.items()}         # the frame of every box, for the vote of rules.frame_for
    roots = (svgmeta.read(text) or {}).get('roots', ())
    spec_arrows = [(a['from'], a['to'], a['kind']) for a in spec.get('arrows', [])]

    box_markup, label_markup, path_markup, problems, grow, nopath, drawn = [], [], [], [], {}, [], set()
    for b in spec.get('boxes', []):
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
            spot = place(sc, draw.BOX_W, h, near, going_right, fr, partners)
            if spot is None and fr is not None:                       # no room inside the frame: below its last box, and the frame grows
                members = [r for r in sc.boxes.values() if fr[0] <= r[0] < fr[0] + fr[2] and fr[1] <= r[1] < fr[1] + fr[3]]
                spot = (members[0][0] if members else fr[0] + 60, max([m[1] + m[3] for m in members] + [fr[1] + 40]) + 28)
                grow[fobj['name']] = (fobj, spot[1] + h + 24)
            if spot is None:
                problems.append('NO FREE SPACE for #%s: decide a place yourself ("x", "y" in the spec)' % b['num'])
                continue
            x, y = spot
        b = dict(b, frame=svgmeta.frame_name(lines[fobj['tl']]) if fobj else None, github=records.get(str(b['num'])) or b.get('github'))
        markup, hh = draw.box(ctx, b, x, y)
        box_markup.append(markup)
        sc.boxes[b['num']] = (x, y, float(draw.BOX_W), float(hh))
        if b.get('new'):
            sc.pills.append((x + 3 - 26, y + 3 - 26, 52, 52))
        print('#%s: x %s y %s w %s h %s  (bottom %s)' % (b['num'], draw.fmt(x), draw.fmt(y), draw.BOX_W, draw.fmt(hh), draw.fmt(y + hh)))
        if fr is not None and y + hh + 24 > fr[1] + fr[3]:
            grow[fobj['name']] = (fobj, y + hh + 24)

    maxx = max(r[0] + r[2] for r in sc.boxes.values())
    maxy = max(r[1] + r[3] for r in sc.boxes.values())
    leg = info['legend']
    if leg and maxx + 60 > leg[0]:                       # the legend keeps its place right of the farthest box: move it with the new column
        dx = maxx + 60 - leg[0]
        move_legend(lines, dx)
        sc.bounds = (sc.bounds[0], sc.bounds[1], sc.bounds[2] + dx, sc.bounds[3])
        print('legend moved %s px to the right' % draw.fmt(dx))
        maxx = max(maxx, leg[0] + dx + leg[2])
    for a in spec.get('arrows', []):
        kind = a['kind']
        if kind not in draw.EDGE:
            sys.exit('unknown arrow word "%s": use one of %s' % (kind, ', '.join(draw.EDGE)))
        if 'points' in a:
            pts = [tuple(p) for p in a['points']]
            lab = tuple(a['label']) if 'label' in a else route.place_label(sc, pts, kind)
        else:
            ra, rb = sc.boxes.get(a['from']), sc.boxes.get(a['to'])
            if not ra or not rb:
                problems.append('arrow #%s -> #%s names a box that is not in the diagram' % (a['from'], a['to']))
                continue
            # the router picks the sides: it searches every pair at once (the same side twice too) and keeps the cheapest path. Never
            # try side pairs in a fixed order and take the first that has a path: that took an 8-bend detour out of the far side of a
            # box when the arrow could leave the near side and run down beside its column with 2 bends.
            pts = route.route(sc, a['from'], a['to'], '*', '*')
            if not pts:
                problems.append('NO PATH for #%s %s #%s: kept in the metadata ("nopath"); name it in the box note, and say what would have to move' % (a['from'], kind, a['to']))
                nopath.append((a['from'], a['to'], kind))
                continue
            lab = route.place_label(sc, pts, kind)
        sc.arrows.append(list(pts))
        path_markup.append(draw.arrow(pts, kind, a['from'], a['to']))
        drawn.add((a['from'], a['to']))
        shift = None
        if not lab:                                               # a short arrow: 8px of shaft, else beside its shaft
            any_ = route.place_label_any(sc, pts, kind)
            if any_:
                lab, shift = any_[:2], any_[2]
                if any_[3]:
                    problems.append('the label of #%s %s #%s fits only with less than 20px of shaft (a short arrow): check it by eye'
                                    % (a.get('from', '?'), kind, a.get('to', '?')))
        if lab:
            label_markup += draw.label(kind, lab[0], lab[1], shift)
            dx, dy = shift or (0, 0)
            sc.labels.append((lab[0] + dx - draw.label_width(kind) / 2, lab[1] + dy - 9, draw.label_width(kind), 18.0))
        else:
            problems.append('no free straight stretch for the label of #%s %s #%s' % (a.get('from', '?'), kind, a.get('to', '?')))
        for px, py in pts:
            maxx, maxy = max(maxx, px), max(maxy, py)

    s = '\n'.join(lines)
    ls = s.split('\n')
    i_box = next(i for i, l in enumerate(ls) if l.startswith('<g id="n'))
    i_lbl = next((i for i, l in enumerate(ls) if re.match(r'<rect [^>]*fill="#fffdf7"', l)), None)
    if i_lbl is None:                                           # a diagram with no labels yet: after the last box group
        i_lbl = max(i for i, l in enumerate(ls) if l == '</g>' and any(x.startswith('<g id="n') for x in ls[max(0, i - 60):i])) + 1
    ls[i_lbl:i_lbl] = box_markup + label_markup               # after the last box, before the existing labels
    ls[i_box:i_box] = path_markup                             # arrows under the boxes, like the others
    s = '\n'.join(ls)

    for name, (fobj, bottom) in grow.items():
        pat = re.compile(r'(<rect x="%s" y="%s" width="[\d.]+" height=")[\d.]+(" rx="18")' % (re.escape(draw.fmt(fobj['x'])), re.escape(draw.fmt(fobj['y']))))
        s, n = pat.subn(lambda m: m.group(1) + draw.fmt(bottom - fobj['y']) + m.group(2), s, count=1)
        maxy = max(maxy, bottom)
        print('frame "%s": bottom edge now %s%s' % (name, draw.fmt(bottom), '' if n else ' (NOT CHANGED: edit it by hand)'))
        if any(f['y'] > fobj['y'] and f['y'] < bottom + 10 and f['x'] < fobj['x'] + fobj['w'] and f['x'] + f['w'] > fobj['x'] for f in frames if f is not fobj):
            problems.append('the frame "%s" now touches the frame below it: move that frame down (collapse.py --moves)' % name)

    m = re.match(r'<svg [^>]*width="(\d+)" height="(\d+)" viewBox="0 0 \d+ \d+"', s)
    W, H = int(m.group(1)), int(m.group(2))
    nW, nH = max(W, int(maxx) + 80), max(H, int(maxy) + 70)
    if (nW, nH) != (W, H):
        s = s.replace('width="%d" height="%d" viewBox="0 0 %d %d"' % (W, H, W, H), 'width="%d" height="%d" viewBox="0 0 %d %d"' % (nW, nH, nW, nH), 1)
        s = re.sub(r'<rect x="0" y="0" width="%d" height="%d" fill="(#[0-9a-f]{6})"/>' % (W, H),          # the page, whatever its colour
                   lambda q: '<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (nW, nH, q.group(1)), s, count=1)
        print('canvas %dx%d -> %dx%d' % (W, H, nW, nH))
    s, hops_added, hops_removed = hops.add_hops(s)           # the jump arcs of the whole diagram, recomputed
    # second pass: each new arrow was routed before the boxes and arrows after it in the spec were placed, so a cheaper path may
    # exist now (route.path_cost); reroute.reroute keeps a new path only when it costs less
    import reroute
    s, better, _ = reroute.reroute(s, sorted(drawn), improve=True)
    if better:
        s, _, _ = hops.add_hops(s)
        s, _, _ = model.relabel(s, hop_pad=20)
        s, _, nolab = model.label_missing(s, [(d[0], d[1]) for d in better])
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
    print('wrote %s: %d boxes, %d arrows, %d jump arcs added, %d stale removed' % (out, len(box_markup), len(path_markup), hops_added, hops_removed))
    for p in problems:
        print('PROBLEM', p)
    print('next: check_diag.py %s <previous revision>' % out)


if __name__ == '__main__':
    main()
