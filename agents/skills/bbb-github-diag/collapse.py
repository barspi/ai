#!/usr/bin/env python3
"""Collapse boxes of a lineage SVG into one-line boxes with a hover pop-up, or expand them again. Local text edits, no gh.

usage: collapse.py in.svg out.svg [--set N=keywords]... [--spec spec.tsv] [--expand N,N|all]
                                  [--moves moves.json] [--shrink-frames] [--remove N,N] [--center] [--no-cue]

A collapsed box keeps the first line (kind, number link, name, pill, `new` pill) and ONE line of keywords; everything under the
separator is dropped from the box and kept in a pop-up (a full copy of the box, links included) shown on hover. The state lives
in the SVG: the first <rect> of a collapsed box carries data-collapsed="1" data-keywords="...". Collapse only on request.

  --set N=keywords   collapse box N with these keywords (one line, at most 232px at 12.5px; fewer words is better). On a box that
                     is already collapsed it only changes the keywords.
  --spec file.tsv    the same, one `N<TAB>keywords` per line
  --expand N,N|all   put the full box back (taken from its pop-up); arrows are not touched
  --moves file.json  {"boxes": {"123": 3251, ...}, "frames": {"frame title": {"y": 100, "h": 420}}}: new top y of boxes and new y/h of
                     dotted frames (plain title text). Use it for the second step, the rearrangement; this script does not decide a layout.
  --shrink-frames    pull the bottom edge of each frame up to its lowest box (+ the old bottom padding); nothing else moves
  --remove N,N       delete boxes (and their pop-ups) from the diagram; refused while an arrow still ends on one of them
  --center           a straight arrow between two collapsed boxes with the same top runs through their centres (default: it keeps its old height)
  --no-cue           leave out the small "..." at the bottom right of a collapsed box

Every arrow that ends on a collapsed or moved box is re-attached keeping its shape and its lanes; its label is put on a straight
stretch. Arrows between boxes that did not change are left byte for byte. A collapsed box gets taller when many arrows end on one
side (14px apart) or when a straight arrow must keep its height. Run check_diag.py afterwards.
"""
import json, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fonts import load
import hops, draw

HC = 62.0                # least height of a collapsed box
STEP = 14.0               # least distance between two arrows on one side of a box (the checker wants 14)
INNER = 232.0             # text width inside a box
POP_CSS = ('.pop{visibility:hidden;opacity:0;pointer-events:none;filter:drop-shadow(0 6px 12px rgba(0,0,0,.35))}')
MARK = ('/*collapse-begin*/', '/*collapse-end*/')
NOTE = ('<!-- collapsed boxes: data-collapsed and data-keywords on the first rect of a box group; run collapse.py again after an edit. '
        'Pop-ups (g id="popN") are siblings of the boxes and come before the script element: keep boxes and pop-ups direct children of the '
        'root, or the hover rule stops working. -->')
_font = load('regular', 50)


HC_TWO = 78.0            # least height of a collapsed box whose first line needed a second line (box_header.py)


def two_lines(grp):
    """Does this box group have a second `kind` text (the arrow and the name 13px lower)?"""
    return sum(1 for l in grp if l.startswith('<text class="kind"')) > 1


def tw(t, size=12.5):
    return _font.getlength(t) * size / 50


