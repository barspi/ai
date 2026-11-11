#!/usr/bin/env python3
"""Close the empty space that collapsing (or removing) boxes leaves, in the diagram as it is. Boxes only move up; columns and frames stay.

usage: compact.py IN.svg OUT.svg [--gap 28] [--frame WORDS] [--force]

--frame WORDS: only the frame whose title contains WORDS (and the frames inside it) closes its gaps and shrinks; what lies below it in
the same columns moves up by the same amount, and every other gap of the picture stays.

Method (generic, read from the SVG; nothing about one diagram):
1. Every box belongs to the smallest dotted frame that contains it, or to no frame. Boxes of one region and one column keep their order
   and, when the gap between two is over 60px, move up until they are `gap` px apart (100px where a vertical arrow with a label joins two
   neighbours). A gap where a bent arrow ends on the bottom of the upper box or the top of the lower one stays as it is: that arrow
   runs in the gap, often beside the lanes of others, and the router needs the room it had (a rule that left 25px per lane plus 25px
   still lost such an arrow, and the frame came out no shorter: the lowest column sets its bottom). A gap of 60px or less is left alone: it may carry arrows.
2. Boxes joined by a straight horizontal arrow form a chain and move together, so that arrow stays straight.
3. A frame shrinks to its lowest box (+ its old bottom padding). Whatever lies below a shrunk frame in the same columns (frames, their
   boxes, other boxes) moves up by the same amount.
4. The result goes through collapse.process (--moves): it moves the boxes and frames, re-attaches the arrows that end on them keeping their
   shape, puts the labels on a straight stretch and grows or shrinks the canvas. Then model.repair() routes again (route.py) every arrow
   that is invalid (an end on no box, a run through a box, a run within 14px of another arrow), hops.py redoes the jump arcs and
   model.relabel() moves labels that sit badly. If the result has more invalid arrows than the input had, nothing is written (exit 1)
   unless --force is given. Run check_diag.py afterwards.
"""
import json, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, hops, model

VGAP = 100.0


def compute(text, gap=28.0, min_gap=60.0, only=None):
    """only: words of one frame's title; then only the boxes of that frame (and of frames inside it) close their gaps, only that
    frame shrinks, and what lies below it in the same columns moves up by the same amount. Every other gap stays."""
    lines, box, pop, frame = collapse.parse(text)
    R = {n: [b['x'], b['y'], b['w'], b['h']] for n, b in box.items()}
    member = {}
    for n, (x, y, w, h) in R.items():
        inside = [i for i, f in enumerate(frame) if f['x'] <= x and x + w <= f['x'] + f['w'] and f['y'] <= y and y + h <= f['y'] + f['h']]
        member[n] = min(inside, key=lambda i: frame[i]['w'] * frame[i]['h']) if inside else -1
    scope = None                                 # the frames whose boxes may close their gaps (None: all)
    if only:
        hit = [i for i, f in enumerate(frame) if only.lower() in f['name'].lower()]
        if len(hit) != 1:
            sys.exit('--frame %r: %d frames have it in their title' % (only, len(hit)))
        t = frame[hit[0]]
        scope = {i for i, f in enumerate(frame) if t['x'] <= f['x'] and f['x'] + f['w'] <= t['x'] + t['w'] and t['y'] <= f['y'] and f['y'] + f['h'] <= t['y'] + t['h']}
    # straight horizontal arrows tie their two boxes into a chain; vertical arrows ask for a taller gap
    arrows = [model.arrow_points(l) for l in lines if l.startswith('<path d="M') and 'marker-end' in l]

    def at(p):
        for n, (x, y, w, h) in R.items():
            if y - 3 <= p[1] <= y + h + 3 and (abs(p[0] - x) <= 3 or abs(p[0] - (x + w)) <= 3):
                return n
        return None

    def at_tb(p):
        for n, (x, y, w, h) in R.items():
            if x - 3 <= p[0] <= x + w + 3 and (abs(p[1] - y) <= 3 or abs(p[1] - (y + h)) <= 3):
                return n
        return None

    parent = {n: n for n in R}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    vert = set()
    for pts in arrows:
        a, b = at(pts[0]), at(pts[-1])
        if len(pts) == 2 and abs(pts[0][1] - pts[1][1]) < .01 and a is not None and b is not None and a != b:
            parent[find(a)] = find(b)
        if len(pts) == 2 and abs(pts[0][0] - pts[1][0]) < .01:
            a, b = at_tb(pts[0]), at_tb(pts[-1])
            if a is not None and b is not None:
                vert.add(frozenset((a, b)))
    tops, bottoms = set(), set()                 # boxes with an arrow end on their top or bottom side: that arrow runs in the gap
    for pts in arrows:
        for p in (pts[0], pts[-1]):
            for n, (x, y, w, h) in R.items():
                if x - 3 <= p[0] <= x + w + 3:
                    if abs(p[1] - y) <= 3:
                        tops.add(n)
                    elif abs(p[1] - (y + h)) <= 3:
                        bottoms.add(n)
    chains = {}
    for n in R:
        chains.setdefault(find(n), []).append(n)

    NY = {n: R[n][1] for n in R}
    cols = {}
    for n in R:
        cols.setdefault((member[n], round(R[n][0])), []).append(n)

    def limit(n):
        lst = sorted(cols[(member[n], round(R[n][0]))], key=lambda m: NY[m])
        i = lst.index(n)
        if i == 0:
            return 0.0
        p = lst[i - 1]
        g = VGAP if frozenset((p, n)) in vert else gap
        cur = NY[n] - (NY[p] + R[p][3])
        if cur <= min_gap:                       # a gap that is already tight is left alone (it may carry arrows)
            return 0.0
        if g != VGAP and (p in bottoms or n in tops):   # a bent arrow ends on the bottom of p or the top of n: it runs in this gap,
            return 0.0                                   # often beside the lanes of others; the router needs the room it had
        return max(0.0, cur - g)

    for _ in range(40):
        moved = False
        for members in chains.values():
            if scope is not None and any(member[n] not in scope for n in members):
                continue
            d = min(limit(n) for n in members)
            if d > 0.5:
                for n in members:
                    NY[n] -= d
                moved = True
        if not moved:
            break

    # frames shrink to their lowest box; what lies below them (same columns) moves up by the same amount
    FY = {i: f['y'] for i, f in enumerate(frame)}
    FH = {i: f['h'] for i, f in enumerate(frame)}
    for i in sorted(range(len(frame)), key=lambda i: frame[i]['y']):
        mem = [n for n in R if member[n] == i]
        if not mem or (scope is not None and i not in scope):
            continue
        f = frame[i]
        pad = f['y'] + f['h'] - max(R[n][1] + R[n][3] for n in mem)
        new_h = max(NY[n] + R[n][3] for n in mem) + pad - FY[i]
        s = FH[i] - new_h
        if s > 1:
            old_bottom = FY[i] + FH[i]
            FH[i] = new_h
            for j, g in enumerate(frame):
                if j != i and g['y'] >= old_bottom - 1 and g['x'] < f['x'] + f['w'] and g['x'] + g['w'] > f['x']:
                    FY[j] -= s
                    for n in R:
                        if member[n] == j:
                            NY[n] -= s
            for n in R:
                if member[n] == -1 and R[n][1] >= old_bottom - 1 and R[n][0] < f['x'] + f['w'] and R[n][0] + R[n][2] > f['x']:
                    NY[n] -= s
    boxes = {str(n): round(NY[n], 1) for n in R if abs(NY[n] - R[n][1]) > .05}
    frames = {f['name']: {'y': round(FY[i], 1), 'h': round(FH[i], 1)} for i, f in enumerate(frame) if abs(FY[i] - f['y']) > .05 or abs(FH[i] - f['h']) > .05}
    return {'boxes': boxes, 'frames': frames}


