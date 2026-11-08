#!/usr/bin/env python3
"""Route again some arrows of a diagram, in the diagram as it is. Boxes and the other arrows do not move.

usage: reroute.py IN.svg OUT.svg (A>B ...|--frame-leavers) [--force]

A>B names one drawn arrow by its two boxes (its data-from and data-to, svgmeta.py). --frame-leavers takes every arrow whose two boxes are
in the same frame but whose path leaves that frame (check_diag.py fails them). Each one, in turn: its path and its label are removed,
route.py finds a new path in the picture as it is now (an arrow inside one frame is searched inside it first), the label goes on the new
path. Then hops.py redoes the jump arcs and model.relabel() moves labels that now sit badly. An arrow that finds no path keeps its old
one and is printed. Nothing is written when the result has more invalid arrows than the input (exit 1), unless --force.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draw, hops, model, route, svgmeta


def leaves_frame(text):
    """(a, b) of every drawn arrow whose two boxes share a frame while some point of its path is outside that frame."""
    sc, info = model.read(text)
    out = []
    for ln in info['lines']:
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if not at or at[0] not in sc.boxes or at[1] not in sc.boxes:
            continue
        fr = route.common_frame(sc, at[0], at[1])
        if fr and any(not (fr[0] - 1 <= x <= fr[0] + fr[2] + 1 and fr[1] - 1 <= y <= fr[1] + fr[3] + 1) for x, y in model.arrow_points(ln)):
            out.append(at[:2])
    return out


def reroute(text, pairs):
    """Returns (text, done, failed)."""
    done, failed = [], []
    for a, b in pairs:
        lines = text.split('\n')
        hit = [i for i, l in enumerate(lines) if svgmeta.is_arrow(l) and (svgmeta.arrow_of(l) or (None, None))[:2] == (a, b)]
        if len(hit) != 1:
            failed.append((a, b, '%d drawn arrows with these ends' % len(hit)))
            continue
        i = hit[0]
        kind = svgmeta.arrow_of(lines[i])[2]
        segs = route.segments(model.arrow_points(lines[i]))
        gone = {i}
        for j in range(len(lines)):                       # its label: a label of its word centred on one of its stretches
            lab = draw.label_at(lines, j)
            if lab and lab[5] == kind:
                cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
                if any((o == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1) for o, c, lo, hi in segs):
                    gone |= set(range(j, j + 1 + lab[4]))
                    lab_at = j
                    break
        else:
            lab_at = None
        rest = '\n'.join(l for k, l in enumerate(lines) if k not in gone)
        sc, _ = model.read(rest)
        pts = route.route(sc, a, b, '*', '*')
        if not pts:
            failed.append((a, b, 'no path: the old one stays'))
            continue
        lines[i] = re.sub(r'd="[^"]*"', 'd="M%s"' % ' L'.join('%s,%s' % (draw.fmt(x), draw.fmt(y)) for x, y in pts), lines[i], count=1)
        sc.arrows.append(list(pts))
        lab = route.place_label(sc, pts, kind)
        if lab_at is not None:                            # the old label lines go; the new label takes their place
            n_old = len([k for k in gone if k != i])
            lines[lab_at:lab_at + n_old] = draw.label(kind, *lab) if lab else []
        elif lab:
            k = next((k for k, l in enumerate(lines) if l == '<!--legend-->'), len(lines) - 2)
            lines[k:k] = draw.label(kind, *lab)
        text = '\n'.join(lines)
        done.append((a, b, len(pts) - 2, bool(sc.left_frame)))
    return text, done, failed


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 2:
        sys.exit(__doc__)
    src, out = args[0], args[1]
    text = open(src, encoding='utf-8').read()
    pairs = [tuple(int(x.lstrip('#')) for x in p.split('>')) for p in args[2:]]
    if '--frame-leavers' in sys.argv:
        pairs += [p for p in leaves_frame(text) if p not in pairs]
    if not pairs:
        print('nothing to route again')
        open(out, 'w', encoding='utf-8').write(text)
        return
    before = model.repair(text, count_only=True)[1]
    res, done, failed = reroute(text, pairs)
    res, _, _ = hops.add_hops(res)
    res, _, bad = model.relabel(res, hop_pad=20)
    after = model.repair(res, count_only=True)[1]
    if after > before and '--force' not in sys.argv:
        print('REFUSED: %d arrows invalid after, %d before. Nothing written.' % (after, before))
        sys.exit(1)
    open(out, 'w', encoding='utf-8').write(res)
    for a, b, bends, left in done:
        print('#%d -> #%d: %d bends%s' % (a, b, bends, ' (no path inside their frame: it leaves it)' if left else ''))
    for a, b, why in failed:
        print('PROBLEM #%d -> #%d: %s' % (a, b, why))
    for x, y, why in bad:
        print('PROBLEM label near (%d,%d): %s' % (x, y, why))
    print('next: check_diag.py %s' % out)


if __name__ == '__main__':
    main()
