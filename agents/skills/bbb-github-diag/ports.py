#!/usr/bin/env python3
"""Port ordering: the arrows on one side of a box, going out and coming in, take their slots on that side in the order of the boxes
at their other ends, so that they do not cross each other beside the box.

usage: ports.py IN.svg OUT.svg            B, then A; write OUT (IN may be OUT)
       ports.py IN.svg --check            list the pairs of arrows of one side that cross each other

B, plan (cheap: a sort per side, before any path is searched). Every arrow takes its natural pair of sides (route.sides_for). At each
   end, the box at the other end gives a target point: the middle of that box's two sides that face this one (the side the arrow
   uses there, and the facing side on the other axis). The ends on one side, out and in together, are sorted by their target points
   along the side (y on a left or right side, x on a top or bottom one), and the side is cut into as many equal spans, one per end,
   in that order. Every arrow is then routed again inside its two spans (route.route span_a, span_b): the router picks the slot in
   the span, so its rules (route.HARD_H apart, a straight entry) still hold while the order is the planned one. An arrow with no
   path inside its spans is routed freely; one with no path at all keeps the path it had.
A, repair (only where B left a crossing: crossing_pairs). The arrows of that side are routed again in the order of their far boxes,
   each confined to the part of the side past the slot of the arrow before it and short of the room the arrows after it need, the
   router free to pick the far side. Kept when it scores better: fewer labels without a place (label_fails), then a lower path cost
   of the side's arrows (route.path_cost). check_diag.py warns about each crossing that stays.
Then straighten.straighten (vertical alignment, Brandes and Koepf): a Z arrow whose jog is the 5px grid step or the 20px corner margin
becomes straight when one of its boxes moves up or down by the jog.
A pinned arrow (a route the user chose: svgmeta.is_pinned) keeps its path, and A leaves its side alone. Nothing is written when an
arrow disappeared or more arrows became invalid (exit 1).
"""
import math, os, re, sys, tempfile
from typing import NamedTuple
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draw, hops, model, move, route, straighten, svgmeta

SLOT_GAP = 25       # two slots of one side at least this far apart: route.HARD_H (22) on the 5px grid


class Drawn(NamedTuple):
    """A drawn arrow between two drawn boxes."""
    a: int
    b: int
    kind: str
    line: int         # its line in the text
    pinned: bool


class End(NamedTuple):
    """One end of a drawn arrow, on one side of its box."""
    arrow: Drawn
    box: int          # the box this end touches
    side: str         # R, L, T or B
    end: str          # 'tail' or 'tip'
    far: tuple        # the target point of the box at the other end (facing_point)

    @property
    def other(self):
        return self.arrow.b if self.end == 'tail' else self.arrow.a


def along(p, side):
    """A point's place along a side: its y on a left or right side, its x on a top or bottom one."""
    return p[1] if side in 'RL' else p[0]


def centre(r):
    x, y, w, h = r
    return x + w / 2, y + h / 2


def middle(r, side):
    """The midpoint of one side of box r."""
    x, y, w, h = r
    return {'R': (x + w, y + h / 2), 'L': (x, y + h / 2), 'T': (x + w / 2, y), 'B': (x + w / 2, y + h)}[side]


def facing_point(r, toward, side):
    """The target point of box r for an arrow from (or to) box `toward` that uses `side` of r: the middle of the midpoints of that
    side and of r's side on the other axis that faces `toward`."""
    (cx, cy), (tx, ty) = centre(r), centre(toward)
    cross = ('T' if ty < cy else 'B') if side in 'RL' else ('L' if tx < cx else 'R')
    (x1, y1), (x2, y2) = middle(r, side), middle(r, cross)
    return (x1 + x2) / 2, (y1 + y2) / 2


def drawn(text):
    """Every drawn arrow whose two boxes are drawn."""
    sc, info = model.read(text)
    return [Drawn(at[0], at[1], at[2], i, svgmeta.is_pinned(ln)) for i, ln in enumerate(info['lines'])
            for at in [svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)] if at and at[0] in sc.boxes and at[1] in sc.boxes]


def plan(sc, arrows):
    """B: {line: (side at a, span at a, side at b, span at b)} for each arrow; see the module text."""
    sides, on = {}, {}
    for d in arrows:
        ra, rb = sc.boxes[d.a], sc.boxes[d.b]
        sa, sb = sides[d.line] = route.sides_for(ra, rb)[0]
        on.setdefault((d.a, sa), []).append((along(facing_point(rb, ra, sb), sa), d.line, 0))
        on.setdefault((d.b, sb), []).append((along(facing_point(ra, rb, sa), sb), d.line, 1))
    span = {}
    for (n, s), ends in on.items():
        lo, hi = route._side_cells(sc.boxes[n], s, 20)
        step = (hi - lo) / len(ends)
        for k, (_, line, which) in enumerate(sorted(ends)):
            span[line, which] = (lo + k * step, lo + (k + 1) * step)
    return {line: (sa, span[line, 0], sb, span[line, 1]) for line, (sa, sb) in sides.items()}


