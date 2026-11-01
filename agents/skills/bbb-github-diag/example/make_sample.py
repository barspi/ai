#!/usr/bin/env python3
"""Draws sample-lineage.svg: an invented repository (acme/shop, invented numbers, titles and people) that uses
every box state, every pill, the `new` mark and the main arrow words of the skill. It is both the picture to
copy the look from and a small build script to copy the code from (box, edge, legend, find box).
The people shown on each box are read from `assignees.tsv` and `prauthors.tsv` next to this file: the same two
files that `refresh_meta.py --tsv-dir` writes for a real diagram, so nobody types them by hand.

usage: python3 make_sample.py [out.svg]      (default: sample-lineage.svg next to this file)
then:  python3 ../check_diag.py sample-lineage.svg
"""
import os, re, sys, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from fonts import load          # a Helvetica-like font on macOS, Linux or Windows
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'sample-lineage.svg')
REPO = 'acme/shop'

# ------------------------------------------------------------------ palette (the page, the ink, one set per state)
PAGE, INK, INK2 = '#f3f0e8', '#1c2430', '#3b4350'
STY = {
    'open':     dict(fill='#f8e8e4', stroke='#8a3030', pill='#9f2d2d', pw=47.6, word='open',    kind='ISSUE'),
    'umbrella': dict(fill='#f8e8e4', stroke='#8a3030', pill='#9f2d2d', pw=47.6, word='open',    kind='UMBRELLA'),
    'closed':   dict(fill='#eceae6', stroke='#6e6a64', pill='#4e4b48', pw=62.4, word='closed',  kind='ISSUE'),
    'merged':   dict(fill='#e7f0fb', stroke='#1d4e89', pill='#163e73', pw=62.4, word='merged',  kind='PR'),
    'waiting':  dict(fill='#ffeb85', stroke='#8f6400', pill='#9a6700', pw=69.8, word='waiting', kind='PR'),
    'draft':    dict(fill='#fff6c9', stroke='#8f6400', pill='#9a6700', pw=55.0, word='draft',   kind='PR', dashed=True),
    'prclosed': dict(fill='#eceae6', stroke='#6e6a64', pill='#4e4b48', pw=62.4, word='closed',  kind='PR', stripes=True, cross=True),
}
# arrow word: colour, dashed, arrowhead marker, label width
EDGE = {
    'child':        ('#1c2430', False, 'h-child', 46.0),
    'closed by':    ('#1d4e89', False, 'h-closed', 71.6),
    'work done by': ('#1d4e89', True, 'h-work', 90.8),
    'follow-up':    ('#8a4b12', False, 'h-led', 71.6),
    'led to':       ('#8a4b12', False, 'h-led', 52.4),
    'supersedes':   ('#b02a2a', False, 'h-cross', 66.0),
    'blocked by':   ('#8a3030', False, 'h-blocked', 66.0),
    'related':      ('#6e6a64', True, 'h-ref', 58.8),
}
MEANS = [('child', 'B is a formal child of umbrella A'), ('closed by', 'B is the pull request that closed issue A'),
         ('work done by', 'B worked on A without closing it'), ('follow-up', 'B was filed for what A left out'),
         ('led to', 'work on A produced B'), ('supersedes', 'pull request A replaced B (B closed unmerged)'),
         ('blocked by', 'A cannot finish until B is done'), ('related', 'related work, no parent')]

