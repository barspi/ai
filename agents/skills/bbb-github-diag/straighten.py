#!/usr/bin/env python3
"""Make Z-shaped arrows straight by moving one of their boxes up or down, when there is free room. Columns and frames do not change.

usage: straighten.py IN.svg OUT.svg [--force]

An arrow with exactly two bends that leaves one box by its right side and enters the other by its left side (or the reverse) is a
horizontal line with a vertical jog in the middle. It becomes straight when one of its two boxes moves vertically by the height of the
jog. This is the vertical alignment step of Brandes and Koepf (2001), done greedily on the picture as it is:
- candidates are taken shortest jog first; the box that moves is the one with fewer other arrows (ties: the arrow's tip), so a hub stays;
- a move is taken only when the straight line will carry its label (a free stretch between the jump arcs where other arrows cross it);
- a box with an arrow that is already straight never moves (the move would bend it);
- a box moves only when its new place keeps GAP (28px) from every other box, stays inside its frame (40px below the top for the title,
  20px above the bottom), and the box has not moved already;
- move_boxes() shifts the box and its pop-up and moves the ends of its arrows (and the stretch into a side end); then model.repair() routes
  again only the arrows the move left invalid, hops.py redoes the jump arcs, and model.relabel() puts the labels back on good stretches.
Nothing is written when the result has more invalid arrows than the input (exit 1), unless --force.
"""
import collections, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, draw, fit_heights, hops, model, route, svgmeta

GAP = 28.0


def plan(text, hold=()):
    """{box: new top y} and the arrows each move makes straight."""
    lines, box, _, frames = collapse.parse(text)
    sc, _ = model.read(text)
    rect = {n: list(r) for n, r in sc.boxes.items()}
    degree = collections.Counter()
    has_straight = set()                                  # boxes with a straight (two-point) arrow: moving one would bend it
    zs = []
    for i, ln in enumerate(lines):
        if not (ln.startswith('<path d="M') and 'marker-end' in ln):
            continue
        pts = fit_heights.straight(model.arrow_points(ln))
        ends = [next((n for n, r in sc.boxes.items() if model._side(p, r)), None) for p in (pts[0], pts[-1])]
        for n in ends:
            if n is not None:
                degree[n] += 1
                if len(pts) == 2:
                    has_straight.add(n)
        if len(pts) == 4 and None not in ends and ends[0] != ends[1] and abs(pts[0][1] - pts[1][1]) < .01 and abs(pts[2][1] - pts[3][1]) < .01 \
                and abs(pts[1][0] - pts[2][0]) < .01:
            at = svgmeta.arrow_of(ln)
            zs.append((abs(pts[3][1] - pts[0][1]), i, ends[0], ends[1], pts[0][1], pts[3][1], pts[0][0], pts[3][0], at[2] if at else 'related'))
    verticals = [(c, lo, hi, k) for k, ln in enumerate(lines) if ln.startswith('<path d="M') and 'marker-end' in ln
                 for o, c, lo, hi in route.segments(fit_heights.straight(model.arrow_points(ln))) if o == 'v']

    def label_fits(i, y, xa, xb, kind):
        """Will the straight line at y from xa to xb carry its label: a free stretch, between the jump arcs where other arrows cross it
        (7px radius plus the 20px the checker keeps) and the arrowhead (11px), of the label's width plus 20px of shaft each side?"""
        lo, hi = min(xa, xb), max(xa, xb)
        cuts = sorted([lo] + [c for c, v0, v1, k in verticals if k != i and lo < c < hi and v0 < y < v1] + [hi])
        need = draw.label_width(kind) + 40
        pieces = [(b - a) - (27 if a != lo else 0) - (27 if b != hi else 11) for a, b in zip(cuts, cuts[1:])]
        return max(pieces) >= need
    frame_of = {}
    for n, r in rect.items():
        inside = [f for f in frames if f['x'] <= r[0] and r[0] + r[2] <= f['x'] + f['w'] and f['y'] <= r[1] and r[1] + r[3] <= f['y'] + f['h']]
        frame_of[n] = min(inside, key=lambda f: f['w'] * f['h']) if inside else None
    moved, out, straightened = set(), {}, []

    def free(n, y):
        x, _, w, h = rect[n]
        for m, (ox, oy, ow, oh) in rect.items():
            if m != n and ox < x + w + GAP and ox + ow + GAP > x and oy < y + h + GAP and oy + oh + GAP > y:
                return False
        f = frame_of[n]
        return f is None or (f['y'] + 40 <= y and y + h <= f['y'] + f['h'] - 20)

    for _, i, a, b, ya, yb, xa, xb, kind in sorted(zs):
        for n, dy in sorted(((b, ya - yb), (a, yb - ya)), key=lambda t: (degree[t[0]], t[0] != b)):
            if n in moved or n in hold or n in has_straight or abs(dy) < .01:
                continue
            if free(n, rect[n][1] + dy) and label_fits(i, ya if n == b else yb, xa, xb, kind):
                rect[n][1] += dy
                moved.add(n)
                out[n] = round(rect[n][1], 1)
                straightened.append((a, b, n, dy))
                break
    return out, straightened


