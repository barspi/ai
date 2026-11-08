#!/usr/bin/env python3
"""Shrink every collapsed box to the height its drawn arrows need, keeping its top edge where it is. Nothing else moves.

usage: fit_heights.py IN.svg OUT.svg [--force]

Why: layout.py sizes a box before any arrow is routed, so it reserves room on the sides of a collapsed box for the arrows the router
will add (36px each, see layout.plan). That is an estimate; once the arrows are drawn, the room that was not used is given back here.

For each collapsed box: the new height is the largest of its least collapsed height (collapse.HC, or collapse.HC_TWO when the first line
needed a second line), what each side needs for the arrows that end on it (24px plus 20px per arrow after the first, the rule of
layout.min_height for a collapsed box), and what holds the ends of its straight arrows, which do not move (the layout made them
straight). The end of a bent arrow that falls outside the shorter side moves to the nearest free place on it, and the straight stretch
into it moves with it; an end on the bottom moves up with the bottom edge (its vertical stretch gets longer); an end on the top does
not move. Then, as compact.py does: model.repair() routes again only the arrows
the change left invalid (an end on no box, a run through a box, a run closer than 14px to another arrow), hops.py redoes the jump arcs,
and model.relabel() puts each label back on a good stretch of its own arrow. When the result has more invalid arrows than the input,
nothing is written (exit 1), unless --force. The pop-ups do not change: they are full copies drawn over the picture.

build.py runs fit() after routing, so a new diagram never keeps the reserved room.
"""
import collections, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, draw, hops, model, svgmeta


def side_need(k):
    """Least collapsed-box height for k arrow ends on one side (layout.min_height for a collapsed box)."""
    return 24 + 20 * max(k - 1, 0)


def straight(pts):
    """The corner points of an orthogonal path: points on a straight run (left by jump arcs) are dropped."""
    out = []
    for p in pts:
        if len(out) >= 2 and (out[-2][0] == out[-1][0] == p[0] or out[-2][1] == out[-1][1] == p[1]):
            out[-1] = p
        elif not out or p != out[-1]:
            out.append(p)
    return out


MARGIN = 12.0       # an arrow end keeps this far from the top and bottom corners of a side
GAP = 20.0          # and this far from the next end on the same side (layout.attach for a collapsed box)


def shrink(text, keep=()):
    """Move the arrow ends and shorten the boxes. Returns (text, [(box, old height, new height)]). No repair here.
    A straight arrow (two points) keeps both ends where they are, so it stays straight: the box keeps the height that holds them.
    The end of a bent arrow moves only when it falls outside the shorter side, to the nearest free place (GAP from the other ends),
    and the straight stretch that comes into it moves with it. Boxes in `keep` keep their height."""
    lines, box, _, _ = collapse.parse(text)
    sc, _ = model.read(text)
    ends = collections.defaultdict(list)                    # box -> [(line index, 0 or -1, side)]
    for i, ln in enumerate(lines):
        if ln.startswith('<path d="M') and 'marker-end' in ln:
            pts = model.arrow_points(ln)
            for k in (0, -1):
                for n, r in sc.boxes.items():
                    s = model._side(pts[k], r)
                    if s:
                        ends[n].append((i, k, s))
                        break
    paths = {}                                              # line index -> corner points, as changed so far
    get = lambda i: paths.setdefault(i, straight(model.arrow_points(lines[i])))
    changed = []
    for n in sorted(box):
        b = box[n]
        if not b['coll'] or n in keep:
            continue
        x, y = b['x'], b['y']
        base = collapse.HC_TWO if collapse.two_lines(lines[b['a']:b['b'] + 1]) else collapse.HC
        count = collections.Counter(s for _, _, s in ends[n])
        side = {'L': [], 'R': []}                            # (y of the end, line, end, fixed)
        for i, k, s in ends[n]:
            if s in side:
                pts = get(i)
                side[s].append((pts[0 if k == 0 else -1][1], i, k, len(pts) == 2))
        fixed_low = max([ey - y + MARGIN for es in side.values() for ey, _, _, f in es if f] + [0])
        new_h = float(round(max(base, side_need(count['L']), side_need(count['R']), fixed_low)))
        if new_h >= b['h'] - 0.5:
            continue
        lo, hi = y + MARGIN, y + new_h - MARGIN
        for s, es in side.items():
            taken = [ey for ey, _, _, f in es if f or lo <= ey <= hi]
            for ey, i, k, f in sorted(es, key=lambda e: abs(e[0] - (lo + hi) / 2)):
                if f or lo <= ey <= hi:
                    continue
                slots = [lo + 2 * q for q in range(int((hi - lo) / 2) + 1)]
                free = [v for v in slots if all(abs(v - t) >= GAP for t in taken)]
                if not free:
                    new_h += GAP                            # no room left on this side: keep one more slot
                    hi += GAP
                    free = [hi]
                ny = min(free, key=lambda v: abs(v - ey))
                taken.append(ny)
                pts = get(i)
                kk = 0 if k == 0 else len(pts) - 1
                nb = 1 if kk == 0 else len(pts) - 2
                if abs(pts[nb][1] - pts[kk][1]) < 0.5:     # the horizontal stretch into the end moves with it
                    pts[nb] = (pts[nb][0], ny)
                pts[kk] = (pts[kk][0], ny)
        if new_h >= b['h'] - 0.5:
            continue
        for i, k, s in ends[n]:
            if s == 'B':
                pts = get(i)
                kk = 0 if k == 0 else len(pts) - 1
                pts[kk] = (pts[kk][0], y + new_h)
        changed.append((n, b['h'], new_h))
    for i, pts in paths.items():
        d = 'M' + ' L'.join('%s,%s' % (draw.fmt(px), draw.fmt(py)) for px, py in straight(pts))
        lines[i] = re.sub(r'd="[^"]*"', 'd="%s"' % d, lines[i], count=1)
    for n, _, h in changed:
        collapse.set_height(lines, n, h)
    return '\n'.join(lines), changed, sorted(paths)