# ------------------------------------------------------------------ the invented facts
# (number, column, row, state, title, meta line, merge line, notes)
CX = [80, 545, 1010, 1475]          # column x; boxes are 260 wide, gaps are 205
ITEMS = [
    (100, 0, 1, 'umbrella', 'Checkout rework: cart, coupons and guest retry', 'opened 2026-03-02 · still open', None,
     ['Lists #101, #102 and #103 as children.', '**Blocked by #102.**']),
    (101, 1, 0, 'closed', 'Cart totals round half up instead of half even', 'opened 2026-03-04 · closed 2026-03-11', None,
     ['Closed by PR #110.']),
    (110, 2, 0, 'merged', 'cart: round totals half even (#101)', 'opened 2026-03-09 · merged 2026-03-11', 'merge 9f3c2ab41 (bob)',
     ['Closes #101.', 'Shipping is rounded the old way: #120.']),
    (120, 3, 0, 'open', 'cart: round shipping half even too', 'opened 2026-03-11 · still open', None,
     ['Follow-up of PR #110.', '**Blocks #121.**']),
    (102, 1, 1, 'open', 'Coupon stacking: allow one percent coupon and one fixed coupon', 'opened 2026-03-05 · still open', None,
     ['Fix in PR #111 (open).', '**Blocks #100.**']),
    (111, 2, 1, 'waiting', 'checkout: stack one percent and one fixed coupon (#102)', 'opened 2026-03-20 · waiting for review', None,
     ['Closes #102. Related: PR #112.', 'Review found #121.']),
    (121, 3, 1, 'open', 'coupon line shows the old total after stacking', 'opened 2026-03-21 · still open', None,
     ['**Found in review of PR #111.**', '**Blocked by #120.**', 'Fix in PR #122 (draft).']),
    (122, 3, 2, 'draft', 'checkout: show the stacked total on the coupon line (#121)', 'opened 2026-03-22 \u00b7 draft', None,
     ['Closes #121.']),
    (103, 1, 2, 'closed', 'Guest checkout fails on payment retry', 'opened 2026-03-10 · closed 2026-03-18', None,
     ['Work started in PR #112,', 'finished in PR #113.']),
    (112, 2, 2, 'prclosed', 'checkout: keep the guest cart on retry (#103)', 'opened 2026-03-12 · closed 2026-03-17', None,
     ['**Not merged: superseded by PR #113.**']),
    (113, 2, 3, 'merged', 'checkout: retry reuses the guest cart and the payment key (#103)', 'opened 2026-03-16 · merged 2026-03-18',
     'merge 4d1e7c0a2 (alice, bob)', ['Closes #103. Supersedes PR #112.']),
]
def read_tsv(name):
    path = os.path.join(HERE, name)
    rows = {}
    for line in open(path, encoding='utf-8') if os.path.exists(path) else []:
        a = line.rstrip('\n').split('\t')
        if len(a) == 2 and a[1]:
            rows[int(a[0])] = a[1].split(',')
    return rows


ASSIGNEES, PRAUTH = read_tsv('assignees.tsv'), read_tsv('prauthors.tsv')     # written by refresh_meta.py --tsv-dir
NEW = {120, 121}                     # the boxes added in the latest revision of this sample
PRS = {n for n, _c, _r, st, *_ in ITEMS if STY[st]['kind'] == 'PR'}


# ------------------------------------------------------------------ helpers
def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').encode('ascii', 'xmlcharrefreplace').decode()


TITLES = {it[0]: it[4] for it in ITEMS}


def link(num, bold=False):
    """A number is a link, always underlined, with the item's title as a tooltip (a <title> child of the <a>)."""
    u = 'https://github.com/%s/%s/%d' % (REPO, 'pull' if num in PRS else 'issues', num)
    tip = '<title>%s</title>' % esc(TITLES[num]) if num in TITLES else ''
    return '<a href="%s" xlink:href="%s" target="_blank">%s<tspan style="text-decoration:underline">#%d</tspan></a>' % (u, u, tip, num)


def rich(t):
    """Escape and link #NNN. **text** is a live claim and is bold."""
    if '**' in t:
        return ''.join(('<tspan style="font-weight:700">%s</tspan>' % rich(p)) if i % 2 else rich(p) for i, p in enumerate(t.split('**')) if p)
    out, pos = '', 0
    for m in re.finditer(r'#(\d{3,4})', t):
        out += esc(t[pos:m.start()]) + link(int(m.group(1)))
        pos = m.end()
    return out + esc(t[pos:])


_kind_font = load('bold', 54)      # 13.5px bold, measured at 4x
_who_font = load('bold', 46)       # 11.5px bold


