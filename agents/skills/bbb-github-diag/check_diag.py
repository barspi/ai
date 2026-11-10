#!/usr/bin/env python3
"""Geometry, text and content checks for an issue/PR lineage SVG. No rendering.
usage: check_diag.py new.svg [old.svg] [--keep-new]
With old.svg (the frozen previous revision) the `new` pills must be on exactly the boxes added since; with --keep-new, also on the
boxes that had one in old.svg.
Exit code 1 when a check fails. Checks the SVG text and path geometry only."""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')   # keep the compiled fonts.py out of the skill folder
import xml.dom.minidom as md
from fonts import load      # finds Helvetica/Arial/Liberation/DejaVu and Menlo/Consolas/... on macOS, Linux and Windows

_files = [a for a in sys.argv[1:] if not a.startswith('--')]
new = open(_files[0], encoding='utf-8').read()
old = open(_files[1], encoding='utf-8').read() if len(_files) > 1 else None
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
    r'<g id="n(\d+)"(?: data-[\w-]+="[^"]*")*>\s*<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', new)}
labels, shifts = [], []          # each label as drawn; and its shift when it is drawn beside its shaft (draw.label shift), else None
for m in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="4" fill="#fffdf7"[^>]*>', new):
    sh = re.search(r' transform="translate\(([-\d.]+),([-\d.]+)\)"', m.group(0))
    sh = (float(sh.group(1)), float(sh.group(2))) if sh else None
    x, y, w, h = (float(v) for v in m.groups())
    labels.append((x + sh[0], y + sh[1], w, h) if sh else (x, y, w, h))
    shifts.append(sh)
paths = []
for m in re.finditer(r'<path d="M([^"]+)" fill="none"', new):
    d = m.group(1)
    pts = [(float(a), float(b)) for a, b in re.findall(r'(-?\d+\.?\d*),(-?\d+\.?\d*)', d)]
    paths.append((pts, 'A' in d))
frames = [tuple(float(v) for v in m.groups()) for m in re.finditer(
    r'<rect x="([\d.-]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="18" fill="#ffffff"', new)]
print(len(boxes), 'boxes', len(paths), 'paths', len(labels), 'labels', len(frames), 'frames')

# ---- dotted frames must not overlap each other (a frame that shrinks or moves can run into its neighbour)
for i, (ax, ay, aw, ah) in enumerate(frames):
    for (bx_, by_, bw_, bh_) in frames[i + 1:]:
        if ax < bx_ + bw_ - 1 and bx_ < ax + aw - 1 and ay < by_ + bh_ - 1 and by_ < ay + ah - 1:
            fail(f'frames at ({ax:.0f},{ay:.0f}) and ({bx_:.0f},{by_:.0f}) overlap')

# ---- no line on which way arrows run, in the header or the legend: each arrow reads as its label says (draw.set_header removes them)
if 'Arrows point from the earlier item' in new or 'Arrows run from the earlier item' in new:
    print('WARN the header or the legend still explains which way arrows run: refresh_meta.py --apply (or draw.set_header) removes it')

# ---- collapsed boxes: keywords fit on one line, the pop-up exists, sits at the same corner, comes before the script and is a sibling of its box
_tags = [(m.start(), m.group(0)) for m in re.finditer(r'<g[\s>]|</g>|<script', new)]
_depth, _d, _at = {}, 0, {}
for pos, tag in _tags:
    if tag.startswith('<g'):
        gid = re.match(r'<g id="((?:n|pop)\d+)"', new[pos:pos + 40])
        if gid:
            _depth[gid.group(1)] = _d
            _at[gid.group(1)] = pos
        _d += 1
    elif tag == '</g>':
        _d -= 1
_script = new.find('<script')
_coll = {int(m.group(1)): (float(m.group(2)), float(m.group(3)), m.group(4)) for m in re.finditer(
    r'<g id="n(\d+)"(?: data-[\w-]+="[^"]*")*>\s*<rect x="([\d.]+)" y="([\d.]+)"[^>]*data-collapsed="1" data-keywords="([^"]*)"', new)}
