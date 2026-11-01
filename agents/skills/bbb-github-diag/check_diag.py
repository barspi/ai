#!/usr/bin/env python3
"""Geometry, text and content checks for an issue/PR lineage SVG. No rendering.
usage: check_diag.py new.svg [old.svg]
Exit code 1 when a check fails. Checks the SVG text and path geometry only."""
import re, sys
import xml.dom.minidom as md
from fonts import load      # finds Helvetica/Arial/Liberation/DejaVu and Menlo/Consolas/... on macOS, Linux and Windows

new = open(sys.argv[1], encoding='utf-8').read()
old = open(sys.argv[2], encoding='utf-8').read() if len(sys.argv) > 2 else None
fails = 0


def fail(msg):
    global fails
    fails += 1
    print('FAIL', msg)


md.parseString(new)
print('xml ok')

# ---- text widths, measured once per style (a Helvetica-like sans, a Menlo-like mono for the merge line)
_f, _w = {}, {}


def font(cls):
    if cls not in _f:
        style, size = {'ttl': ('regular', 12.5), 'meta': ('regular', 11), 'note': ('italic', 11), 'mono': ('mono', 11), 'bold': ('bolditalic', 11)}[cls]
        _f[cls] = load(style, int(size * 4))
    return _f[cls]


def width(cls, text):
    k = (cls, text)
    if k not in _w:
        _w[k] = font(cls).getlength(text) / 4
    return _w[k]


# ---- parse
boxes = {int(m.group(1)): tuple(float(v) for v in m.groups()[1:]) for m in re.finditer(
    r'<g id="n(\d+)">\s*<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', new)}