def route_all(text, arrows):
    """B applied: every arrow of `arrows` routed again inside its planned spans, the most important and the shortest first (as
    move.py). Returns (text, {'planned': n, 'free': n, 'kept': n})."""
    lines = text.split('\n')
    taken = {d.line: move.take_out(lines, d.line) for d in arrows}
    sc, _ = model.read('\n'.join(l for k, l in enumerate(lines) if not any(k in t for t in taken.values())))
    spans = plan(sc, arrows)
    reach = lambda d: sum(abs(p - q) for p, q in zip(centre(sc.boxes[d.a]), centre(sc.boxes[d.b])))
    order = sorted(arrows, key=lambda d: (-draw.IMPORTANCE.get(d.kind, 2), reach(d)))
    paths, count = {}, {'planned': 0, 'free': 0, 'kept': 0}
    for d in order:
        sa, span_a, sb, span_b = spans[d.line]
        pts = route.route(sc, d.a, d.b, sa, sb, span_a=span_a, span_b=span_b)
        how = 'planned'
        if not pts:
            pts, how = route.route(sc, d.a, d.b, '*', '*'), 'free'
        if not pts:
            pts, how = model.arrow_points(lines[d.line]), 'kept'
        count[how] += 1
        sc.arrows.append(list(pts))
        paths[d.line] = pts
    return _write(lines, arrows, taken, paths, sc), count


def ends(text):
    """Both ends of every drawn arrow whose ends touch a side of their boxes."""
    sc, info = model.read(text)
    out = []
    for d in drawn(text):
        pts = model.arrow_points(info['lines'][d.line])
        tail, tip = model._side(pts[0], sc.boxes[d.a]), model._side(pts[-1], sc.boxes[d.b])
        if tail and tip:
            ra, rb = sc.boxes[d.a], sc.boxes[d.b]
            out += [End(d, d.a, tail, 'tail', facing_point(rb, ra, tip)), End(d, d.b, tip, 'tip', facing_point(ra, rb, tail))]
    return out


def groups(text):
    """{(box, side): [End, ...]} of every side that two or more arrows use, going out or coming in."""
    out = {}
    for e in ends(text):
        out.setdefault((e.box, e.side), []).append(e)
    return {k: g for k, g in out.items() if len(g) > 1}


def far_key(e):
    """The place an end should take along its side: its far box's target point on the side's axis, then on the other axis."""
    return (along(e.far, e.side), along(e.far, 'T' if e.side in 'RL' else 'R'))


def crossing_pairs(text):
    """[(End, End)]: two arrows of one side whose paths cross each other."""
    lines = text.split('\n')
    segs = lambda e: route.segments(route.straight([tuple(p) for p in model.arrow_points(lines[e.arrow.line])]))
    return [(e, f) for g in groups(text).values() for k, e in enumerate(g) for f in g[k + 1:]
            if e.arrow != f.arrow and route._crossings(segs(e), segs(f))]


def label_fails(text):
    """Labels with no good place once the jump arcs are drawn (hops.py, then model.relabel with the checker's 20px of shaft)."""
    return len(model.relabel(hops.add_hops(text)[0], hop_pad=20)[2])


def score(text, group):
    """What a drawing of one side is judged by, smaller is better: (labels with no place, path cost of the side's arrows)."""
    sc, info = model.read(text)
    pairs = {(e.arrow.a, e.arrow.b) for e in group}
    cost = sum(route.path_cost(sc, model.arrow_points(ln), *at[:2]) for ln in info['lines']
               for at in [svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)] if at and at[:2] in pairs)
    return label_fails(text), cost