def fmt(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')


def esc(t):
    return t.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')


def shift_y_line(line, dy):
    if not dy:
        return line
    line = re.sub(r'\b(y|y1|y2)="(-?[\d.]+)"', lambda m: '%s="%s"' % (m.group(1), fmt(float(m.group(2)) + dy)), line)
    line = re.sub(r'points="([^"]*)"', lambda m: 'points="%s"' % re.sub(r'(-?[\d.]+),(-?[\d.]+)', lambda k: '%s,%s' % (k.group(1), fmt(float(k.group(2)) + dy)), m.group(1)), line)
    line = re.sub(r'rotate\(-45 ([\d.]+) ([\d.]+)\)', lambda m: 'rotate(-45 %s %s)' % (m.group(1), fmt(float(m.group(2)) + dy)), line)
    return line


def set_height(lines, n, h):
    """Give the collapsed box n the height h, in place: its rect, an umbrella's inner frame, a closed pull request's stripes and the
    "..." cue at the bottom. Used by build.py and fit_heights.py."""
    _, box, _, _ = parse('\n'.join(lines))
    b = box[n]
    a = b['a']
    lines[a + 1] = re.sub(r'height="[\d.]+"', 'height="%s"' % fmt(h), lines[a + 1], count=1)
    for k in range(a + 2, b['b'] + 1):
        if lines[k].startswith('<rect') and 'rx="7"' in lines[k]:
            lines[k] = re.sub(r'height="[\d.]+"', 'height="%s"' % fmt(h - 8), lines[k], count=1)
        elif lines[k].startswith('<rect') and 'url(#stripes' in lines[k]:
            lines[k] = re.sub(r'height="[\d.]+"', 'height="%s"' % fmt(h), lines[k], count=1)
        if '&#8230;' in lines[k]:
            lines[k] = re.sub(r' y="[\d.]+"', ' y="%s"' % fmt(b['y'] + h - 10), lines[k], count=1)


def group_end(lines, i):
    depth = 0
    for j in range(i, len(lines)):
        depth += lines[j].count('<g ') + lines[j].count('<g>') - lines[j].count('</g>')
        if depth == 0:
            return j
    raise ValueError('unclosed group at line %d' % i)


def parse(s):
    lines = s.split('\n')
    box, pop = {}, {}
    for i, ln in enumerate(lines):
        m = re.match(r'<g id="n(\d+)"(?: data-[\w-]+="[^"]*")*>$', ln)
        if m:
            j = group_end(lines, i)
            r = re.match(r'<rect x="([\d.]+)" y="([\d.]+)" width="(\d+)(?:\.0)?" height="([\d.]+)"([^>]*)/?>', lines[i + 1])
            box[int(m.group(1))] = dict(a=i, b=j, x=float(r.group(1)), y=float(r.group(2)), w=float(r.group(3)), h=float(r.group(4)),
                                       coll='data-collapsed="1"' in lines[i + 1])
        m = re.match(r'<g id="pop(\d+)" class="pop">$', ln)
        if m:
            pop[int(m.group(1))] = (i, group_end(lines, i))
    frame = []
    for i, ln in enumerate(lines):
        m = re.match(r'<rect x="([\d.-]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="18"[^>]*stroke-dasharray="2 6"', ln)
        if m and i + 1 < len(lines) and lines[i + 1].startswith('<text class="ftl"'):
            frame.append(dict(rl=i, tl=i + 1, x=float(m.group(1)), y=float(m.group(2)), w=float(m.group(3)), h=float(m.group(4)),
                              name=re.sub(r'<[^>]+>', '', lines[i + 1]).replace('&#8212;', '—')))
    return lines, box, pop, frame


def expand(s, nums):
    """Put the full box of every collapsed box in `nums` back, from its pop-up."""
    lines, box, pop, _ = parse(s)
    out = list(lines)
    for n in nums:
        if n not in box or not box[n]['coll']:
            continue
        pa, pb = pop[n]
        full = list(lines[pa:pb + 1])
        full[0] = lines[box[n]['a']]          # the box's own tag, with its attributes (svgmeta.py)
        b = box[n]
        out[b['a']] = '\n'.join(full)                      # one list item, so the other line numbers stay valid
        for k in range(b['a'] + 1, b['b'] + 1):
            out[k] = None
        for k in range(pa, pb + 1):
            out[k] = None
    return '\n'.join(l for l in out if l is not None)


def remove_boxes(s, nums):
    """Delete boxes (and their pop-ups). Refuses when an arrow still ends on one: remove or redraw the arrow first."""
    lines, box, pop, _ = parse(s)
    out = list(lines)
    for n in nums:
        if n not in box:
            sys.exit('no box #%d' % n)
        b = box[n]
        for ln in lines:
            if ln.startswith('<path d="M') and 'marker-end' in ln:
                pts = [(float(a), float(c)) for a, c in re.findall(r'(-?[\d.]+),(-?[\d.]+)', re.sub(r'A[^L]*', '', ln.split('"')[1]))]
                for px, py in (pts[0], pts[-1]):
                    if b['x'] - 3 <= px <= b['x'] + b['w'] + 3 and b['y'] - 3 <= py <= b['y'] + b['h'] + 3:
                        sys.exit('an arrow still ends on #%d: remove or redraw it first' % n)
        for k in range(b['a'], b['b'] + 1):
            out[k] = None
        if n in pop:
            for k in range(pop[n][0], pop[n][1] + 1):
                out[k] = None
    rule = re.compile(r'#n(%s):hover~#pop\1,#pop\1:hover\{[^}]*\}' % '|'.join(str(n) for n in nums))
    out = [rule.sub('', l) if l is not None and '<style>' in l else l for l in out]     # their hover rules go too
    return '\n'.join(l for l in out if l is not None)


def process(s, sets, moves=None, shrink_frames=False, cue=True, expand_nums=(), remove=(), center_pairs=False):
    log = []
    if remove:
        s = remove_boxes(s, remove)
        log += ['removed #%d' % n for n in remove]
    lines0, box0, pop0, _ = parse(s)
    if expand_nums == 'all':
        expand_nums = [n for n, b in box0.items() if b['coll']]
    redo = [n for n in sets if n in box0 and box0[n]['coll']]                  # new keywords on a collapsed box: expand, then collapse again
    s = expand(s, set(expand_nums) | set(redo))
    lines, BOX, POP, FRAME = parse(s)
    for n in sets:
        if n not in BOX:
            sys.exit('no box #%d' % n)
    COLL = {n: kw for n, kw in sets.items()}
    for n, b in BOX.items():                                                    # boxes collapsed by an earlier run stay collapsed
        if b['coll'] and n not in COLL:
            m = re.search(r'data-keywords="([^"]*)"', lines[b['a'] + 1])
            COLL[n] = m.group(1).replace('&quot;', '"').replace('&lt;', '<').replace('&amp;', '&')
    for n, kw in COLL.items():
        if tw(kw) > INNER:
            sys.exit('keywords of #%d are %.0fpx wide (limit %.0f): shorten them' % (n, tw(kw), INNER))
    new_coll = {n for n in COLL if not BOX[n]['coll']}

    PATH = []
    for i, ln in enumerate(lines):
        if ln.startswith('<path d="M') and 'marker-end' in ln:
            d = ln.split('"')[1]
            pts = [(float(a), float(b)) for a, b in re.findall(r'(-?[\d.]+),(-?[\d.]+)', re.sub(r'A[^L]*', '', d))]
            PATH.append(dict(i=i, pts=pts, d=d, arc=' A' in d, line=ln))
    LABEL = []
    for i, ln in enumerate(lines):
        lab = draw.label_at(lines, i)                    # a label of any height: one text line, or two such as "evidence, / does not close"
        if lab:
            x, y, w, h = lab[:4]
            LABEL.append(dict(i=i, cx=x + w / 2, cy=y + h / 2, w=w, line=ln))

    def attach(p, tol=3.0):
        px, py = p
        for n, b in BOX.items():
            x, y, w, h = b['x'], b['y'], b['w'], b['h']
            if y - tol <= py <= y + h + tol:
                if abs(px - x) <= tol:
                    return n, 'L'
                if abs(px - (x + w)) <= tol:
                    return n, 'R'
            if x - tol <= px <= x + w + tol:
                if abs(py - y) <= tol:
                    return n, 'T'
                if abs(py - (y + h)) <= tol:
                    return n, 'B'
        return None, None

    for p in PATH:
        p['s'], p['e'] = attach(p['pts'][0]), attach(p['pts'][-1])

    # ---- positions
    NEWY = {n: b['y'] for n, b in BOX.items()}
    for n, y in ((moves or {}).get('boxes') or {}).items():
        NEWY[int(n)] = float(y)
    DY = {n: NEWY[n] - BOX[n]['y'] for n in BOX}

    def fixed_y(k, e, n):
        """New y a straight arrow keeps on collapsed box n (its end e), or None."""
        p = PATH[k]
        if len(p['pts']) != 2 or abs(p['pts'][0][1] - p['pts'][1][1]) > .01:
            return None
        on, _side = p['e'] if e == 0 else p['s']
        if on is None:
            return None
        oy = p['pts'][0][1]
        if on in COLL:
            if center_pairs and abs(NEWY[n] - NEWY[on]) < .01:               # two collapsed boxes with the same top: through their centres
                return NEWY[n] + HC / 2
            return oy + DY[n] if abs(DY[n] - DY[on]) < .01 else None
        return oy + DY[on]

    NEWH = {n: b['h'] for n, b in BOX.items()}

    def side_slots(n, side, h):
        """New y of every arrow end on (box n, side L/R) for a box h tall: ({(k, e): y}, ok). ok: spacing and margins hold and every straight arrow keeps its height."""
        ends = [(k, e) for k, p in enumerate(PATH) for e, key in ((0, 's'), (1, 'e')) if p[key] == (n, side)]
        y = NEWY[n]
        if n not in COLL:
            return {(k, e): PATH[k]['pts'][0 if e == 0 else -1][1] + DY[n] for k, e in ends}, True
        ends.sort(key=lambda ke: PATH[ke[0]]['pts'][0 if ke[1] == 0 else -1][1])
        cnt = len(ends)
        ideal = [y + h / 2 + (i - (cnt - 1) / 2) * STEP for i in range(cnt)]
        fixed, want_fixed = [None] * cnt, True
        for i, (k, e) in enumerate(ends):
            fy = fixed_y(k, e, n)
            if fy is not None and fy >= y + 8:
                if fy <= y + h - 8:
                    fixed[i] = fy
                else:
                    want_fixed = False                                    # the box is too short for this straight arrow
        ys = [fixed[i] if fixed[i] is not None else ideal[i] for i in range(cnt)]
        for _ in range(3):
            for i in range(cnt):
                if fixed[i] is not None:
                    continue
                lo = ys[i - 1] + STEP if i > 0 else y + 8
                hi = ys[i + 1] - STEP if i + 1 < cnt else y + h - 8
                ys[i] = min(max(ideal[i], lo), max(lo, hi)) if lo <= hi else (lo + hi) / 2
        ok = want_fixed and all(y + 8 - .01 <= v <= y + h - 8 + .01 for v in ys) and all(ys[i + 1] - ys[i] >= STEP - .01 for i in range(cnt - 1))
        return {ends[i]: ys[i] for i in range(cnt)}, ok

    for n in COLL:
        h = HC_TWO if two_lines(lines[BOX[n]['a']:BOX[n]['b'] + 1]) else HC
        while h < 600 and not all(side_slots(n, side, h)[1] for side in 'LR'):
            h += 1
        NEWH[n] = float(h)

    SLOT = {}
    for n in BOX:
        changed = n in COLL or abs(DY[n]) > .01
        if not changed:
            continue
        for side in 'LR':
            SLOT.update({(n, side) + ke: v for ke, v in side_slots(n, side, NEWH[n])[0].items()})

    def end_xy(p, k, e):
        n, side = p['s'] if e == 0 else p['e']
        ox, oy = p['pts'][0 if e == 0 else -1]
        if n is None:
            return ox, oy
        if side in 'LR':
            return ox, SLOT.get((n, side, k, e), oy + DY.get(n, 0.0))
        if side == 'T':
            return ox, NEWY[n]
        return ox, NEWY[n] + NEWH[n]

    def rebuild(k, p):
        pts, n = p['pts'], len(p['pts'])
        s_new, e_new = end_xy(p, k, 0), end_xy(p, k, 1)
        if p['arc']:
            if abs((s_new[1] - pts[0][1]) - (e_new[1] - pts[-1][1])) > .5:
                log.append('NOTE arrow with a jump arc ends on boxes that moved differently: redraw it by hand near (%d,%d)' % pts[0])
            dy = s_new[1] - pts[0][1]
            return re.sub(r'(-?[\d.]+),(-?[\d.]+)', lambda m: '%s,%s' % (m.group(1), fmt(float(m.group(2)) + dy)), p['d']), [(a, b + dy) for a, b in pts]
        seg_h = [abs(pts[i][1] - pts[i + 1][1]) < .01 for i in range(n - 1)]
        ny = [None] * n
        ny[0], ny[-1] = s_new[1], e_new[1]
        if n == 2:
            if seg_h[0] and abs(ny[0] - ny[1]) > .01:                      # a straight arrow whose ends no longer line up: an elbow
                xm = (pts[0][0] + pts[1][0]) / 2
                return None, [(pts[0][0], ny[0]), (xm, ny[0]), (xm, ny[1]), (pts[1][0], ny[1])]
            return None, [(pts[0][0], ny[0]), (pts[1][0], ny[1])]
        for i in range(1, n):
            if seg_h[i - 1] and ny[i - 1] is not None and ny[i] is None:
                ny[i] = ny[i - 1]
        for i in range(n - 2, -1, -1):
            if seg_h[i] and ny[i + 1] is not None and ny[i] is None:
                ny[i] = ny[i + 1]
        for i in range(n):
            if ny[i] is None:
                near_start = abs(pts[i][1] - pts[0][1]) <= abs(pts[i][1] - pts[-1][1])
                ny[i] = pts[i][1] + ((s_new[1] - pts[0][1]) if near_start else (e_new[1] - pts[-1][1]))
        out = []
        for q in zip([a for a, _ in pts], ny):
            if not out or abs(q[0] - out[-1][0]) > .01 or abs(q[1] - out[-1][1]) > .01:
                out.append(q)
        return None, out

    def seg_dist(a, b, c):
        if abs(a[1] - b[1]) < .01:
            return abs(c[1] - a[1]) + max(0, min(a[0], b[0]) - c[0], c[0] - max(a[0], b[0]))
        return abs(c[0] - a[0]) + max(0, min(a[1], b[1]) - c[1], c[1] - max(a[1], b[1]))

    def place_label(newpts, old_pts, oc, lw, shift):
        cands, last = [], len(newpts) - 2
        for i in range(len(newpts) - 1):
            a, b = newpts[i], newpts[i + 1]
            horiz = abs(a[1] - b[1]) < .01
            ln = abs(a[0] - b[0]) + abs(a[1] - b[1])
            if horiz:
                lo, hi = min(a[0], b[0]), max(a[0], b[0])
                if i == last:
                    if b[0] < a[0]:
                        lo += 11
                    else:
                        hi -= 11
                cands.append((hi - lo >= lw + 40, ln, ((lo + hi) / 2, a[1])))
            else:
                lo, hi = min(a[1], b[1]), max(a[1], b[1])
                if i == last:
                    if b[1] > a[1]:
                        hi -= 11
                    else:
                        lo += 11
                cands.append((ln >= 80, ln, (a[0], (lo + hi) / 2)))
        if len(newpts) == len(old_pts):                                         # same shape: keep the label on the same stretch if it fits
            oi = min(range(len(old_pts) - 1), key=lambda i: seg_dist(old_pts[i], old_pts[i + 1], oc))
            if cands[oi][0]:
                return cands[oi][2], True
        ok = [c for c in cands if c[0]]
        best = min(ok or cands, key=lambda c: abs(c[2][0] - oc[0] - shift[0]) + abs(c[2][1] - oc[1] - shift[1]) - 0.2 * c[1])
        return best[2], bool(ok)

    # ---- label to path
    lab_of = {}
    for li, L in enumerate(LABEL):
        best = None
        for k, p in enumerate(PATH):
            for a, b in zip(p['pts'], p['pts'][1:]):
                if abs(a[1] - b[1]) < .01:
                    dist = abs(L['cy'] - a[1]) if min(a[0], b[0]) - 1 <= L['cx'] <= max(a[0], b[0]) + 1 else 1e9
                else:
                    dist = abs(L['cx'] - a[0]) if min(a[1], b[1]) - 1 <= L['cy'] <= max(a[1], b[1]) + 1 else 1e9
                if dist < 2 and (best is None or dist < best[0]):
                    best = (dist, k)
        if best:
            lab_of.setdefault(best[1], li)

    out = list(lines)
    # ---- pop-ups already in the file (boxes collapsed by an earlier run)
    pops = {}
    for n, (pa, pb) in POP.items():
        pops[n] = [shift_y_line(l, DY.get(n, 0.0)) for l in lines[pa:pb + 1]]
        for k in range(pa, pb + 1):
            out[k] = None
    # ---- boxes
    for n, b in BOX.items():
        grp = lines[b['a']:b['b'] + 1]
        dy = DY[n]
        if n not in COLL:
            if dy:
                out[b['a']:b['b'] + 1] = [shift_y_line(l, dy) for l in grp]
            continue
        if b['coll']:                                                           # already collapsed, unchanged keywords: only move it
            if dy:
                out[b['a']:b['b'] + 1] = [shift_y_line(l, dy) for l in grp]
            continue
        keep, k = [], 0
        while k < len(grp) and 'class="ttl"' not in grp[k]:
            keep.append(grp[k])
            k += 1
        rest = grp[k:]
        pill = []
        for q, l in enumerate(rest):
            if l.startswith('<g transform="rotate(-45'):
                pill = rest[q:]
                break
        kw = COLL[n]
        keep[1] = re.sub(r'height="[\d.]+"', 'height="%s"' % fmt(NEWH[n]), keep[1], count=1)
        keep[1] = keep[1].replace('/>', ' data-collapsed="1" data-keywords="%s"/>' % esc(kw), 1)
        keep = [re.sub(r'height="[\d.]+"', 'height="%s"' % fmt(NEWH[n] - 8), l, count=1) if 'rx="7"' in l and l.startswith('<rect') else l for l in keep]   # an umbrella's inner frame
        full_title = re.sub(r'<[^>]+>', '', ' '.join(re.findall(r'class="ttl"[^>]*>(.*?)</text>', '\n'.join(grp))))
        keep = [re.sub(r'height="[\d.]+"', 'height="%s"' % fmt(NEWH[n]), l, count=1) if 'url(#stripes' in l else l for l in keep]      # the red stripes of a closed pull request
        kw_y = 64 if two_lines(grp) else 51                                      # a second kind line (a long name) pushes the keywords down
        keep.append('<text class="ttl" x="%s" y="%s">%s</text>' % (fmt(b['x'] + 14), fmt(b['y'] + kw_y), kw.replace('&', '&amp;').replace('<', '&lt;')))
        if cue:
            keep.append('<text class="meta" x="%s" y="%s" text-anchor="end" style="fill:#8d877e;font-size:12px">&#8230;</text>' % (fmt(b['x'] + 248), fmt(b['y'] + NEWH[n] - 10)))
        keep.append('<title>%s</title>' % full_title)                           # a native tooltip where there is no hover (already escaped)
        keep += pill if pill else ['</g>']
        out[b['a']:b['b'] + 1] = [shift_y_line(l, dy) for l in keep] + [None] * (len(grp) - len(keep))
        full = [shift_y_line(l, dy) for l in grp]
        full[0] = '<g id="pop%d" class="pop">' % n
        pops[n] = full
    # ---- frames
    FN = {}
    if moves:
        FN.update({k: v for k, v in (moves.get('frames') or {}).items()})
    if shrink_frames:
        for f in FRAME:
            inside = [n for n, b in BOX.items() if f['x'] <= b['x'] and b['x'] + b['w'] <= f['x'] + f['w'] and f['y'] <= b['y'] and b['y'] + b['h'] <= f['y'] + f['h']]
            if inside and f['name'] not in FN:
                pad = f['y'] + f['h'] - max(BOX[n]['y'] + BOX[n]['h'] for n in inside)
                h = max(NEWY[n] + NEWH[n] for n in inside) + pad - f['y']
                if h < f['h'] - 1:
                    FN[f['name']] = {'y': f['y'], 'h': h}
    fbottom = []
    for f in FRAME:
        v = FN.get(f['name'])
        y, h = (float(v.get('y', f['y'])), float(v.get('h', f['h']))) if v else (f['y'], f['h'])
        fbottom.append(y + h)
        if v:
            out[f['rl']] = re.sub(r'y="[\d.]+" width="([\d.]+)" height="[\d.]+"', lambda m: 'y="%s" width="%s" height="%s"' % (fmt(y), m.group(1), fmt(h)), lines[f['rl']], count=1)
            ty = float(re.search(r'y="([\d.]+)"', lines[f['tl']]).group(1))
            out[f['tl']] = re.sub(r'y="[\d.]+"', 'y="%s"' % fmt(y + ty - f['y']), lines[f['tl']], count=1)
    # ---- arrows and labels: only those that end on a box that changed
    for k, p in enumerate(PATH):
        if p['s'][0] is None or p['e'][0] is None:
            continue
        if not any(n in COLL or abs(DY[n]) > .01 for n in (p['s'][0], p['e'][0])):
            continue
        d, newpts = rebuild(k, p)
        if d is None:
            d = 'M' + ' L'.join('%s,%s' % (fmt(a), fmt(b)) for a, b in newpts)
        out[p['i']] = p['line'].replace('d="%s"' % p['d'], 'd="%s"' % d)
        li = lab_of.get(k)
        if li is None:
            continue
        L = LABEL[li]
        d0 = abs(L['cy'] - p['pts'][0][1]) + abs(L['cx'] - p['pts'][0][0])
        d1 = abs(L['cy'] - p['pts'][-1][1]) + abs(L['cx'] - p['pts'][-1][0])
        sh = (0.0, (newpts[0][1] - p['pts'][0][1]) if d0 <= d1 else (newpts[-1][1] - p['pts'][-1][1]))
        c, ok = place_label(newpts, p['pts'], (L['cx'], L['cy']), L['w'], sh)
        if not ok:
            log.append('NOTE no straight stretch long enough for a label near (%d,%d): move a box or redraw that arrow' % c)
        draw.move_label(out, L['i'], c[0], c[1])         # the rectangle and all its text lines move together

    res = '\n'.join(l for l in out if l is not None)
    # ---- canvas
    if moves or shrink_frames:
        bottom = max(fbottom + [NEWY[n] + NEWH[n] for n in BOX])
        m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)" viewBox="0 0 (\d+) (\d+)"', res)
        H = int(bottom + 80)
        if m and H != int(m.group(2)):
            res = res.replace('height="%s" viewBox="0 0 %s %s"' % (m.group(2), m.group(3), m.group(4)), 'height="%d" viewBox="0 0 %s %d"' % (H, m.group(3), H), 1)
            res = re.sub(r'(<rect x="0" y="0" width="[\d.]+" height=")%s(" fill="#[0-9a-f]{6}"/>)' % m.group(2), lambda q: q.group(1) + str(H) + q.group(2), res, count=1)
    # ---- CSS (rewritten every run) and the pop-up layer (before the <script>: the find box moves every node that exists when it runs)
    res = re.sub(re.escape(MARK[0]) + '.*?' + re.escape(MARK[1]), '', res, flags=re.S)
    res = res.replace(NOTE + '\n', '')
    coll_now = sorted(n for n in COLL)
    if coll_now:
        css = MARK[0] + POP_CSS + ''.join('#n%d:hover~#pop%d,#pop%d:hover{visibility:visible;opacity:1;pointer-events:auto}' % (n, n, n) for n in coll_now) + MARK[1]
        res = res.replace('</style>', css + '</style>', 1)
        layer = NOTE + '\n' + '\n'.join('\n'.join(pops[n]) for n in coll_now) + '\n'
        if '<script' in res:
            res = res.replace('<script', layer + '<script', 1)
        else:
            res = res.replace('</svg>', layer + '</svg>', 1)
    for n in sorted(new_coll):
        log.append('collapsed #%d: %s (%.0fpx tall)' % (n, COLL[n], NEWH[n]))
    for n in sorted(set(expand_nums)):
        log.append('expanded #%d' % n)
    return res, log


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0].startswith('--'):
        sys.exit(__doc__)
    src, dst = args[0], args[1]
    sets, moves, shrink, cue, exp, rem, center = {}, None, False, True, (), (), False
    i = 2
    while i < len(args):
        a = args[i]
        if a == '--set':
            n, kw = args[i + 1].split('=', 1)
            sets[int(n)] = kw
            i += 2
        elif a == '--spec':
            for line in open(args[i + 1], encoding='utf-8'):
                if line.strip() and not line.startswith('#'):
                    n, kw = line.rstrip('\n').split('\t', 1)
                    sets[int(n)] = kw
            i += 2
        elif a == '--expand':
            exp = 'all' if args[i + 1] == 'all' else [int(v) for v in args[i + 1].split(',')]
            i += 2
        elif a == '--remove':
            rem = [int(v) for v in args[i + 1].split(',')]
            i += 2
        elif a == '--moves':
            moves = json.load(open(args[i + 1], encoding='utf-8'))
            i += 2
        elif a == '--shrink-frames':
            shrink = True
            i += 1
        elif a == '--center':
            center = True
            i += 1
        elif a == '--no-cue':
            cue = False
            i += 1
        else:
            sys.exit('unknown option ' + a)
    s = open(src, encoding='utf-8').read()
    res, log = process(s, sets, moves, shrink, cue, exp, rem, center)
    res, hops_added, hops_removed = hops.add_hops(res)                  # arrows were re-attached: redo the jump arcs of the whole diagram
    log.append('jump arcs: %d added, %d stale removed' % (hops_added, hops_removed))
    open(dst, 'w', encoding='utf-8').write(res)
    print('\n'.join(log) or 'nothing to do')
    print('wrote', dst)


if __name__ == '__main__':
    main()