for n, (cx_, cy_, kw) in sorted(_coll.items()):
    kwt = kw.replace('&amp;', '&').replace('&quot;', '"').replace('&lt;', '<')
    if width('ttl', kwt) > 232:
        fail(f'keywords of collapsed #{n} are {width("ttl", kwt):.0f}px wide (limit 232): shorten them')
    pm = re.search(r'<g id="pop%d" class="pop">\s*<rect x="([\d.]+)" y="([\d.]+)"' % n, new)
    if not pm:
        fail(f'collapsed #{n} has no pop-up (g id="pop{n}")')
        continue
    if abs(float(pm.group(1)) - cx_) > .5 or abs(float(pm.group(2)) - cy_) > .5:
        fail(f'pop-up of #{n} is at ({pm.group(1)},{pm.group(2)}), not at the corner of its box ({cx_:.0f},{cy_:.0f})')
    if _script >= 0 and _at[f'pop{n}'] > _script:
        fail(f'pop-up of #{n} comes after the <script>: the find box script would leave it outside the drawing and the hover rule would never match')
    if _depth.get(f'pop{n}') != _depth.get(f'n{n}'):
        fail(f'pop-up of #{n} is not a sibling of its box (depth {_depth.get(f"pop{n}")} vs {_depth.get(f"n{n}")}): the hover rule needs siblings')
    if f'#n{n}:hover~#pop{n}' not in new:
        fail(f'no hover rule for the pop-up of #{n}')
    _bm = re.search(r'<g id="n%d"(?: data-[\w-]+="[^"]*")*>' % n, new)
    if not _bm or '<title>' not in new[_bm.end():_bm.end() + 3000]:
        fail(f'collapsed #{n} has no <title> tooltip with its full title')
for pm in re.finditer(r'<g id="pop(\d+)" class="pop">', new):
    if int(pm.group(1)) not in _coll:
        fail(f'pop-up pop{pm.group(1)} has no collapsed box')
for rm in re.finditer(r'#n(\d+):hover~#pop(\d+)', new):
    if rm.group(1) != rm.group(2) or int(rm.group(1)) not in _coll:
        fail(f'hover rule {rm.group(0)} matches no collapsed box with its pop-up')
# SVG has no z-index: what comes later in the file is painted on top. The pop-ups must come after every box, arrow, label, cross
# and the legend, or that part covers the open pop-up. After the first pop-up only pop-ups (and the find box script) may follow.
_first_pop = new.find('<g id="pop')
if _coll and _first_pop >= 0:
    if not re.search(r'\.pop\{visibility:hidden;opacity:0;pointer-events:none', new):
        fail('the CSS rule that hides the pop-ups (.pop{visibility:hidden;opacity:0;pointer-events:none...}) is missing')
    _end = _script if _script >= 0 else new.rfind('</svg>')
    _tail = re.sub(r'<g id="pop\d+" class="pop">.*?\n</g>', '', new[_first_pop:_end], flags=re.S)   # a pop-up ends with "</g>" on its own line
    _left = re.findall(r'<(?:g|path|rect|text|line|circle|polyline|polygon|use|image)\b[^>]{0,60}', _tail)
    if _left:
        fail(f'{len(_left)} drawn element(s) come after the first pop-up and paint over the open pop-ups (first: {_left[0][:60]!r}); '
             'move them before the pop-ups')
if _coll:
    print(len(_coll), 'collapsed boxes')

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