def move_boxes(text, moves):
    """Move boxes vertically, {box: dy}, with their pop-ups, and the ends of the arrows that touch them: an end on a left or right side
    moves with the straight stretch into it, an end on the top or bottom moves alone (its vertical stretch changes length). Nothing
    else changes. Returns (text, line indexes of the arrows changed)."""
    lines, box, pop, _ = collapse.parse(text)
    sc, _ = model.read(text)
    paths = {}
    get = lambda i: paths.setdefault(i, fit_heights.straight(model.arrow_points(lines[i])))
    for i, ln in enumerate(lines):
        if not (ln.startswith('<path d="M') and 'marker-end' in ln):
            continue
        pts0 = model.arrow_points(ln)
        for k in (0, -1):
            n = next((n for n, r in sc.boxes.items() if model._side(pts0[k], r)), None)
            if n not in moves:
                continue
            side = model._side(pts0[k], sc.boxes[n])
            pts = get(i)
            kk = 0 if k == 0 else len(pts) - 1
            nb = 1 if kk == 0 else len(pts) - 2
            dy = moves[n]
            if side in 'LR' and abs(pts[nb][1] - pts[kk][1]) < .5 and len(pts) > 2:
                pts[nb] = (pts[nb][0], pts[nb][1] + dy)
            pts[kk] = (pts[kk][0], pts[kk][1] + dy)
    for i, pts in paths.items():
        pts = fit_heights.straight(pts)
        if len(pts) < 2:
            raise ValueError('a move leaves the arrow on line %d with no length' % i)
        d = 'M' + ' L'.join('%s,%s' % (draw.fmt(x), draw.fmt(y)) for x, y in pts)
        lines[i] = re.sub(r'd="[^"]*"', 'd="%s"' % d, lines[i], count=1)
    for n, dy in moves.items():
        spans = [(box[n]['a'], box[n]['b'])] + ([pop[n]] if n in pop else [])
        for a, b in spans:
            for k in range(a, b + 1):
                lines[k] = collapse.shift_y_line(lines[k], dy)
    return '\n'.join(lines), sorted(paths)


def straighten(text, tries=4):
    """Returns (text, straightened [(a, b, moved box, dy)], rerouted, problems, invalid before, invalid after). When an arrow whose
    end moved loses the room for its label, the box that moved there stays, and the step runs again from the input (at most `tries`)."""
    before = model.repair(text, count_only=True)[1]
    _, box, _, _ = collapse.parse(text)
    hold = set()
    for _ in range(tries):
        moves, done = plan(text, hold)
        if not moves:
            return text, [], 0, [], before, before
        res, changed = move_boxes(text, {n: y - box[n]['y'] for n, y in moves.items()})
        res, lab_problems = model.replace_labels(text, res, changed)     # the labels of the arrows that changed, placed again on them
        lost = [p for p in lab_problems if 'no straight stretch' in p]
        if not lost:
            break
        guilty = set()
        for p in lost:                                    # 'label of #A kind #B: ...': the moved box at either end stays
            m = re.match(r'label of #(\d+) .* #(\d+):', p)
            guilty |= {int(m.group(1)), int(m.group(2))} & set(moves)
        if not guilty - hold:
            break
        hold |= guilty
    res, _, _ = hops.add_hops(res)
    res, rerouted, bad = model.repair(res)
    res, _, _ = hops.add_hops(res)
    res, _, failed = model.relabel(res, hop_pad=20)
    bad = bad + lab_problems
    after = model.repair(res, count_only=True)[1]
    return res, done, rerouted, bad + ['label near (%d,%d): %s' % f for f in failed], before, after


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        sys.exit(__doc__)
    text = open(args[0], encoding='utf-8').read()
    res, done, rerouted, problems, before, after = straighten(text)
    if after > before and '--force' not in sys.argv:
        print('REFUSED: %d arrows invalid after, %d before. Nothing written.' % (after, before))
        for p in problems:
            print('PROBLEM', p)
        sys.exit(1)
    open(args[1], 'w', encoding='utf-8').write(res)
    print('%d arrows made straight; %d arrows routed again' % (len(done), rerouted))
    for a, b, n, dy in done:
        print('  #%d -> #%d: #%d moved %+.0fpx' % (a, b, n, dy))
    for p in problems:
        print('PROBLEM', p)
    print('next: check_diag.py %s' % args[1])


if __name__ == '__main__':
    main()
