#!/usr/bin/env python3
"""Move boxes to places the user chose, grow a frame, and route again every arrow of a moved box. Other boxes do not move.

usage: move.py IN.svg OUT.svg [N@X,Y ...] [--grow NAME:SIDE:PX ...] [--reroute A>B ...] [--force]

N@X,Y        the new top-left corner of box N (its pop-up moves with it). X or Y may be `=` to keep it, or start with `+`/`-`
             (relative: 3133@=,+124 moves #3133 down 124px).
--grow       moves one side of the frame whose visible title is NAME outward by PX (SIDE: left, right, top, bottom; a negative PX
             moves it inward). The frame title moves with a left or top side.
--reroute    an arrow to route again although neither of its boxes moved (A>B, as reroute.py).
--sides      A>B=SA,SB: the sides (R, L, T, B, or * for any) this arrow must leave A and enter B by, when the user chose a channel
             (3240>3238=R,R: up the right side of a column). Without it the search picks the sides.
--keep-out   X,Y,W,H: a rectangle the arrows routed here keep out of, as if it were a box, when the user chose the corridor (go
             below a row, not over it). Nothing is drawn there; the other arrows are not touched.

Steps, in order:
1. the boxes move and the --grow frames grow; each moved box gets the data-frame of the smallest frame that now holds it
   (svgmeta.py). A moved box that sticks out below the frame it was in makes that frame grow (frames.grow: what lies below moves down
   by as much, and the arrows that ran through it are routed again);
2. every arrow with an end on a moved box, every --reroute arrow and every arrow a push cut is taken out with its label;
3. model.route_arrows routes them in the picture as it now is, the most important first (draw.IMPORTANCE), then the shortest; an
   arrow between two boxes of one frame never leaves it: when the frame has no room, it grows down; each path leaves room for its
   label where it can (the cheapest of the k cheapest that does), and the label goes there;
4. model.settle routes again any other arrow the move left invalid (a box moved onto it), redoes the jump arcs and places again
   every label that now sits badly. Nothing is left for a later step.
A moved box that overlaps another box (28px) or crosses a frame border is printed as a PROBLEM; an arrow with no path is left out,
listed in the metadata ("nopath") and printed. Nothing is written when the result has more invalid arrows than the input (exit 1),
unless --force.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, draw, hops, model, route, svgmeta

GAP = 28.0


def shift_line(line, dx, dy):
    """Shift every coordinate of one line of markup by dx, dy."""
    line = collapse.shift_y_line(line, dy)
    if not dx:
        return line
    f = collapse.fmt
    line = re.sub(r'\b(x|x1|x2|cx)="(-?[\d.]+)"', lambda m: '%s="%s"' % (m.group(1), f(float(m.group(2)) + dx)), line)
    line = re.sub(r'points="([^"]*)"', lambda m: 'points="%s"' % re.sub(r'(-?[\d.]+),(-?[\d.]+)', lambda k: '%s,%s' % (f(float(k.group(1)) + dx), k.group(2)), m.group(1)), line)
    line = re.sub(r'rotate\(-45 ([\d.]+) ([\d.]+)\)', lambda m: 'rotate(-45 %s %s)' % (f(float(m.group(1)) + dx), m.group(2)), line)
    return line


def place(old, spec):
    if spec == '=':
        return old
    if spec[0] in '+-':
        return old + float(spec)
    return float(spec)


def move_and_grow(text, moves, grows):
    """moves {n: (x, y)}, grows [(frame name, side, px)]. Returns the text."""
    lines, box, pop, frames = collapse.parse(text)
    for n, (x, y) in moves.items():
        b = box[n]
        dx, dy = x - b['x'], y - b['y']
        for a, z in [(b['a'], b['b'])] + ([pop[n]] if n in pop else []):
            for k in range(a, z + 1):
                lines[k] = shift_line(lines[k], dx, dy)
    for name, side, px in grows:
        hit = [f for f in frames if svgmeta.frame_name(lines[f['tl']]) == name]
        if len(hit) != 1:
            raise SystemExit('no frame titled %r' % name)
        f = hit[0]
        x, y, w, h = f['x'], f['y'], f['w'], f['h']
        if side == 'right':
            w += px
        elif side == 'bottom':
            h += px
        elif side == 'left':
            x, w = x - px, w + px
            lines[f['tl']] = shift_line(lines[f['tl']], -px, 0)
        elif side == 'top':
            y, h = y - px, h + px
            lines[f['tl']] = shift_line(lines[f['tl']], 0, -px)
        else:
            raise SystemExit('side must be left, right, top or bottom')
        r = lines[f['rl']]
        for k, v in (('x', x), ('y', y), ('width', w), ('height', h)):
            r = re.sub(r'\b%s="[\d.-]+"' % k, '%s="%s"' % (k, collapse.fmt(v)), r, count=1)
        lines[f['rl']] = r
    text = '\n'.join(lines)
    where = svgmeta.drawn_frames(text)
    for n in moves:
        text = svgmeta.set_box(text, n, frame=where.get(n))
    return text


def problems_of_place(text, moved):
    lines, box, _, frames = collapse.parse(text)
    out = []
    for n in moved:
        b = box[n]
        for m, o in box.items():
            if m != n and o['x'] < b['x'] + b['w'] + GAP and o['x'] + o['w'] + GAP > b['x'] and o['y'] < b['y'] + b['h'] + GAP and o['y'] + o['h'] + GAP > b['y']:
                out.append('#%d is closer than %dpx to #%d' % (n, GAP, m))
        for f in frames:
            inside = f['x'] <= b['x'] and b['x'] + b['w'] <= f['x'] + f['w'] and f['y'] <= b['y'] and b['y'] + b['h'] <= f['y'] + f['h']
            apart = b['x'] + b['w'] < f['x'] or b['x'] > f['x'] + f['w'] or b['y'] + b['h'] < f['y'] or b['y'] > f['y'] + f['h']
            if not inside and not apart:
                out.append('#%d crosses the border of frame %r' % (n, f['name']))
    return out


def take_out(lines, i):
    """Line indexes of the arrow on line i and of its label (a label of its word centred on one of its stretches)."""
    return [i] + list(model.label_lines(lines, i))


def fit_frames(text, homes):
    """Grow each frame that a moved box now sticks out of at the bottom, by frames.grow (what lies below moves down), so that the box
    keeps frames.BOTTOM_PAD px above the bottom border. homes {box: frame rect it was in before the move}. Returns (text, line indexes
    of the arrows the pushes cut, [(frame title, px)])."""
    import frames
    cut, grown = set(), []
    for n, rect in homes.items():
        _, box, _, frs = collapse.parse(text)
        b = box[n]
        f = next((f for f in frs if abs(f['x'] - rect[0]) < .5 and abs(f['y'] - rect[1]) < .5), None)
        if f is None or not (f['x'] <= b['x'] and b['x'] + b['w'] <= f['x'] + f['w'] and f['y'] <= b['y'] < f['y'] + f['h']):
            continue                                       # left its frame (problems_of_place says so) or was never in one
        need = b['y'] + b['h'] + frames.BOTTOM_PAD - (f['y'] + f['h'])
        if need > 0:
            push = frames.grow(text, (f['x'], f['y'], f['w'], f['h']), need)
            text, cut = push.text, cut | set(push.cut)
            grown.append((f['name'], need))
    return text, sorted(cut), grown


def move(text, moves, grows=(), extra=(), sides=None, keep_out=()):
    """Returns (text, routed [(a, b, bends, room)], failed [(a, b, why)], place problems). Every arrow of a moved box, every arrow
    named in extra, and every arrow a frame push cut is routed again (model.route_arrows); then model.settle routes again any other
    arrow the move left invalid (a box moved onto it). Nothing is left for a later step."""
    before = text
    lines = text.split('\n')
    todo = [i for i, ln in enumerate(lines) if svgmeta.is_arrow(ln) and (lambda at: at and (at.a in moves or at.b in moves or at[:2] in extra))(model.arrow_at(ln))]
    sc0, _ = model.read(text)
    homes = {n: route.frame_of(sc0, n) for n in moves if n in sc0.boxes}
    text = move_and_grow(text, moves, grows)
    text, cut, grown = fit_frames(text, {n: r for n, r in homes.items() if r})
    text, pend = model.take_out(text, todo + cut, sides, pin=set(sides or {}) | set(extra))
    text, _, _ = hops.add_hops(text)                     # the jump arcs over the arrows just taken out go before routing
    where = problems_of_place(text, moves) + ['frame "%s" grown %dpx (what lies below moved down)' % g for g in grown]
    res = model.route_arrows(text, pend, keep_out)
    where += ['frame "%s" grown %dpx to make room for an arrow' % g for g in res.grown]
    text, _, more = model.settle(before, res.text, [(p.a, p.b) for p in pend])
    where += more
    failed = [(a, b, why) for a, b, _, why in res.failed]
    if failed:
        meta = svgmeta.read(text)
        for a, b, kind, _ in res.failed:
            svgmeta.add_nopath(meta, a, b, kind, 'no path after move.py')
        text = svgmeta.write(text, meta)
    return text, res.routed, failed, where + [model.no_label(x) for x in res.unlabelled]


def main():
    argv = sys.argv[1:]
    args, grows, extra, sides, keep_out = [], [], [], {}, []
    k = 0
    while k < len(argv):
        a = argv[k]
        if a == '--keep-out':
            keep_out.append(tuple(float(v) for v in argv[k + 1].split(',')))
            k += 2
        elif a == '--sides':
            pair, ss = argv[k + 1].split('=')
            sides[tuple(int(x.lstrip('#')) for x in pair.split('>'))] = tuple(ss.split(','))
            k += 2
        elif a == '--grow':
            name, side, px = argv[k + 1].rsplit(':', 2)
            grows.append((name, side, float(px)))
            k += 2
        elif a == '--reroute':
            extra.append(tuple(int(x.lstrip('#')) for x in argv[k + 1].split('>')))
            k += 2
        elif a.startswith('--'):
            k += 1
        else:
            args.append(a)
            k += 1
    if len(args) < 2:
        sys.exit(__doc__)
    src, out = args[0], args[1]
    text = open(src, encoding='utf-8').read()
    _, box, _, _ = collapse.parse(text)
    moves = {}
    for m in args[2:]:
        ns, xy = m.split('@')
        sx, sy = xy.split(',')
        n = int(ns.lstrip('#'))
        moves[n] = (place(box[n]['x'], sx), place(box[n]['y'], sy))
    before = model.repair(text, count_only=True)[1]
    res, routed, failed, where = move(text, moves, grows, extra, sides, keep_out)
    after = model.repair(res, count_only=True)[1]
    if after > before and '--force' not in sys.argv:
        print('REFUSED: %d arrows invalid after, %d before. Nothing written.' % (after, before))
        sys.exit(1)
    want, got = model.count_arrows(text) - len(failed), model.count_arrows(res)   # a failed arrow is left out (nopath); no other may go
    if got != want:
        print('REFUSED: %d arrows after, %d expected (%d before, %d left out). Nothing written.' % (got, want, want + len(failed), len(failed)))
        sys.exit(1)
    open(out, 'w', encoding='utf-8').write(res)
    for n, (x, y) in moves.items():
        print('#%d: x %s y %s' % (n, collapse.fmt(x), collapse.fmt(y)))
    for a, b, bends, room in routed:
        print('#%d -> #%d: %d bends%s' % (a, b, bends, '' if room else ' (WARN: no path of the cheapest had room for the full label)'))
    for p in where:
        print('PROBLEM', p)
    for a, b, why in failed:
        print('PROBLEM #%d -> #%d: %s' % (a, b, why))
    print('next: check_diag.py %s' % out)


if __name__ == '__main__':
    main()