# ---- the first line (tag, number, arrow, name) is one kind text (box_header.py): it must end before the pill (6px) and the red cross (12px);
#      a second kind text (the arrow and the name on their own line) must end inside the box
import box_header
for n, (bx, by, bw, bh) in boxes.items():
    g = re.search(r'<g id="n%d"(?: data-[\w-]+="[^"]*")*>(.*?)</g>' % n, new, re.S).group(1)
    texts = list(box_header.KIND_TEXT.finditer(g))
    if not texts or box_header.who_of(g) is None:
        continue
    pill = re.search(r'<rect x="([\d.]+)" y="[\d.]+" width="[\d.]+" height="20" rx="10"', g)
    cross = re.search(r'<line x1="([\d.]+)"[^>]*stroke="#ff2a2a"', g)
    if not pill:
        continue
    limit = float(cross.group(1)) - 12 if cross else float(pill.group(1)) - 6
    for i, t in enumerate(texts):
        end = float(t.group(1)) + box_header.text_width(t.group(4))
        lim = limit if i == 0 else bx + bw - 12
        if end > lim + 0.5:
            fail(f'first line of #{n} ends at {end:.0f}, past {lim:.0f} ({"pill or cross" if i == 0 else "box edge"}): shorten the login or put the arrow and name on a second line')

# ---- old form (a separate name text and arrow polyline): the name must not run into the pill or the red cross, and must be at least 9px
for n, (bx, by, bw, bh) in boxes.items():
    g = re.search(r'<g id="n%d"(?: data-[\w-]+="[^"]*")*>(.*?)</g>' % n, new, re.S).group(1)
    k = re.search(r'<text class="kind" x="([\d.]+)" y="([\d.]+)"', g)
    nm = re.search(r'<text class="meta" x="([\d.]+)" y="([\d.]+)" style="[^"]*font-size:([\d.]+)px[^"]*">([^<]*)</text>', g)
    pill = re.search(r'<rect x="([\d.]+)" y="[\d.]+" width="[\d.]+" height="20" rx="10"', g)
    if not (k and nm and pill):
        continue
    x, y, size, text = float(nm.group(1)), float(nm.group(2)), float(nm.group(3)), nm.group(4)
    if x < bx + 10:
        fail(f'name "{text}" in #{n} starts at {x:.0f}, left of the box text column (box x {bx:.0f})')
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

for i, (pts, arcs) in enumerate(paths):  # arrow tails touch a box edge too (an exit that falls below its box is a defect)
    px, py = pts[0]
    ok = any((abs(px - bx) < 1.5 or abs(px - (bx + bw)) < 1.5) and by - 1 <= py <= by + bh + 1 or
             (abs(py - by) < 1.5 or abs(py - (by + bh)) < 1.5) and bx - 1 <= px <= bx + bw + 1
             for (bx, by, bw, bh) in boxes.values())
    if not ok:
        fail(f'path {i} tail ({px},{py}) does not touch a box')

for sg in segs:
    for n, r in boxes.items():
        if seg_in_box(sg, r):
            fail(f'path {sg[0]} runs through box #{n}')

