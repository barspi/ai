#!/usr/bin/env python3
"""Jump arcs: where a horizontal arrow crosses a vertical arrow, the horizontal one hops over it.

As a command:   hops.py IN.svg OUT.svg        (OUT may be IN)   prints how many arcs it added and how many stale ones it removed.
As a module:    hops.add_hops(svg_text) -> (svg_text, added, removed)

add_nodes.py and collapse.py call it by themselves after they write arrows, so a revision needs no separate hops step. Run the command
only on a diagram whose arrows were edited by hand.

A path is `M x,y L x,y ...`, possibly with arcs `A7 7 0 0 1 x,y` already in it (an arc over a real crossing is left alone; an arc that
hops over nothing, because the arrow it hopped was moved, is removed). For every plain crossing of a horizontal run of path A with a
vertical run of path B (B is any arrow), A gets a 14px arc over B, drawn above the line (the skill rule: the horizontal arrow hops).
A crossing closer than 12px to the end of a run is not a crossing (it is a bend or a touching end) and is skipped. Two verticals closer
than 20px get one arc, not two. Only arrows are read: a `<path d="M ..." ... marker-end=...>` on one line, as add_nodes.py and the
sample generator write them.
"""
import re, sys

R = 7.0


def fmt(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')


def parse(d):
    """-> list of ('M'|'L'|'A', (x, y), arc numbers or None) with arcs kept as they are."""
    out = []
    for m in re.finditer(r'([MLA])\s*((?:-?[\d.]+[ ,]*)+)', d):
        nums = [float(v) for v in re.findall(r'-?[\d.]+', m.group(2))]
        if m.group(1) == 'A':
            out.append(('A', (nums[5], nums[6]), nums))
        else:
            out.append((m.group(1), (nums[0], nums[1]), None))
    return out


def is_arrow(ln):
    return ln.startswith('<path d="M') and 'marker-end' in ln


def add_hops(text, marks=True):
    """Repeat until nothing changes (an arrow that had an arc removed can have a new crossing right after it). Then, unless marks is
    False, xmarks.redo() (that adds lines: a caller that keeps line numbers across the call passes marks=False)."""
    total_added = total_removed = 0
    for _ in range(5):
        text, added, removed = _once(text)
        total_added += added
        total_removed += removed
        if not added and not removed:
            break
    import xmarks                                  # the red crosses go on top of the boxes again (xmarks.py)
    return (xmarks.redo(text) if marks else text), total_added, total_removed


def unparse(seg):
    out = []
    for c, (x, y), nums in seg:
        if c == 'A':
            out.append('A%s %s,%s' % (' '.join(fmt(v) for v in nums[:5]), fmt(x), fmt(y)))
        else:
            out.append('%s%s,%s' % (c, fmt(x), fmt(y)))
    return ' '.join(out)


def merge_runs(seg):
    """Drop a plain point that lies inside one straight run (the run goes on the same way after it): a removed arc leaves its two ends
    behind as such points. The line looks the same, but route.py keeps other arrows away from every point of a path and this step
    skips a crossing near one, so a left-over point can close a channel. The start of an arc and the end of one are kept."""
    out = [seg[0]]
    for i in range(1, len(seg) - 1):
        (pc, p, _), (cc, c, _), (nc, n, _) = out[-1], seg[i], seg[i + 1]
        if cc == 'L' and nc == 'L':
            if abs(p[1] - c[1]) < .01 and abs(c[1] - n[1]) < .01 and (p[0] - c[0]) * (c[0] - n[0]) > 0:
                continue
            if abs(p[0] - c[0]) < .01 and abs(c[0] - n[0]) < .01 and (p[1] - c[1]) * (c[1] - n[1]) > 0:
                continue
        out.append(seg[i])
    return out + seg[-1:]


def _once(text):
    lines = text.split('\n')
    for k, ln in enumerate(lines):                # first, the points left by arcs removed earlier
        if is_arrow(ln):
            d = ln.split('"')[1]
            seg = parse(d)
            if len(seg) > 2:
                m = merge_runs(seg)
                if len(m) < len(seg):
                    lines[k] = ln.replace('d="%s"' % d, 'd="%s"' % unparse(m), 1)
    verts, horiz = [], []                      # vertical and horizontal runs of every arrow
    for k, ln in enumerate(lines):
        if not is_arrow(ln):
            continue
        seg = parse(ln.split('"')[1])
        for a, b in zip(seg, seg[1:]):
            if b[0] != 'L':
                continue
            if abs(a[1][0] - b[1][0]) < .01 and abs(a[1][1] - b[1][1]) > 0.01:
                verts.append((k, a[1][0], min(a[1][1], b[1][1]), max(a[1][1], b[1][1])))
            elif abs(a[1][1] - b[1][1]) < .01 and abs(a[1][0] - b[1][0]) > 0.01:
                horiz.append((k, a[1][1], min(a[1][0], b[1][0]), max(a[1][0], b[1][0])))

    def stale(k, a, b):
        """An existing arc from a to b that hops over nothing: no other arrow crosses it there (the arrow it hopped was moved)."""
        if abs(a[1] - b[1]) < .01:             # arc on a horizontal run: a vertical of another arrow must cross at its middle
            cx, cy = (a[0] + b[0]) / 2, a[1]
            return not any(kk != k and abs(x - cx) <= 1.5 and y0 < cy < y1 for kk, x, y0, y1 in verts)
        if abs(a[0] - b[0]) < .01:             # arc on a vertical run
            cx, cy = a[0], (a[1] + b[1]) / 2
            return not any(kk != k and abs(y - cy) <= 1.5 and x0 < cx < x1 for kk, y, x0, x1 in horiz)
        return False

    removed = added = 0
    for k, ln in enumerate(lines):
        if not is_arrow(ln):
            continue
        d = ln.split('"')[1]
        seg = parse(d)
        new = ['M%s,%s' % (fmt(seg[0][1][0]), fmt(seg[0][1][1]))]
        changed = False
        for a, b in zip(seg, seg[1:]):
            if b[0] == 'A':
                if stale(k, a[1], b[1]):
                    new.append('L%s,%s' % (fmt(b[1][0]), fmt(b[1][1])))
                    removed += 1
                    changed = True
                    continue
                new.append('A%s %s,%s' % (' '.join(fmt(v) for v in b[2][:5]), fmt(b[2][5]), fmt(b[2][6])))      # keep the x,y form: later scripts read pairs with a comma
                continue
            ax, ay = a[1]
            bx, by = b[1]
            if abs(ay - by) < .01 and abs(ax - bx) > 0.01 and a[0] != 'A':
                lo, hi = sorted((ax, bx))
                hits = sorted({x for kk, x, y0, y1 in verts if kk != k and lo + 12 < x < hi - 12 and y0 + 3 < ay < y1 - 3})
                keep, last = [], None          # two verticals closer than 20px would make overlapping arcs: skip the second
                for x in hits:
                    if last is None or x - last >= 20:
                        keep.append(x)
                        last = x
                if bx < ax:
                    keep.reverse()
                for x in keep:
                    sweep = 1 if bx > ax else 0
                    new.append('L%s,%s A7 7 0 0 %d %s,%s' % (fmt(x - R if bx > ax else x + R), fmt(ay), sweep, fmt(x + R if bx > ax else x - R), fmt(ay)))
                    added += 1
                    changed = True
            new.append('L%s,%s' % (fmt(bx), fmt(by)))
        if changed:
            lines[k] = ln.replace('d="%s"' % d, 'd="%s"' % ' '.join(new), 1)
    return '\n'.join(lines), added, removed


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    out, n_added, n_removed = add_hops(open(sys.argv[1], encoding='utf-8').read())
    open(sys.argv[2], 'w', encoding='utf-8').write(out)
    print('hops added:', n_added, 'stale arcs removed:', n_removed)