labels = [tuple(float(v) for v in m.groups()) for m in re.finditer(
    r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="4" fill="#fffdf7"', new)]
paths = []
for m in re.finditer(r'<path d="M([^"]+)" fill="none"', new):
    d = m.group(1)
    pts = [(float(a), float(b)) for a, b in re.findall(r'(-?\d+\.?\d*),(-?\d+\.?\d*)', d)]
    paths.append((pts, 'A' in d))
frames = [tuple(float(v) for v in m.groups()) for m in re.finditer(
    r'<rect x="([\d.-]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="18" fill="#ffffff"', new)]
print(len(boxes), 'boxes', len(paths), 'paths', len(labels), 'labels', len(frames), 'frames')

# ---- text inside boxes must fit
for n, (bx, by, bw, bh) in boxes.items():
    for m in re.finditer(r'<text class="(ttl|meta|note|mono)" x="([\d.]+)" y="([\d.]+)">(.*?)</text>', new):
        cls, x, y, body = m.group(1), float(m.group(2)), float(m.group(3)), m.group(4)
        if bx <= x <= bx + 20 and by < y < by + bh:
            def clean(t):
                t = re.sub(r'<title>.*?</title>', '', t)      # a link's tooltip is not drawn text
                t = re.sub(r'<[^>]+>', '', t)
                t = t.replace('&#183;', '·').replace('&#8211;', '–').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                return re.sub(r'&#(\d+);', lambda k: chr(int(k.group(1))), t)
            txt = clean(body)
            w = width(cls, txt)
            for bm in re.finditer(r'<tspan style="font-weight:700">(.*?)</tspan>(?=</text>|<)', body):   # bold runs are wider
                seg = clean(bm.group(1))
                w += width('bold', seg) - width(cls, seg)
            if x + w > bx + bw - 12:
                fail(f'text too wide in #{n}: "{txt[:40]}" {w:.0f}px')

# ---- the assignee or submitter name must not run into the pill or the red cross, and must be at least 9px
for n, (bx, by, bw, bh) in boxes.items():
    g = re.search(r'<g id="n%d">(.*?)</g>' % n, new, re.S).group(1)
    k = re.search(r'<text class="kind" x="([\d.]+)" y="([\d.]+)"', g)
    nm = re.search(r'<text class="meta" x="([\d.]+)" y="([\d.]+)" style="[^"]*font-size:([\d.]+)px[^"]*">([^<]*)</text>', g)
    pill = re.search(r'<rect x="([\d.]+)" y="[\d.]+" width="[\d.]+" height="20" rx="10"', g)
    if not (k and nm and pill):
        continue
    x, y, size, text = float(nm.group(1)), float(nm.group(2)), float(nm.group(3)), nm.group(4)
    if size < 9 - 0.01:
        fail(f'name in #{n} is {size}px (minimum 9px; use a second line)')
    w = load('bold', int(size * 4)).getlength(text.replace('&amp;', '&')) / 4
    on_label_line = abs(y - float(k.group(2))) < 1
    cross = re.search(r'<line x1="([\d.]+)"[^>]*stroke="#ff2a2a"', g)
    limit = (float(cross.group(1)) - 6 - 6 if cross else float(pill.group(1)) - 6) if on_label_line else bx + bw - 12
    if x + w > limit + 0.5:
        fail(f'name "{text}" in #{n} ends at {x + w:.0f}, past {limit:.0f} (pill or cross): shrink to 9px or use a second line')

# ---- segments
segs = []
for i, (pts, arcs) in enumerate(paths):
    for p, q in zip(pts, pts[1:]):
        if abs(p[1] - q[1]) < .01:
            segs.append((i, 'h', p[1], min(p[0], q[0]), max(p[0], q[0]), arcs))
        elif abs(p[0] - q[0]) < .01:
            segs.append((i, 'v', p[0], min(p[1], q[1]), max(p[1], q[1]), arcs))


def seg_in_box(sg, r, pad=1):
    i, o, c, lo, hi, _ = sg
    x, y, w, h = r
    if o == 'h':
        return y + pad < c < y + h - pad and lo < x + w - pad and hi > x + pad
    return x + pad < c < x + w - pad and lo < y + h - pad and hi > y + pad


for i, (pts, arcs) in enumerate(paths):  # arrow tips touch a box edge
    px, py = pts[-1]
    ok = any((abs(px - bx) < 1.5 or abs(px - (bx + bw)) < 1.5) and by - 1 <= py <= by + bh + 1 or
             (abs(py - by) < 1.5 or abs(py - (by + bh)) < 1.5) and bx - 1 <= px <= bx + bw + 1
             for (bx, by, bw, bh) in boxes.values())
    if not ok:
        fail(f'path {i} tip ({px},{py}) does not touch a box')

for sg in segs:
    for n, r in boxes.items():
        if seg_in_box(sg, r):
            fail(f'path {sg[0]} runs through box #{n}')

# ---- labels
for k, (x, y, w, h) in enumerate(labels):
    for n, (bx, by, bw, bh) in boxes.items():
        if bx - 2 < x + w and bx + bw + 2 > x and by - 2 < y + h and by + bh + 2 > y:
            fail(f'label {k} at ({x:.0f},{y:.0f}) overlaps box #{n}')
    for k2 in range(k + 1, len(labels)):
        x2, y2, w2, h2 = labels[k2]
        if x - 2 < x2 + w2 and x + w + 2 > x2 and y - 2 < y2 + h2 and y + h + 2 > y2:
            fail(f'labels {k} and {k2} overlap near ({x:.0f},{y:.0f})')
    own = None
    for sg in segs:
        i, o, c, lo, hi, _ = sg
        if o == 'h' and y < c < y + h and lo < x + w and hi > x and abs(c - (y + h / 2)) < 1:
            own = sg
        elif o == 'v' and x < c < x + w and lo < y + h and hi > y and abs(c - (x + w / 2)) < 1:
            own = sg
    for sg in segs:
        i, o, c, lo, hi, _ = sg
        if own is not None and i == own[0]:
            continue
        if (o == 'h' and y < c < y + h and lo < x + w and hi > x) or (o == 'v' and x < c < x + w and lo < y + h and hi > y):
            fail(f'label {k} at ({x:.0f},{y:.0f}) covers another path (path {i})')
    if own is None:
        fail(f'label {k} at ({x:.0f},{y:.0f}) is not centered on a straight stretch')
        continue
    i, o, c, lo, hi, _ = own
    pts = paths[i][0]
    a, b = (x, x + w) if o == 'h' else (y, y + h)
    first, last = (pts[0][0], pts[-1][0]) if o == 'h' else (pts[0][1], pts[-1][1])
    tail_here = (o == 'h' and abs(pts[0][1] - c) < .5 and lo - .5 <= pts[0][0] <= hi + .5) or (o == 'v' and abs(pts[0][0] - c) < .5 and lo - .5 <= pts[0][1] <= hi + .5)
    tip_here = (o == 'h' and abs(pts[-1][1] - c) < .5 and lo - .5 <= pts[-1][0] <= hi + .5) or (o == 'v' and abs(pts[-1][0] - c) < .5 and lo - .5 <= pts[-1][1] <= hi + .5)
    if tail_here or tip_here:
        # the stretch runs from the tail (or from its far end) to the base of the arrowhead (or to its far end);
        # "far end" is the end of the segment away from the box edge, whichever way the arrow points
        if tail_here:
            s0 = first
        else:
            s0 = hi if abs(last - lo) < .5 else lo
        if tip_here:
            s1 = last - 11 * (1 if abs(last - hi) < .5 else -1)   # shaft ends at the base of the arrowhead
        else:
            s1 = lo if abs(first - hi) < .5 else hi
        left, right = sorted((s0, s1))
        above, below = a - left, right - b
        if min(above, below) < 20:
            fail(f'label {k} at ({x:.0f},{y:.0f}) leaves {above:.0f}/{below:.0f}px of straight shaft (need 20)')
        if tail_here and tip_here and abs(above - below) > 12.5:
            fail(f'label {k} at ({x:.0f},{y:.0f}) is off center on its shaft: {above:.0f} vs {below:.0f}px')

# ---- crossings between plain paths (jumps are drawn with arcs, so arc paths are skipped)
plain = [s for s in segs if not s[5]]
cross = 0
for a in plain:
    for b in plain:
        if a[0] >= b[0] or a[1] == b[1]:
            continue
        h, v = (a, b) if a[1] == 'h' else (b, a)
        if h[3] < v[2] < h[4] and v[3] < h[2] < v[4]:
            cross += 1
            fail(f'unintended crossing of paths {a[0]} and {b[0]} near ({v[2]:.0f},{h[2]:.0f})')
print('plain crossings', cross)

# ---- parallel spacing closer than 13.5px
for a in segs:
    for b in segs:
        if a[0] >= b[0] or a[1] != b[1]:
            continue
        if min(a[4], b[4]) - max(a[3], b[3]) > 20 and 0.5 < abs(a[2] - b[2]) < 13.5:
            fail(f'parallel lines of paths {a[0]} and {b[0]} only {abs(a[2] - b[2]):.1f}px apart')

# ---- content
for n in sorted(boxes):
    if f'/issues/{n}"' not in new and f'/pull/{n}"' not in new:
        fail(f'#{n} has no link')
print('new pills', len(re.findall(r'rotate\(-45 ([\d.]+) ([\d.]+)\)', new)))
if old:
    ob = {int(m.group(1)) for m in re.finditer(r'<g id="n(\d+)">', old)}
    nb = {int(m.group(1)) for m in re.finditer(r'<g id="n(\d+)">', new)}
    if ob != nb:
        print('note: boxes added', sorted(nb - ob), 'removed', sorted(ob - nb))
cols = sorted({round(b[0]) for b in boxes.values()})
print('column gaps', [cols[i + 1] - cols[i] - 260 for i in range(len(cols) - 1)])
print('canvas', re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', new).groups())
print('FAILS', fails)
sys.exit(1 if fails else 0)