def main():
    argv = sys.argv[1:]
    gap, only = 28.0, None
    if '--gap' in argv:
        gap = float(argv.pop(argv.index('--gap') + 1))
    if '--frame' in argv:
        only = argv.pop(argv.index('--frame') + 1)
    args = [a for a in argv if not a.startswith('--')]
    if len(args) != 2:
        sys.exit(__doc__)
    text = open(args[0], encoding='utf-8').read()
    moves = compute(text, gap, only=only)
    if not moves['boxes'] and not moves['frames']:
        print('nothing to close')
        open(args[1], 'w', encoding='utf-8').write(text)
        return
    before = model.repair(text, count_only=True)[1]
    res, log = collapse.process(text, {}, moves)
    res, added, removed = hops.add_hops(res)
    res, rerouted, bad = model.repair(res)                  # arrows the move left invalid are routed again, in the diagram as it is
    res, added2, removed2 = hops.add_hops(res)
    added, removed = added + added2, removed + removed2
    res, relabeled, failed = model.relabel(res)
    after = model.repair(res, count_only=True)[1]
    if after > before and '--force' not in sys.argv:     # a move must never leave the diagram worse than it was
        print('REFUSED: closing the gaps would leave %d arrows invalid (%d before). Nothing written. Collapse fewer boxes at a time, '
              'or run with --force and repair the arrows by hand.' % (after, before))
        for p in bad:
            print('PROBLEM', p)
        sys.exit(1)
    open(args[1], 'w', encoding='utf-8').write(res)
    print('moved %d boxes, %d frames; %d arrows routed again; jump arcs: %d added, %d stale removed; %d labels moved' % (
        len(moves['boxes']), len(moves['frames']), rerouted, added, removed, relabeled))
    print('\n'.join(l for l in log if not l.startswith('NOTE')))
    for p in bad:
        print('PROBLEM', p)
    for p in failed:
        print('PROBLEM label near (%d,%d): %s' % p)
    print('next: check_diag.py %s' % args[1])


if __name__ == '__main__':
    main()