def node(num, x, y, state, title, meta, mono, notes, new):
    st = STY[state]
    lines = textwrap.wrap(title, 33)
    t = len(lines)
    nlines = []
    for n in notes:                                    # notes wrap at 38 characters
        nlines += textwrap.wrap(n, 38) if '**' not in n else [n]
    h = 78 + 15 * t + 14 * len(nlines) + (14 if mono else 0)
    pr = st['kind'] == 'PR'
    u = 'https://github.com/%s/%s/%d' % (REPO, 'pull' if pr else 'issues', num)
    o = ['<g id="n%d">' % num,
         '<rect x="%s" y="%s" width="260" height="%s" rx="10" fill="%s" stroke="%s" stroke-width="1.6"%s/>' % (
             x, y, h, st['fill'], st['stroke'], ' stroke-dasharray="6 4"' if st.get('dashed') else ''),
         '<text class="kind" x="%s" y="%s" style="fill:%s">%s %s</text>' % (x + 14, y + 28, st['stroke'], st['kind'], link(num))]
    # assignee (issue: tiny arrow and name, or `?`) or submitter (pull request: `by` name), after the number.
    # It must end before the pill (and before the red cross): 11.5px, else 9px, else a second line. Never truncated.
    if pr:
        text = 'by ' + (PRAUTH.get(num) or ['?'])[0]
    else:
        names = ASSIGNEES.get(num)
        text = '?' if not names else names[0] + (' +%d' % (len(names) - 1) if len(names) > 1 else '')
    label = '%s #%d' % (st['kind'], num)
    w = _kind_font.getlength(label) / 4 + 0.3 * len(label)
    limit = x + 248 - st['pw'] - (25 if st.get('cross') else 6)        # the cross's left edge is 19px left of the pill
    for size, line_y, x0 in ((11.5, y + 28, x + 14 + w), (9, y + 28, x + 14 + w), (11.5, y + 41, x - w)):
        ax = x0 + 6                                                    # where the tiny arrow starts
        tx = x0 + 8 if pr else ax + 15
        end = tx + load('bold', int(size * 4)).getlength(text) / 4
        if end <= (limit if line_y == y + 28 else x + 246):
            break
    else:
        raise SystemExit('name of #%d does not fit even on a second line' % num)
    if not pr:
        ay = line_y - 4.6
        o.append('<polyline points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" stroke="%s" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>' % (
            ax, ay, ax + 10, ay, ax + 7, ay - 2.6, ax + 10, ay, ax + 7, ay + 2.6, st['stroke']))
    o.append('<text class="meta" x="%.1f" y="%s" style="fill:%s;font-size:%gpx;font-weight:600">%s</text>' % (tx, line_y, st['stroke'], size, esc(text)))
    o.append('<rect x="%.1f" y="%s" width="%s" height="20" rx="10" fill="%s"/>' % (x + 248 - st['pw'], y + 13, st['pw'], st['pill']))
    o.append('<text class="pill" x="%.1f" y="%s" text-anchor="middle" style="fill:%s">%s</text>' % (x + 248 - st['pw'] / 2, y + 27, st['fill'], st['word']))
    if st.get('stripes'):                              # a pull request closed without merging: soft red stripes under the text
        o.append('<defs><pattern id="stripes%d" width="22" height="22" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="9" height="22" fill="#b84a4a" fill-opacity=".10"/></pattern></defs>' % num)
        o.append('<rect x="%s" y="%s" width="260" height="%s" rx="10" fill="url(#stripes%d)"/>' % (x, y, h, num))
    if st.get('cross'):                                # and a red cross left of the pill
        kx, ky = x + 248 - st['pw'] - 13, y + 23
        for a, b in ((-6, 6), (6, -6)):
            o.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#ff2a2a" stroke-width="2.8" stroke-linecap="round"/>' % (kx - 6 if a < 0 else kx + 6, ky - 6, kx + 6 if a < 0 else kx - 6, ky + 6))
    for i, l in enumerate(lines):
        o.append('<text class="ttl" x="%s" y="%s">%s</text>' % (x + 14, y + 55 + 15 * i, rich(l)))
    o.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-opacity="0.35"/>' % (x + 14, y + 52 + 15 * t, x + 246, y + 52 + 15 * t, st['stroke']))
    o.append('<text class="meta" x="%s" y="%s">%s</text>' % (x + 14, y + 65 + 15 * t, esc(meta)))
    ny = y + 79 + 15 * t
    if mono:
        o.append('<text class="mono" x="%s" y="%s">%s</text>' % (x + 14, ny, esc(mono)))
        ny += 14
    for i, n in enumerate(nlines):
        o.append('<text class="note" x="%s" y="%s">%s</text>' % (x + 14, ny + 14 * i, rich(n)))
    if new:                                            # corner ribbon, rotated -45 degrees, centred 3px inside the corner
        cx, cy, pw, ph = x + 3, y + 3, 47.0, 21.7
        o += ['<g transform="rotate(-45 %s %s)">' % (cx, cy),
              '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="#ff2a2a" stroke="%s" stroke-width="1.2"/>' % (cx - pw / 2, cy - ph / 2, pw, ph, ph / 2, PAGE),
              '<text class="pill" x="%s" y="%s" text-anchor="middle" style="fill:#ffffff;font-size:15.75px;letter-spacing:.9px">new</text>' % (cx + .45, cy + 4.2), '</g>']
    o.append('</g>')
    return h, '\n'.join(o)


