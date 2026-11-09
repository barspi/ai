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
1. the boxes move and the frames grow; each moved box gets the data-frame of the smallest frame that now holds it (svgmeta.py);
2. every arrow with an end on a moved box, and every --reroute arrow, is taken out with its label;
3. they are routed again in the picture as it now is, the most important first (draw.IMPORTANCE), then the shortest (the distance
   between the two box centres); an arrow inside one frame is searched inside it first (route.py); its label goes on the new path;
4. hops.py redoes the jump arcs and model.relabel() moves labels that now sit badly.
A moved box that overlaps another box (28px) or crosses a frame border is printed as a PROBLEM; an arrow with no path is left out and
printed. Nothing is written when the result has more invalid arrows than the input (exit 1), unless --force.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, draw, hops, model, route, svgmeta

GAP = 28.0
GONE = '<!--move.py: gone-->'


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
    kind = svgmeta.arrow_of(lines[i])[2]
    segs = route.segments(model.arrow_points(lines[i]))
    for j in range(len(lines)):
        lab = draw.label_at(lines, j)
        if lab and lab[5] == kind:
            cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
            if any((o == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1) for o, c, lo, hi in segs):
                return [i] + list(range(j, j + 1 + lab[4]))
    return [i]


def move(text, moves, grows=(), extra=(), sides=None, keep_out=()):
    """Returns (text, routed [(a, b, bends, left its frame)], failed [(a, b, why)], place problems)."""
    lines = text.split('\n')
    todo = []
    for i, ln in enumerate(lines):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at and (at[0] in moves or at[1] in moves or at[:2] in extra):
            todo.append((i, at))
    slots = {}
    for i, at in todo:
        gone = take_out(lines, i)
        slots[i] = (lines[i], gone[1] if len(gone) > 1 else None)
        for k in gone:
            lines[k] = GONE
    text = move_and_grow('\n'.join(lines), moves, grows)
    # The jump arcs over the arrows just taken out go now, before routing: a stale arc splits the line it sits on, and route.py keeps
    # every other arrow away from a split point, so an arc over nothing can close a channel. hops.py keeps the lines in place.
    text, _, _ = hops.add_hops(text, marks=False)          # marks=False: the line numbers of the slots must not move
    where = problems_of_place(text, moves)
    sc0, _ = model.read(text)
    centre = lambda n: (sc0.boxes[n][0] + sc0.boxes[n][2] / 2, sc0.boxes[n][1] + sc0.boxes[n][3] / 2)
    order = sorted(todo, key=lambda t: (-draw.IMPORTANCE.get(t[1][2], 2),
                                        sum(abs(p - q) for p, q in zip(centre(t[1][0]), centre(t[1][1])))))
    routed, failed = [], []
    lines = text.split('\n')                              # one list for the whole loop: a slot may come to hold two lines of markup
    for i, (a, b, kind) in order:
        text = '\n'.join(lines)
        sc, _ = model.read(text)
        for k, r in enumerate(keep_out):                  # an obstacle like a box, under a key no box has
            sc.boxes[-1 - k] = tuple(r)
        pts = route.route(sc, a, b, *(sides or {}).get((a, b), ('*', '*')))
        for k in range(len(keep_out)):
            del sc.boxes[-1 - k]
        if not pts:
            failed.append((a, b, 'no path: the arrow is left out'))
            continue
        old, lab_at = slots[i]
        lines[i] = re.sub(r'd="[^"]*"', 'd="M%s"' % ' L'.join('%s,%s' % (draw.fmt(x), draw.fmt(y)) for x, y in pts), old, count=1)
        sc.arrows.append(list(pts))
        lab = route.place_label(sc, pts, kind)
        if lab:
            k = lab_at if lab_at is not None else i
            lines[k] = '\n'.join(draw.label(kind, *lab))
        routed.append((a, b, len(pts) - 2, bool(sc.left_frame)))
    text = '\n'.join(l for l in '\n'.join(lines).split('\n') if l != GONE)
    if failed:
        meta = svgmeta.read(text)
        for a, b, _ in failed:
            svgmeta.add_nopath(meta, a, b, next(k for _, (x, y, k) in todo if (x, y) == (a, b)), 'no path after move.py')
        text = svgmeta.write(text, meta)
    return text, routed, failed, where


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
        n, xy = m.split('@')
        sx, sy = xy.split(',')
        n = int(n.lstrip('#'))
        moves[n] = (place(box[n]['x'], sx), place(box[n]['y'], sy))
    before = model.repair(text, count_only=True)[1]
    res, routed, failed, where = move(text, moves, grows, extra, sides, keep_out)
    res, _, _ = hops.add_hops(res)
    res, _, bad = model.relabel(res, hop_pad=20)
    after = model.repair(res, count_only=True)[1]
    if after > before and '--force' not in sys.argv:
        print('REFUSED: %d arrows invalid after, %d before. Nothing written.' % (after, before))
        sys.exit(1)
    open(out, 'w', encoding='utf-8').write(res)
    for n, (x, y) in moves.items():
        print('#%d: x %s y %s' % (n, collapse.fmt(x), collapse.fmt(y)))
    for a, b, bends, left in routed:
        print('#%d -> #%d: %d bends%s' % (a, b, bends, ' (no path inside their frame: it leaves it)' if left else ''))
    for p in where:
        print('PROBLEM', p)
    for a, b, why in failed:
        print('PROBLEM #%d -> #%d: %s' % (a, b, why))
    for x, y, why in bad:
        print('PROBLEM label near (%d,%d): %s' % (x, y, why))
    print('next: check_diag.py %s' % out)


if __name__ == '__main__':
    main()