# ---- a jog (a short segment between two bends) shorter than 30px reads as a glitch; a straight arrow or a longer jog is fine
for i, (pts, arcs) in enumerate(paths):
    if arcs:
        continue
    for k in range(1, len(pts) - 2):
        d = abs(pts[k + 1][0] - pts[k][0]) + abs(pts[k + 1][1] - pts[k][1])
        if 0.5 < d < 30 and k >= 1:
            print(f'WARN path {i} has a {d:.0f}px jog near ({pts[k][0]:.0f},{pts[k][1]:.0f}): make it straight or 30px or more')   # a warning: the rule says about 30px

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
    sx, sy = (x - shifts[k][0], y - shifts[k][1]) if shifts[k] else (x, y)      # a label beside its shaft: its place on the shaft
    for sg in segs:
        i, o, c, lo, hi, _ = sg
        if o == 'h' and sy < c < sy + h and lo < sx + w and hi > sx and abs(c - (sy + h / 2)) < 1:
            own = sg
        elif o == 'v' and sx < c < sx + w and lo < sy + h and hi > sy and abs(c - (sx + w / 2)) < 1:
            own = sg
    for sg in segs:
        i, o, c, lo, hi, _ = sg
        if own is not None and i == own[0] and not shifts[k]:       # a label beside its shaft covers no line, its own included
            continue
        if (o == 'h' and y < c < y + h and lo < x + w and hi > x) or (o == 'v' and x < c < x + w and lo < y + h and hi > y):
            fail(f'label {k} at ({x:.0f},{y:.0f}) covers another path (path {i})')
    if own is None:
        fail(f'label {k} at ({x:.0f},{y:.0f}) is not centered on a straight stretch')
        continue
    if shifts[k]:
        if (abs(shifts[k][0]) > w / 2 + 12) or (abs(shifts[k][1]) > h / 2 + 12):
            fail(f'label {k} at ({x:.0f},{y:.0f}) is drawn more than 12px beside its shaft')
        continue                                                     # beside a short shaft: the 20px shaft rule does not apply
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
    ob = {int(m.group(1)) for m in re.finditer(r'<g id="n(\d+)"(?: data-[\w-]+="[^"]*")*>', old)}
    nb = {int(m.group(1)) for m in re.finditer(r'<g id="n(\d+)"(?: data-[\w-]+="[^"]*")*>', new)}
    if ob != nb:
        print('note: boxes added', sorted(nb - ob), 'removed', sorted(ob - nb))

    def pill_boxes(text, bx):
        got = set()
        for m in re.finditer(r'rotate\(-45 ([\d.]+) ([\d.]+)\)', text):
            for n, (px, py, pw_, ph_) in bx.items():
                if abs(float(m.group(1)) - (px + 3)) < 2 and abs(float(m.group(2)) - (py + 3)) < 2:
                    got.add(n)
        return got
    old_boxes = {int(m.group(1)): tuple(float(v) for v in m.groups()[1:]) for m in re.finditer(r'<g id="n(\d+)"(?: data-[\w-]+="[^"]*")*>\s*<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', old)}
    have, kept = pill_boxes(new, boxes), pill_boxes(old, old_boxes)
    added = nb - ob
    if '--keep-new' in sys.argv:                  # the user asked to keep the old pills: the pills of the old file stay, and every added box has one
        if not (added <= have and have <= added | kept):
            fail(f'new pills on {sorted(have)}: expected the added boxes {sorted(added)} plus the kept ones {sorted(kept)}')
    elif have != added:
        fail(f'new pills on {sorted(have)}, but the boxes added since the previous revision are {sorted(added)} (run new_revision.py, or use --keep-new when the user asked to keep the pills)')