# ------------------------------------------------------------------ geometry: rows are as tall as their tallest box
ROW_GAP = 130                       # room for a vertical arrow with its label between two rows
Y0 = 190
heights, rendered = {}, {}
for num, c, r, st, title, meta, mono, notes in ITEMS:
    heights[num], _ = node(num, CX[c], 0, st, title, meta, mono, notes, num in NEW)
row_h = {}
for num, c, r, *_ in ITEMS:
    row_h[r] = max(row_h.get(r, 0), heights[num])
row_y = {0: Y0}
for r in (1, 2, 3):
    row_y[r] = row_y[r - 1] + row_h[r - 1] + ROW_GAP
BOX = {}
for num, c, r, st, title, meta, mono, notes in ITEMS:
    y = row_y[r]
    if num == 100:                  # the umbrella starts at the row of its middle child, so that arrow is straight
        y = row_y[1]
    BOX[num] = (CX[c], y, 260, heights[num])
    _, rendered[num] = node(num, CX[c], y, st, title, meta, mono, notes, num in NEW)

PATHS, LABELS = [], []


def edge(pts, kind, lab):
    col, dash, mk, w = EDGE[kind]
    d = 'M' + ' L'.join('%.1f,%.1f' % p for p in pts)
    PATHS.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.9"%s stroke-linejoin="round" marker-end="url(#%s)"/>' % (d, col, ' stroke-dasharray="7 5"' if dash else '', mk))
    LABELS.append('<rect x="%.1f" y="%.1f" width="%s" height="18.0" rx="4" fill="#fffdf7" stroke="%s" stroke-width="0.9"/>' % (lab[0] - w / 2, lab[1] - 9, w, col))
    LABELS.append('<text class="lbl" x="%.1f" y="%.1f" text-anchor="middle" style="fill:%s">%s</text>' % (lab[0], lab[1] + 4, col, kind))


def L(n): return BOX[n][0]
def R(n): return BOX[n][0] + BOX[n][2]
def T(n): return BOX[n][1]
def B(n): return BOX[n][1] + BOX[n][3]


# the umbrella fans out to its three children; each arrow has its own start point and the lanes nest without crossing
u = BOX[100]
edge([(R(100), u[1] + 30), (400, u[1] + 30), (400, T(101) + 60), (L(101), T(101) + 60)], 'child', (472, T(101) + 60))
edge([(R(100), u[1] + 60), (L(102), T(102) + 60)], 'child', (440, u[1] + 60))
edge([(R(100), u[1] + 90), (400, u[1] + 90), (400, T(103) + 60), (L(103), T(103) + 60)], 'child', (472, T(103) + 60))
edge([(R(101), T(101) + 60), (L(110), T(110) + 60)], 'closed by', ((R(101) + L(110)) / 2, T(101) + 60))
edge([(R(110), T(110) + 60), (L(120), T(120) + 60)], 'follow-up', ((R(110) + L(120)) / 2, T(110) + 60))
edge([(R(102), T(102) + 60), (L(111), T(111) + 60)], 'closed by', ((R(102) + L(111)) / 2, T(102) + 60))
edge([(R(111), T(111) + 60), (L(121), T(121) + 60)], 'led to', ((R(111) + L(121)) / 2, T(111) + 60))
edge([(L(121) + 130, T(121)), (L(120) + 130, B(120))], 'blocked by', (L(120) + 130, (T(121) + B(120)) / 2))
edge([(L(121) + 130, B(121)), (L(122) + 130, T(122))], 'closed by', (L(121) + 130, (B(121) + T(122)) / 2))
edge([(R(103), T(103) + 60), (L(112), T(112) + 60)], 'work done by', ((R(103) + L(112)) / 2, T(103) + 60))
lane = R(103) + 30
edge([(R(103), B(103) - 30), (lane, B(103) - 30), (lane, T(113) + 60), (L(113), T(113) + 60)], 'closed by', ((lane + L(113)) / 2, T(113) + 60))
edge([(L(112) + 130, T(113)), (L(112) + 130, B(112))], 'supersedes', (L(112) + 130, (T(113) + B(112)) / 2))
edge([(L(111) + 130, B(111)), (L(112) + 130, T(112))], 'related', (L(111) + 130, (B(111) + T(112)) / 2))

# ------------------------------------------------------------------ frame (an area of work; it names no relation), page, title
fx0, fy0 = L(103) - 60, T(112) - 46
frame = ['<rect x="%s" y="%s" width="%s" height="%s" rx="18" fill="#ffffff" fill-opacity="0.22" stroke="#8d877e" stroke-width="1.6" stroke-dasharray="2 6" stroke-linecap="round"/>' % (
    fx0, fy0, R(113) + 30 - fx0, B(113) + 24 - fy0),
    '<text class="ftl" x="%s" y="%s">guest checkout</text>' % (fx0 + 16, fy0 + 24)]
W = 2420
H = int(max(B(n) for n in BOX) + 80)

# ------------------------------------------------------------------ legend (top right, compact)
LX, LY, LW = 1860, 190, 500
lg = []
y = LY + 30
lg.append('<text class="lgb" x="%s" y="%s" style="font-size:16px">How to read this graph</text>' % (LX + 16, y))
y += 24
lg.append('<text class="lg" x="%s" y="%s">Arrows run from the earlier item to the later one;</text>' % (LX + 16, y))
y += 18
lg.append('<text class="lg" x="%s" y="%s">blocked by, supersedes and related may point back.</text>' % (LX + 16, y))
y += 26
for i, (word, c) in enumerate(((k, STY[k]) for k in ('open', 'closed', 'merged', 'waiting', 'draft'))):
    lx = LX + 16 + i * 96
    lg.append('<rect x="%s" y="%s" width="88" height="30" rx="7" fill="%s" stroke="%s" stroke-width="1.4"%s/>' % (lx, y, c['fill'], c['stroke'], ' stroke-dasharray="6 4"' if c.get('dashed') else ''))
    lg.append('<text class="pill" x="%s" y="%s" text-anchor="middle" style="fill:%s">%s</text>' % (lx + 44, y + 19, c['stroke'], c['word']))
y += 50
lg.append('<text class="lg" x="%s" y="%s">Closed without merging: gray, red stripes, red cross.</text>' % (LX + 16, y))
y += 20
lg.append('<text class="lg" x="%s" y="%s">Red <tspan style="font-weight:700">new</tspan> corner: added in the latest revision.</text>' % (LX + 16, y))
y += 20
lg.append('<text class="lg" x="%s" y="%s"><tspan style="font-weight:700">Bold</tspan> lines are claims that hold now (blocks, found, not merged).</text>' % (LX + 16, y))
y += 14
for word, mean in MEANS:
    y += 28
    col, dash, mk, w = EDGE[word]
    lg.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="1.9"%s marker-end="url(#%s)"/>' % (LX + 16, y - 4, LX + 62, y - 4, col, ' stroke-dasharray="7 5"' if dash else '', mk))
    lg.append('<text class="lgb" x="%s" y="%s" style="font-size:12.5px">%s</text>' % (LX + 74, y, word))
    lg.append('<text class="lg" x="%s" y="%s" style="font-size:12px">%s</text>' % (LX + 170, y, esc(mean)))
LH = y + 22 - LY
legend = ['<rect x="%s" y="%s" width="%s" height="%s" rx="14" fill="#fbfaf6" stroke="#b9b3a8" stroke-width="1.2"/>' % (LX, LY, LW, LH)] + lg

# ------------------------------------------------------------------ assemble
markers = ''.join('<marker id="%s" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L12,6 L0,12 z" fill="%s"/></marker>\n' % (mk, col)
                  for mk, col in (('h-child', '#1c2430'), ('h-closed', '#1d4e89'), ('h-work', '#1d4e89'), ('h-led', '#8a4b12'), ('h-blocked', '#8a3030'), ('h-ref', '#6e6a64')))
markers += '<marker id="h-cross" overflow="visible" viewBox="0 0 16 16" refX="8" refY="8" markerWidth="16" markerHeight="16" markerUnits="userSpaceOnUse" orient="auto"><path d="M2.5,2.5 L13.5,13.5 M13.5,2.5 L2.5,13.5" stroke="#ff2a2a" stroke-width="3" stroke-linecap="round" fill="none"/></marker>\n'
css = ('.kind{font-size:13.5px;font-weight:700;letter-spacing:.3px}.ttl{font-size:12.5px;fill:%s}.meta{font-size:11px;fill:%s}.mono{font-size:11px;font-family:Menlo,Consolas,monospace;fill:%s}'
       '.note{font-size:11px;font-style:italic;fill:%s}.pill{font-size:10.5px;font-weight:700;letter-spacing:.6px}.lbl{font-size:11.5px;font-weight:600}.ftl{font-size:15px;font-style:italic;fill:#6e6a64;letter-spacing:.4px}'
       '.h1{font-size:30px;font-weight:700;fill:%s}.h2{font-size:15px;fill:%s}.lg{font-size:13px;fill:%s}.lgb{font-size:13px;font-weight:700;fill:%s}') % (INK, INK2, INK, INK2, INK, INK2, INK, INK)
script = open(os.path.join(HERE, '..', 'find-box.js'), encoding='utf-8').read()
svg = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="%d" height="%d" viewBox="0 0 %d %d" font-family="Helvetica Neue, Helvetica, Arial, sans-serif">' % (W, H, W, H),
       '<title>Sample lineage of a checkout rework (acme/shop)</title>',
       '<desc>Example for the bbb-github-diag skill: an umbrella with three children, the pull requests that closed or replaced them, follow-ups, a block and a related pair.</desc>',
       '<defs>\n' + markers + '<style>' + css + '</style>\n</defs>',
       '<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (W, H, PAGE),
       '<text class="h1" x="80" y="70">Checkout rework: what grew out of umbrella %s</text>' % link(100),
       '<text class="h2" x="80" y="100"><tspan style="font-weight:700">Repository: %s</tspan></text>' % REPO,
       '<text class="h2" x="80" y="124">Arrows point from the earlier item to the item it produced, or from an issue to the pull request that closed it. Read left to right.</text>',
       '<text class="h2" x="80" y="148">Facts as of 2026-03-22. Dotted frames name an area of work only; the arrows carry the relationships.</text>']
svg += frame + PATHS + [rendered[n] for n in sorted(BOX)] + LABELS + legend
svg += ['<script type="text/javascript"><![CDATA[\n' + script + '\n]]></script>', '</svg>', '']
open(OUT, 'w', encoding='utf-8').write('\n'.join(svg))
print('wrote', OUT, W, 'x', H, len(BOX), 'boxes')