def fit(text, tries=4):
    """shrink(), then repair, jump arcs and labels. When a moved arrow is left with no stretch for its label (20px of shaft each side),
    the boxes at its two ends keep their height and the whole step runs again from the input, at most `tries` times.
    Returns (text, changed, rerouted, problems, invalid before, invalid after, kept)."""
    import route
    before = model.repair(text, count_only=True)[1]
    keep = set()
    for _ in range(tries):
        res, changed, moved = shrink(text, keep)
        if not changed:
            return text, [], 0, [], before, before, keep
        res, _, _ = hops.add_hops(res)
        res, rerouted, bad = model.repair(res)
        res, _, _ = hops.add_hops(res)
        res, _, failed = model.relabel(res, hop_pad=20, redo=set(moved))     # the labels of the arrows that moved, placed again
        short = [(x, y) for x, y, why in failed if 'shaft' in why or 'straight stretch' in why]
        if not short:
            break
        lines = res.split('\n')
        sc, _ = model.read(res)
        shortened = {c[0] for c in changed}
        words = {}                                          # label centre -> its word
        for j in range(len(lines)):
            lab = draw.label_at(lines, j)
            if lab:
                words[(round(lab[0] + lab[2] / 2), round(lab[1] + lab[3] / 2))] = lab[5]
        grown = set()
        for x, y in short:                                  # the moved arrow of that label's word nearest to it; the shortened box at its ends
            word = min(words.items(), key=lambda kv: abs(kv[0][0] - x) + abs(kv[0][1] - y))[1] if words else None
            mine = [i for i in moved if (svgmeta.arrow_of(lines[i]) or (0, 0, word))[2] == word] or list(moved)
            dist = lambda i: min([abs(c - (y if o == 'h' else x)) + max(0, lo - (x if o == 'h' else y), (x if o == 'h' else y) - hi)
                                  for o, c, lo, hi in route.segments(model.arrow_points(lines[i]))] or [1e18])
            pts = model.arrow_points(lines[min(mine, key=dist)])
            grown |= {n for p in (pts[0], pts[-1]) for n, r in sc.boxes.items() if model._side(p, r)} & shortened
        if not grown - keep:
            break
        keep |= grown
    after = model.repair(res, count_only=True)[1]
    return res, changed, rerouted, bad + ['label near (%d,%d): %s' % f for f in failed], before, after, keep


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        sys.exit(__doc__)
    text = open(args[0], encoding='utf-8').read()
    res, changed, rerouted, problems, before, after, kept = fit(text)
    if after > before and '--force' not in sys.argv:
        print('REFUSED: fitting would leave %d arrows invalid (%d before). Nothing written.' % (after, before))
        for p in problems:
            print('PROBLEM', p)
        sys.exit(1)
    open(args[1], 'w', encoding='utf-8').write(res)
    print('%d collapsed boxes shortened by %.0fpx in all; %d arrows routed again%s' % (len(changed), sum(o - h for _, o, h in changed), rerouted,
          '; kept their height for a label: %s' % ' '.join('#%d' % n for n in sorted(kept)) if kept else ''))
    for n, o, h in changed:
        print('  #%d: %.0f -> %.0f' % (n, o, h))
    for p in problems:
        print('PROBLEM', p)
    print('next: check_diag.py %s' % args[1])


if __name__ == '__main__':
    main()
