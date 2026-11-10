#!/usr/bin/env python3
"""Read the geometry of a lineage SVG (boxes, frames, labels, `new` pills, arrows) into a route.Scene, so the router sees the diagram as it is.

    sc, info = model.read(svg_text)
    info: {'lines': [...], 'titles': {num: title}, 'prs': {num}, 'right': x, 'bottom': y, 'legend': (x, y, w, h) or None}
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, route


def arrow_points(line):
    d = line.split('"')[1]
    return [(float(a), float(b)) for a, b in re.findall(r'(-?[\d.]+),(-?[\d.]+)', re.sub(r'A[^L]*', '', d))]


MARKER_KIND = {'h-child': 'child', 'h-closed': 'closed by', 'h-work': 'work done by', 'h-led': 'led to', 'h-blocked': 'blocked by',
               'h-ref': 'related', 'h-cross': 'supersedes', 'h-evid': 'evidence, does not close', 'h-dup': 'duplicate of'}


def _side(p, r, tol=1.5):
    x, y, w, h = r
    if y - 1 <= p[1] <= y + h + 1:
        if abs(p[0] - (x + w)) < tol:
            return 'R'
        if abs(p[0] - x) < tol:
            return 'L'
    if x - 1 <= p[0] <= x + w + 1:
        if abs(p[1] - y) < tol:
            return 'T'
        if abs(p[1] - (y + h)) < tol:
            return 'B'
    return None


def repair(text, count_only=False):
    """Route again every arrow that a move or a collapse left invalid: an end that touches no box, a run through a box, or a run closer
    than 14px beside another arrow. The others stay as they are. Returns (text, rerouted, problems)."""
    sc, info = read(text)
    lines = info['lines']
    arrows = []                                           # (line index, points, tail box, tip box)
    for i, ln in enumerate(lines):
        if ln.startswith('<path d="M') and 'marker-end' in ln:
            pts = arrow_points(ln)
            ends = []
            for p in (pts[0], pts[-1]):
                ends.append(next(((n, _side(p, r)) for n, r in sc.boxes.items() if _side(p, r)), (None, None)))
            arrows.append((i, pts, ends[0], ends[1]))

    def bad(pts, a, b):
        if a[0] is None or b[0] is None:
            return True
        for n, (x, y, w, h) in sc.boxes.items():
            for o, c, lo, hi in route.segments(pts):
                if (o == 'h' and y + 1 < c < y + h - 1 and lo < x + w - 1 and hi > x + 1) or (o == 'v' and x + 1 < c < x + w - 1 and lo < y + h - 1 and hi > y + 1):
                    return True
        return False

    segs = [(k, route.segments(p)) for k, (i, p, a, b) in enumerate(arrows)]

    def close(k):
        for o, c, lo, hi in segs[k][1]:
            for k2, s2 in segs:
                if k2 >= k:
                    continue
                for o2, c2, lo2, hi2 in s2:
                    if o == o2 and 0.5 < abs(c - c2) < 13.5 and min(hi, hi2) - max(lo, lo2) > 20:
                        return True
        return False

    invalid = [k for k, (i, p, a, b) in enumerate(arrows) if bad(p, a, b) or close(k)]
    if count_only:
        return text, len(invalid), []
    if not invalid:
        return text, 0, []
    labels = {}                                           # arrow k -> line index of its label rect
    for i, ln in enumerate(lines):
        lab = route.draw.label_at(lines, i)
        if lab:
            cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
            for k, (ai, p, a, b) in enumerate(arrows):
                if any((o == 'h' and abs(c - cy) < 1 and lo <= cx <= hi) or (o == 'v' and abs(c - cx) < 1 and lo <= cy <= hi) for o, c, lo, hi in route.segments(p)):
                    labels[k] = i
    keep = [k for k in range(len(arrows)) if k not in invalid]
    gone = {labels[k] for k in invalid if k in labels}
    sc.arrows = [arrows[k][1] for k in keep]
    gone_at = [route.draw.label_at(lines, i)[:2] for i in gone]
    sc.labels = [l for l in sc.labels if not any(abs(l[0] - gx) < .5 and abs(l[1] - gy) < .5 for gx, gy in gone_at)]
    problems, done = [], 0
    for k in sorted(invalid, key=lambda k: -sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(arrows[k][1], arrows[k][1][1:]))):
        i, pts, a, b = arrows[k]
        ln = lines[i]
        mk = re.search(r'marker-end="url\(#([\w-]+)\)"', ln)
        word = route.draw.label_at(lines, labels[k])[5] if k in labels else MARKER_KIND.get(mk.group(1) if mk else '', 'related')
        if a[0] is None or b[0] is None:
            problems.append('an arrow near (%d,%d) ends on no box: draw it again with add_nodes.py' % pts[0])
            sc.arrows.append(pts)
            continue
        tries = [(a[1], b[1])] + [s for s in route.sides_for(sc.boxes[a[0]], sc.boxes[b[0]]) if s != (a[1], b[1])]
        new = None
        for sa, sb in tries:
            new = route.route(sc, a[0], b[0], sa, sb)
            if new:
                break
        if not new:
            problems.append('NO PATH for the arrow #%s -> #%s near (%d,%d): it stays as it was; move a box or leave it out' % (a[0], b[0], pts[0][0], pts[0][1]))
            sc.arrows.append(pts)
            continue
        lines[i] = re.sub(r'd="[^"]*"', 'd="M' + ' L'.join('%s,%s' % (route.draw.fmt(x), route.draw.fmt(y)) for x, y in new) + '"', ln, count=1)
        sc.arrows.append(new)
        done += 1
        if k in labels and word in route.draw.EDGE:
            li = labels[k]
            _, _, w, h, _, _ = route.draw.label_at(lines, li)       # the label keeps its own size (a two-line one is 30px tall)
            lab = route.place_label(sc, new, word, w, h)
            if lab:
                route.draw.move_label(lines, li, lab[0], lab[1])    # the rectangle and its text lines move together
                sc.labels.append((lab[0] - w / 2, lab[1] - h / 2, w, h))
            else:
                problems.append('no straight stretch for the label of the arrow #%s -> #%s' % (a[0], b[0]))
    return '\n'.join(lines), done, problems


def replace_labels(old, new, idxs):
    """After arrows changed shape (same line indexes in `old` and `new`), take the label of each arrow in `idxs` off (found on its OLD
    path: a label of its word centred on one of its stretches) and place it again on its NEW path with route.place_label (20px of shaft;
    else the best place with less, reported). Returns (text, problems)."""
    import svgmeta
    lo_, ln_ = old.split('\n'), new.split('\n')
    found = {}                                             # arrow line -> (label line, number of lines)
    for i in idxs:
        at = svgmeta.arrow_of(lo_[i])
        if not at:
            continue
        segs = route.segments(arrow_points(lo_[i]))
        for j in range(len(lo_)):
            lab = route.draw.label_at(lo_, j)
            if lab and lab[5] == at[2] and j not in [v[0] for v in found.values()]:
                cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
                if any((o == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1) for o, c, lo, hi in segs):
                    found[i] = (j, 1 + lab[4])
                    break
    drop = {k for j, m in found.values() for k in range(j, j + m)}
    keep = [l if k not in drop else None for k, l in enumerate(ln_)]
    sc, _ = read('\n'.join(l for l in keep if l is not None))
    problems = []
    for i in idxs:
        at = svgmeta.arrow_of(ln_[i])
        if i not in found or not at:
            continue
        pts = arrow_points(ln_[i])
        lab = route.place_label(sc, pts, at[2])
        if not lab:
            lab = route.place_label(sc, pts, at[2], strict=False)
            problems.append('label of #%d %s #%d: %s' % (at[0], at[2], at[1], 'less than 20px of shaft, check it by eye' if lab else 'no straight stretch: it is left off'))
        if lab:
            w = route.draw.label_width(at[2])
            sc.labels.append((lab[0] - w / 2, lab[1] - 9, w, 18))
            keep[found[i][0]] = '\n'.join(route.draw.label(at[2], *lab))
    return '\n'.join(l for l in keep if l is not None), problems


def off_middle(pts, cx, cy, tol=6):
    """Is the label at (cx, cy) more than tol px from the middle of a straight arrow's shaft (tail to the base of the head)? check_diag.py
    fails 12.5px. An arrow with a bend is never off its middle here."""
    p = route.straight([tuple(x) for x in pts])
    if len(p) != 2:
        return False
    (x0, y0), (x1, y1) = p
    if abs(y0 - y1) < .01:
        return abs(cx - (x0 + x1 - 11 * (1 if x1 > x0 else -1)) / 2) > tol
    return abs(cy - (y0 + y1 - 11 * (1 if y1 > y0 else -1)) / 2) > tol


def relabel(text, hop_pad=0, redo=()):
    """Put every label that does not sit well on its arrow (it covers another arrow, a box or a label, or is off its arrow) on a better
    straight stretch. Returns (text, fixed, failed): the number of labels moved, and (x, y, reason) for each label that found no good place.
    A label with no arrow under it goes back to the nearest arrow of its word that has no label. hop_pad: a label nearer than this to a
    jump arc counts as badly placed (0: only one that covers an arc; build.py passes 20, the shaft the checker asks for). redo: line
    indexes of arrows whose labels are placed again even when they sit well (fit_heights.py passes the arrows it changed). An arrow's
    word is its data-kind (svgmeta.py), else the word of its arrowhead."""
    import svgmeta
    sc, info = read(text)
    lines = info['lines']
    fixed, failed = 0, []
    kinds, redo_k = [], set()                               # the word of each arrow (same order as sc.arrows); the arrows to redo
    for i, ln in enumerate(lines):
        if ln.startswith('<path d="M') and 'marker-end' in ln:
            at = svgmeta.arrow_of(ln)
            mk = re.search(r'marker-end="url\(#([\w-]+)\)"', ln)
            if i in redo:
                redo_k.add(len(kinds))
            kinds.append(at[2] if at else (MARKER_KIND.get(mk.group(1)) if mk else None))

    def on_arrow(k, cx, cy):
        return any((o == 'h' and abs(c - cy) < 1 and lo <= cx <= hi) or (o == 'v' and abs(c - cx) < 1 and lo <= cy <= hi) for o, c, lo, hi in route.segments(sc.arrows[k]))

    def distance(k, cx, cy):
        if not route.segments(sc.arrows[k]):              # an arrow of no length has no stretch to carry a label
            return 1e18
        return min((abs(c - cy) + max(0, lo - cx, cx - hi)) if o == 'h' else (abs(c - cx) + max(0, lo - cy, cy - hi)) for o, c, lo, hi in route.segments(sc.arrows[k]))

    labelled = set()                                        # arrows that carry a label now
    for i in range(len(lines)):
        lab = route.draw.label_at(lines, i)
        if lab:
            labelled |= {k for k in range(len(sc.arrows)) if on_arrow(k, lab[0] + lab[2] / 2, lab[1] + lab[3] / 2)}
    for i, ln in enumerate(lines):
        lab = route.draw.label_at(lines, i)
        if not lab:
            continue
        x, y, w, h, _, word = lab
        rect = route.draw.label_box(lines, i)                  # as drawn: a label beside its shaft is shifted
        shift = route.draw.label_shift(ln)
        cx, cy = x + w / 2, y + h / 2                          # on the shaft, for every label
        own, orphan, own_k = None, False, None
        for k in range(len(sc.arrows)):
            if on_arrow(k, cx, cy) and (kinds[k] == word or own is None):
                own, own_k = sc.arrows[k], k
        if own is None:                                    # a label with no arrow under it (an arrow moved and left it behind):
            free = [k for k in range(len(sc.arrows)) if kinds[k] == word and k not in labelled]   # give it back to the nearest arrow of its word that has no label
            if free:
                k = min(free, key=lambda k: distance(k, cx, cy))
                own, orphan = sc.arrows[k], True
                labelled.add(k)
        others = route.Scene(sc.boxes, sc.frames, [l for l in sc.labels if tuple(l) != rect], sc.pills, sc.arrows, sc.bounds)
        others.hops = sc.hops
        if own is not None and not orphan and own_k not in redo_k and not route._hit(rect, others, own=own, hop_pad=hop_pad) \
                and (not off_middle(own, cx, cy) if not shift else route.place_label(others, own, word, w, h, strict=False) is None):
            continue                                        # sits well (a label beside its shaft: while the shaft is still too short)
        if own is None or word not in route.draw.EDGE:
            failed.append((round(cx), round(cy), 'no arrow of this word to attach the label to'))
            continue
        new, nshift = route.place_label(others, own, word, w, h), None
        if not new:                                         # no place with the full 20px of shaft: take the best place with 8px and say so
            new = route.place_label(others, own, word, w, h, strict=False)
            if new:
                failed.append((round(new[0]), round(new[1]), 'the label fits only with less than 20px of shaft (a short arrow): check it by eye'))
            else:                                           # a shaft too short for any label: beside it
                bs = route.place_label_beside(others, own, word, w, h)
                if not bs:
                    failed.append((round(cx), round(cy), 'no straight stretch long enough: move a box or route that arrow again'))
                    continue
                new, nshift = bs[:2], bs[2:]
        route.draw.move_label(lines, i, new[0], new[1], nshift)
        dx, dy = nshift or (0, 0)
        sc.labels = [l for l in sc.labels if tuple(l) != rect] + [(new[0] + dx - w / 2, new[1] + dy - h / 2, w, h)]
        fixed += 1
    return '\n'.join(lines), fixed, failed


def read(text, bounds=None):
    lines, box, pop, frame = collapse.parse(text)
    boxes = {n: (b['x'], b['y'], b['w'], b['h']) for n, b in box.items()}
    frames = [(f['x'], f['y'], f['w'], f['h']) for f in frame]
    labels = []
    for i, ln in enumerate(lines):
        lab = route.draw.label_box(lines, i)
        if lab:
            labels.append(lab)                                      # as drawn (beside its shaft too); the real height: a two-line label is 30px
        m = re.match(r'<text class="ftl" x="([\d.-]+)" y="([\d.-]+)">([^<]*)', ln)
        if m:
            labels.append((float(m.group(1)) - 4, float(m.group(2)) - 20, 8.5 * len(m.group(3)) + 40, 30.0))
    pills = [(float(m.group(1)) - 26, float(m.group(2)) - 26, 52.0, 52.0) for m in re.finditer(r'<g transform="rotate\(-45 ([\d.]+) ([\d.]+)\)">', text)]
    arrows = [arrow_points(ln) for ln in lines if ln.startswith('<path d="M') and 'marker-end' in ln]
    titles = {}
    for n, b in box.items():
        grp = '\n'.join(lines[b['a']:b['b'] + 1])
        t = re.sub(r'<[^>]+>', '', ' '.join(re.findall(r'class="ttl"[^>]*>(.*?)</text>', grp)))
        titles[n] = t
    prs = {int(m.group(1)) for m in re.finditer(r'href="https://github.com/[^"/]+/[^"/]+/pull/(\d+)"', text)}
    legend = None
    m = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="14" fill="#fbfaf6"', text)
    if m:
        legend = tuple(float(v) for v in m.groups())
    right = max([b[0] + b[2] for b in boxes.values()] + [f[0] + f[2] for f in frames] + [0])
    bottom = max([b[1] + b[3] for b in boxes.values()] + [f[1] + f[3] for f in frames] + [0])
    if bounds is None:
        bounds = (30, 165, (legend[0] - 25) if legend and legend[0] > right else right + 400, bottom + 400)
    sc = route.Scene(boxes, frames, labels, pills, arrows, bounds)
    for ln in lines:                                        # jump arcs: "L x,y A r r 0 0 1 x2,y2" (the arc spans x..x2 on one run)
        if ln.startswith('<path d="M') and ' A' in ln:
            for m in re.finditer(r'L(-?[\d.]+),(-?[\d.]+) A[\d. ]+? (-?[\d.]+),(-?[\d.]+)(?= L| ")', ln.split('"')[1]):
                sc.hops.append(tuple(float(v) for v in m.groups()))
    return sc, dict(lines=lines, titles=titles, prs=prs, right=right, bottom=bottom, legend=legend)


USAGE = """usage: model.py relabel IN.svg OUT.svg     put every badly placed label back on a good straight stretch of its own arrow
                                         (a label left behind by an old move goes back to the nearest unlabelled arrow of its word)
       model.py repair IN.svg OUT.svg      route again every arrow that is invalid (an end on no box, a run through a box)
Run check_diag.py afterwards."""

if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] not in ('relabel', 'repair'):
        sys.exit(USAGE)
    src = open(sys.argv[2], encoding='utf-8').read()
    if sys.argv[1] == 'relabel':
        out, n, notes = relabel(src)
        print('%d labels moved' % n)
    else:
        out, n, notes = repair(src)
        print('%d arrows routed again' % n)
    for p in notes:
        print('PROBLEM', '%s near (%d,%d)' % (p[2], p[0], p[1]) if isinstance(p, tuple) else p)
    open(sys.argv[3], 'w', encoding='utf-8').write(out)