def reorder(text, group, key=far_key):
    """A: the text with the arrows of one side routed again in `key` order, each confined to the part of the side past the slot of
    the arrow before it and short of the room the arrows after it need, and their labels placed again; None when one of them finds
    no path."""
    lines = text.split('\n')
    taken = {e.arrow.line: move.take_out(lines, e.arrow.line) for e in group}
    sc, _ = model.read('\n'.join(l for k, l in enumerate(lines) if not any(k in t for t in taken.values())))
    end = route._side_cells(sc.boxes[group[0].box], group[0].side, 20)[1]   # the last slot of the side (route.side_set)
    paths, after = {}, -math.inf
    for k, e in enumerate(sorted(group, key=key)):
        span = (after + SLOT_GAP, end - (len(group) - 1 - k) * SLOT_GAP)
        a, b = e.arrow.a, e.arrow.b
        if e.end == 'tail':
            pts = route.route(sc, a, b, e.side, '*', span_a=span)
        else:
            pts = route.route(sc, a, b, '*', e.side, span_b=span)
        if not pts:
            return None
        sc.arrows.append(list(pts))
        paths[e.arrow.line], after = pts, along(pts[0] if e.end == 'tail' else pts[-1], e.side)
    return _write(lines, [e.arrow for e in group], taken, paths, sc)


def _write(lines, arrows, taken, paths, sc):
    """The lines with each arrow's path replaced and its label placed again, where its old label was (before the legend when it had
    none)."""
    label = {}
    for d in arrows:
        lab = route.place_label_any(sc, paths[d.line], d.kind)
        if lab:
            w, (dx, dy) = draw.label_width(d.kind), lab[2] or (0, 0)
            sc.labels.append((lab[0] + dx - w / 2, lab[1] + dy - 9, w, 18))
            label[d.line] = draw.label(d.kind, lab[0], lab[1], lab[2])
    at = {t[1]: i for i, t in taken.items() if len(t) > 1}               # first line of an old label -> its arrow's line
    gone = {k for t in taken.values() for k in t}
    homeless = [l for i, t in taken.items() if len(t) == 1 for l in label.get(i, [])]
    out = []
    for k, l in enumerate(lines):
        if k in paths:
            out.append(re.sub(r'd="[^"]*"', 'd="M%s"' % ' L'.join('%s,%s' % (draw.fmt(x), draw.fmt(y)) for x, y in paths[k]), l, count=1))
        elif k in gone:
            out += label.get(at.get(k), [])
        else:
            if l == '<!--legend-->':
                out, homeless = out + homeless, []
            out.append(l)
    return '\n'.join(out[:-2] + homeless + out[-2:])


def untangle(text):
    """A on every side where two arrows cross, kept when it scores better. Returns (text, [one line per side changed])."""
    done = []
    for key in sorted({(e.box, e.side) for e, _ in crossing_pairs(text)}):
        group = groups(text).get(key)                                     # read again: line numbers move after each change
        if not group or any(e.arrow.pinned for e in group):
            continue
        new = reorder(text, group)
        if new and model.count_arrows(new) == model.count_arrows(text) and score(new, group) < score(text, group):
            before, after = score(text, group)[1], score(new, group)[1]
            text = new
            done.append('#%d %s side: order %s (cost %.0f -> %.0f)' % (key + (', '.join(
                '#%d' % e.other for e in sorted(group, key=far_key)), before, after)))
    return text, done


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    check = '--check' in sys.argv
    if len(args) != (1 if check else 2):
        sys.exit(__doc__)
    text = open(args[0], encoding='utf-8').read()
    if check:
        for e, f in crossing_pairs(text):
            print('#%d -> #%d and #%d -> #%d: both on the %s side of #%d, and they cross'
                  % (e.arrow.a, e.arrow.b, f.arrow.a, f.arrow.b, e.side, e.box))
        return
    arrows = [d for d in drawn(text) if not d.pinned]
    res, count = route_all(text, arrows)
    print('B: %(planned)d arrows routed in their planned spans, %(free)d routed freely, %(kept)d kept their path' % count)
    print('B left %d pairs of arrows of one side crossing' % len(crossing_pairs(res)))
    res, done = untangle(res)
    print('\n'.join('A: ' + d for d in done) or 'A: no side changed')
    res, aligned = straighten.straighten(res)[:2]
    print('straighten: %d Z arrows made straight by moving a box' % len(aligned))
    res = hops.add_hops(res)[0]
    res, _, bad = model.relabel(res, hop_pad=20)
    res, _, nolab = model.label_missing(res, [(d.a, d.b) for d in arrows])
    if model.repair(res, count_only=True)[1] > model.repair(text, count_only=True)[1] or model.count_arrows(res) != model.count_arrows(text):
        print('REFUSED: an arrow disappeared or became invalid. Nothing written.')
        sys.exit(1)
    open(args[1], 'w', encoding='utf-8').write(res)
    for x, y, why in bad:
        print('PROBLEM label near (%d,%d): %s' % (x, y, why))
    for x in nolab:
        print('PROBLEM', model.no_label(x))
    print('%d pairs of arrows of one side still cross (check_diag.py lists them)' % len(crossing_pairs(res)))


if __name__ == '__main__':
    main()