cols = sorted({round(b[0]) for b in boxes.values()})
print('column gaps', [cols[i + 1] - cols[i] - 260 for i in range(len(cols) - 1)])
print('canvas', re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', new).groups())
_w, _h = (int(v) for v in re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', new).groups())
if _h >= 2 * _w or _w >= 2 * _h:
    print('NOTE aspect %.1f:1 (%s): ask the user about the layout before going on' % (max(_w, _h) / min(_w, _h), 'tall' if _h > _w else 'wide'))
# ---- largest empty rectangle (boxes, frames and the legend count as occupied), 10px grid
cw, ch = (int(v) for v in re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', new).groups())
occ = list(boxes.values()) + frames + [tuple(float(v) for v in m.groups()) for m in re.finditer(
    r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="14" fill="#fbfaf6"', new)]
G = 10
cols, rows_ = cw // G, ch // G
grid = [[0] * cols for _ in range(rows_)]
for (ox, oy, ow, oh) in occ:
    for gy in range(max(0, int(oy // G)), min(rows_, int((oy + oh) // G) + 1)):
        for gx in range(max(0, int(ox // G)), min(cols, int((ox + ow) // G) + 1)):
            grid[gy][gx] = 1
top = min(oy for (_ox, oy, _ow, _oh) in occ)      # the title and header lines sit above the first box or frame
for gy in range(min(rows_, int(top // G))):
    grid[gy] = [1] * cols
best, heights = (0, 0, 0, 0), [0] * cols
for gy in range(rows_):
    heights = [0 if grid[gy][gx] else heights[gx] + 1 for gx in range(cols)]
    stack = []
    for gx in range(cols + 1):
        h = heights[gx] if gx < cols else 0
        start = gx
        while stack and stack[-1][1] >= h:
            sx, sh = stack.pop()
            area = sh * (gx - sx)
            if area > best[0]:
                best = (area, sx, gy - sh + 1, (gx - sx, sh))
            start = sx
        stack.append((start, h))
_lg = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="14" fill="#fbfaf6"', new)
if _lg:
    _lx, _ly, _lw, _lh = (float(v) for v in _lg.groups())
    _right = max(bx + bw for (bx, by, bw, bh) in list(boxes.values()) + frames)       # the farthest right edge of the nodes
    if _ly > 300 or _lx + _lw < _right - 20:
        print(f'WARN legend right edge {_lx + _lw:.0f} (top {_ly:.0f}) should be in the top row and reach the farthest right node edge {_right:.0f}: move it to the top right of the chart')
if best[0]:
    print(f'largest empty rectangle {best[3][0] * G}x{best[3][1] * G}px at ({best[1] * G},{best[2] * G})')
# ---- what the file keeps about itself (svgmeta.py): each box's frame and GitHub record, each arrow's two boxes and kind, the block
import svgmeta
for _lvl, _msg in svgmeta.problems(new):
    if _lvl == 'error':
        fail('metadata: ' + _msg)
    else:
        print('WARN metadata: ' + _msg)
# ---- a "Blocked by" line names ONE blocker; it is bold while the box and that blocker are open, struck once either is closed
#      (rules.blocked_notes; refresh_meta.py --apply rewrites them). The states come from the records the file keeps.
import svg_state as _ss
_recs = {n: (r.get('github') or {}) for n, r in svgmeta.boxes(new).items()}
_is_open = lambda n: (_recs[n]['state'] in ('open', 'draft')) if _recs.get(n, {}).get('state') else None
for _pop in (False, True):
    for _n, (_a, _b) in _ss.blocks(new, _pop).items():
        for _m in _ss.NOTE_LINE.finditer(new[_a:_b]):
            _plain = _ss._plain(_m.group(3)).strip()
            if re.match(r'was blocked by\b', _plain, re.I):
                fail('#%d%s: "%s" is the old form: a block that is over is a struck "Blocked by" line (refresh_meta.py --apply)'
                     % (_n, ' (pop-up)' if _pop else '', _plain[:60]))
                continue
            if not re.match(r'blocked by\b', _plain, re.I):
                continue
            _clause = re.split(r'[(:]', _plain, 1)[0]
            _named = [int(x) for x in re.findall(r'#(\d+)', _clause)]
            _where = '#%d%s: "%s"' % (_n, ' (pop-up)' if _pop else '', _plain[:60])
            if len(_named) > 1:
                fail('%s names %d blockers: one line per blocker (refresh_meta.py --apply)' % (_where, len(_named)))
                continue
            _bold = re.search(r'font-weight:700">Blocked by', _m.group(3)) is not None
            _struck = re.search(r'line-through">Blocked by', _m.group(3)) is not None
            _holds = None if not _named or _is_open(_named[0]) is None or _is_open(_n) is None else (_is_open(_n) and _is_open(_named[0]))
            if _holds is None:
                continue
            if _holds and not _bold:
                fail('%s: the block holds (both open), so the line is bold (refresh_meta.py --apply)' % _where)
            elif not _holds and not _struck:
                fail('%s: the block is over (%s closed), so the line is struck, not bold (refresh_meta.py --apply)'
                     % (_where, 'the box' if not _is_open(_n) else '#%d' % _named[0]))
import reroute                                # an arrow between two boxes of one frame stays inside it (route.py; an almost hard rule)
for _a, _b in reroute.leaves_frame(new):
    fail('arrow #%d -> #%d leaves the frame its two boxes are in: reroute.py IN OUT %d>%d (or move a box)' % (_a, _b, _a, _b))
for _f in __import__('rules').far_low(new):      # a far low arrow from closed work is not drawn (rules.far_low)
    print('WARN far low arrow #%d %s #%d: %s; rules.py prune drops it into "nopath"' % _f)
import rules                                  # arrows a person should look at again: asked, never failed (rules.py review)
for _f in rules.review(new):
    print('ASK %s: %s' % (_f['check'], _f['message']))

print('FAILS', fails)
sys.exit(1 if fails else 0)
