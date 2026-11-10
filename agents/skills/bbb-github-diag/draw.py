#!/usr/bin/env python3
"""Drawing pieces shared by build.py, add_nodes.py and relayout.py: the box, the arrow vocabulary, the legend, the page frame.

Nothing here decides a position. A caller gives a box its x, y and gets markup and a size back; an arrow gets its points from route.py.

Text rules kept in one place:
- Titles and notes wrap by the measured width of the real font (fonts.py), never by a character count. The box is always 260 wide;
  only its height changes with the number of lines.
- A reference to another item is written `#N` (any number of digits) in a title or note; `PR #N` marks a pull request. It becomes a
  link to https://github.com/OWNER/REPO/issues/N or /pull/N, underlined, with the item's title as a tooltip. `**text**` is bold.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fonts import load
import box_header, svgmeta

PAGE, INK, INK2 = '#ebe5d7', '#1c2430', '#3b4350'   # the page is a step darker than a frame's inside (FRAME_FILL_OPACITY)
FRAME_FILL_OPACITY = '0.5'                          # white over the page: a frame reads as a lighter panel among many arrows
BOX_W, INNER = 260, 232

# state -> colours. `kind` is the tag; flags: dashed (draft), stripes + cross (pull request closed unmerged), cross (issue closed by hand)
STY = {
    'open':       dict(fill='#f8e8e4', stroke='#8a3030', pill='#9f2d2d', pw=47.6, word='open',    kind='ISSUE'),
    'closed':     dict(fill='#eceae6', stroke='#6e6a64', pill='#4e4b48', pw=62.4, word='closed',  kind='ISSUE'),
    'handclosed': dict(fill='#eceae6', stroke='#6e6a64', pill='#4e4b48', pw=62.4, word='closed',  kind='ISSUE', cross=True),
    'merged':     dict(fill='#e7f0fb', stroke='#1d4e89', pill='#163e73', pw=62.4, word='merged',  kind='PR'),
    'waiting':    dict(fill='#ffeb85', stroke='#8f6400', pill='#9a6700', pw=69.8, word='waiting', kind='PR'),
    'draft':      dict(fill='#fff6c9', stroke='#8f6400', pill='#9a6700', pw=55.0, word='draft',   kind='PR', dashed=True),
    'prclosed':   dict(fill='#eceae6', stroke='#6e6a64', pill='#4e4b48', pw=62.4, word='closed',  kind='PR', stripes=True, cross=True),
}

# arrow word -> colour, dashed, marker, forward (points from the earlier item to the later one), what it means (legend)
EDGE = {
    'child':        ('#1c2430', False, 'h-child',   True,  'B is a formal child of umbrella A'),
    'follow-up':    ('#8a4b12', False, 'h-led',     True,  'B was filed for what A left out'),
    'led to':       ('#8a4b12', False, 'h-led',     True,  'work on A produced B'),
    'spawned':      ('#8a4b12', False, 'h-led',     True,  'A caused B to be filed as a new work stream'),
    'revised by':   ('#8a4b12', False, 'h-led',     True,  'B is a later pull request that changes what A delivered'),
    'closed by':    ('#1d4e89', False, 'h-closed',  True,  'B is the pull request that closed issue A'),
    'work done by': ('#1d4e89', True,  'h-work',    True,  'B worked on A without closing it'),
    'evidence, does not close': ('#9a6700', True, 'h-evid', True, 'B is evidence for A; A stays open'),
    'supersedes':   ('#b02a2a', False, 'h-cross',   False, 'pull request A replaced B (B closed unmerged)'),
    'duplicate of': ('#b02a2a', False, 'h-dup',     False, 'issue A was closed as a duplicate of B'),
    'blocked by':   ('#8a3030', False, 'h-blocked', False, 'A cannot finish until B is done'),
    'depends on':   ('#6e6a64', True,  'h-ref',     False, 'A needs the result of B, which does not block it'),
    'references':   ('#6e6a64', True,  'h-ref',     False, 'A points to B as relevant prior work'),
    'mentioned':    ('#6e6a64', True,  'h-ref',     False, 'A names B in passing'),
    'related':      ('#6e6a64', True,  'h-ref',     False, 'related work, neither is the parent'),
}

# How much an arrow matters to the reader, 3 (very) to 1 (low). It decides which arrows shape the layout (how hard each pulls two frames
# together) and which are routed first, so the important ones get the short, simple paths and a low one is the one left out when space
# runs out. Its direction (forward or not, the 4th field of EDGE) is a separate fact: it sets the columns.
IMPORTANCE = {'child': 3, 'closed by': 3, 'blocked by': 3, 'depends on': 3,
              'follow-up': 2, 'led to': 2, 'spawned': 2, 'revised by': 2, 'work done by': 2, 'evidence, does not close': 2,
              'supersedes': 2, 'duplicate of': 2, 'references': 2,
              'related': 1, 'mentioned': 1}
PULL = {3: 1.0, 2: 0.6, 1: 0.2}                     # tier -> how hard the arrow pulls its two frames together


def pull(kind):
    return PULL[IMPORTANCE.get(kind, 2)]
MARKERS = (('h-child', '#1c2430'), ('h-closed', '#1d4e89'), ('h-work', '#1d4e89'), ('h-led', '#8a4b12'), ('h-blocked', '#8a3030'),
           ('h-ref', '#6e6a64'), ('h-evid', '#9a6700'), ('h-dup', '#b02a2a'))


def fmt(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').encode('ascii', 'xmlcharrefreplace').decode()


_bold = load('bold', 46)


def label_width(word):
    """Width of the opaque label that sits on an arrow: the bold 11.5px word plus 18.4px of padding."""
    return round(_bold.getlength(word) / 4 + 18.4, 1)


def wrap_px(text, style, size, maxw=INNER):
    """Greedy word wrap by the measured width of the real font. **bold** words are measured in the bold face, and every wrapped line
    that holds bold words gets its own pair of markers, so a bold sentence wraps like any other."""
    f = load(style, int(size * 4))
    fb = load({'italic': 'bolditalic', 'regular': 'bold'}.get(style, style), int(size * 4))
    words = [(w, i % 2 == 1) for i, part in enumerate(text.split('**')) for w in part.split()]

    def width(ws):
        return sum((fb if b else f).getlength(w) for w, b in ws) / 4 + f.getlength(' ') / 4 * max(len(ws) - 1, 0)

    def render(ws):                               # runs of plain and bold words; each bold run gets its markers
        runs = []
        for w, b in ws:
            if runs and runs[-1][1] == b:
                runs[-1][0].append(w)
            else:
                runs.append(([w], b))
        return ' '.join(('**%s**' if b else '%s') % ' '.join(r) for r, b in runs)

    lines, cur = [], []
    for wb in words:
        if cur and width(cur + [wb]) > maxw:
            lines.append(cur)
            cur = [wb]
        else:
            cur.append(wb)
    return [render(ws) for ws in lines + ([cur] if cur else [])]


class Ctx:
    """What a box needs to know about the diagram: the repository, the titles (link tooltips) and which numbers are pull requests."""

    def __init__(self, repo, titles=None, prs=()):
        self.repo, self.titles, self.prs = repo, {str(k): v for k, v in (titles or {}).items()}, {str(p) for p in prs}

    def link(self, num, pr=None):
        pr = (str(num) in self.prs) if pr is None else pr
        u = 'https://github.com/%s/%s/%s' % (self.repo, 'pull' if pr else 'issues', num)
        tip = '<title>%s</title>' % esc(self.titles[str(num)]) if str(num) in self.titles else ''
        return '<a href="%s" xlink:href="%s" target="_blank">%s<tspan style="text-decoration:underline">#%s</tspan></a>' % (u, u, tip, num)

    def rich(self, t):
        """Escape a line, link every #N (a `PR #N` links a pull request), and bold **text**."""
        if '**' in t:
            return ''.join(('<tspan style="font-weight:700">%s</tspan>' % self.rich(p)) if i % 2 else self.rich(p) for i, p in enumerate(t.split('**')) if p)
        out, pos = '', 0
        for m in re.finditer(r'#(\d+)', t):
            pr = True if t[:m.start()].endswith('PR ') else None
            out += esc(t[pos:m.start()]) + self.link(m.group(1), pr)
            pos = m.end()
        return out + esc(t[pos:])


def box_lines(b):
    """The wrapped title and note lines of a spec box (dict: title, notes, mono)."""
    title = wrap_px(b['title'], 'regular', 12.5)
    notes = []
    for n in b.get('notes', []):
        notes += wrap_px(n, 'italic', 11)                                 # bold words wrap too (wrap_px keeps their markers)
    return title, notes


def box_height(b, min_h=0):
    title, notes = box_lines(b)
    return max(min_h, 78 + 15 * len(title) + 14 * len(notes) + (14 if b.get('mono') else 0))


def two_lines(ctx, b):
    """Does the first line of this box (tag, number, arrow, name) need a second line? Then a collapsed box needs 78px, not 62px."""
    st = STY[b['state']]
    pr = st['kind'] == 'PR'
    if pr:
        who = 'by ' + esc(b['author']) if b.get('author') else None
    else:
        names = b.get('assignees') or []
        who = esc('?' if not names else names[0] + (' +%d' % (len(names) - 1) if len(names) > 1 else ''))
    limit = 248 - st['pw'] - (31 if st.get('cross') else 6)
    return box_header.header(14, 28, st['stroke'], st['kind'], ctx.link(b['num'], pr), who, bool(b.get('umbrella')) and not pr, limit)[1]


def box(ctx, b, x, y, min_h=0):
    """Markup of one full box. b: num, state, title, meta, notes, mono, assignees, author, umbrella, new. Returns (markup, height)."""
    st = STY[b['state']]
    num = b['num']
    pr = st['kind'] == 'PR'
    umb = bool(b.get('umbrella')) and not pr
    title, notes = box_lines(b)
    t = len(title)
    h = box_height(b, min_h)
    o = [svgmeta.box_open(num, b.get('frame'), b.get('github')),      # with the box's frame and GitHub record (svgmeta.py)
         '<rect x="%s" y="%s" width="260" height="%s" rx="10" fill="%s" stroke="%s" stroke-width="%s"%s/>' % (
             fmt(x), fmt(y), fmt(h), st['fill'], st['stroke'], 2.6 if umb else 1.6, ' stroke-dasharray="6 4"' if st.get('dashed') else '')]
    if umb:                                                  # the double border of an umbrella
        o.append('<rect x="%s" y="%s" width="252" height="%s" rx="7" fill="none" stroke="%s" stroke-width="0.9"/>' % (fmt(x + 4), fmt(y + 4), fmt(h - 8), st['stroke']))
    if pr:
        who = 'by ' + esc(b['author']) if b.get('author') else None
    else:
        names = b.get('assignees') or []
        who = esc('?' if not names else names[0] + (' +%d' % (len(names) - 1) if len(names) > 1 else ''))
    limit = x + 248 - st['pw'] - (31 if st.get('cross') else 6)         # the cross's left edge is 19px left of the pill, and 12px clear of it
    o.append(box_header.header(x + 14, y + 28, st['stroke'], st['kind'], ctx.link(num, pr), who, umb, limit)[0])
    o.append('<rect x="%.1f" y="%s" width="%s" height="20" rx="10" fill="%s"/>' % (x + 248 - st['pw'], fmt(y + 13), st['pw'], st['pill']))
    o.append('<text class="pill" x="%.1f" y="%s" text-anchor="middle" style="fill:%s">%s</text>' % (x + 248 - st['pw'] / 2, fmt(y + 27), st['fill'], st['word']))
    if st.get('stripes'):                                    # a pull request closed without merging: soft red stripes under the text
        o.append('<defs><pattern id="stripes%s" width="22" height="22" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="9" height="22" fill="#b84a4a" fill-opacity=".10"/></pattern></defs>' % num)
        o.append('<rect x="%s" y="%s" width="260" height="%s" rx="10" fill="url(#stripes%s)"/>' % (fmt(x), fmt(y), fmt(h), num))
    if st.get('cross'):                                      # and a red cross left of the pill
        kx, ky = x + 248 - st['pw'] - 13, y + 23
        o.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#ff2a2a" stroke-width="2.8" stroke-linecap="round"/>' % (fmt(kx - 6), fmt(ky - 6), fmt(kx + 6), fmt(ky + 6)))
        o.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#ff2a2a" stroke-width="2.8" stroke-linecap="round"/>' % (fmt(kx + 6), fmt(ky - 6), fmt(kx - 6), fmt(ky + 6)))
    for i, l in enumerate(title):
        o.append('<text class="ttl" x="%s" y="%s">%s</text>' % (fmt(x + 14), fmt(y + 55 + 15 * i), ctx.rich(l)))
    o.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-opacity="0.35"/>' % (fmt(x + 14), fmt(y + 52 + 15 * t), fmt(x + 246), fmt(y + 52 + 15 * t), st['stroke']))
    o.append('<text class="meta" x="%s" y="%s">%s</text>' % (fmt(x + 14), fmt(y + 65 + 15 * t), esc(b.get('meta', ''))))
    ny = y + 79 + 15 * t
    if b.get('mono'):
        o.append('<text class="mono" x="%s" y="%s">%s</text>' % (fmt(x + 14), fmt(ny), esc(b['mono'])))
        ny += 14
    for i, n in enumerate(notes):
        o.append('<text class="note" x="%s" y="%s">%s</text>' % (fmt(x + 14), fmt(ny + 14 * i), ctx.rich(n)))
    if b.get('new'):
        o += new_pill(x, y)
    o.append('</g>')
    return '\n'.join(o), h


def new_pill(x, y):
    """The red `new` corner ribbon, rotated -45 degrees, centred 3px inside the top-left corner of a box at x, y."""
    cx, cy, pw, ph = x + 3, y + 3, 47.0, 21.7
    return ['<g transform="rotate(-45 %s %s)">' % (fmt(cx), fmt(cy)),
            '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="#ff2a2a" stroke="%s" stroke-width="1.2"/>' % (fmt(cx - pw / 2), fmt(cy - ph / 2), pw, ph, ph / 2, PAGE),
            '<text class="pill" x="%s" y="%s" text-anchor="middle" style="fill:#ffffff;font-size:15.75px;letter-spacing:.9px">new</text>' % (fmt(cx + .45), fmt(cy + 4.2)),
            '</g>']


def arrow(pts, kind, a=None, b=None):
    """The path of one arrow from box a to box b. Points are final coordinates; hops.py adds the jump arcs afterwards. With a and b the
    path carries data-from, data-to and data-kind (svgmeta.py), so the arrow's meaning never depends on reading its geometry."""
    col, dash, mk = EDGE[kind][:3]
    d = 'M' + ' L'.join('%s,%s' % (fmt(px), fmt(py)) for px, py in pts)
    return '<path d="%s" fill="none" stroke="%s" stroke-width="1.9"%s stroke-linejoin="round" marker-end="url(#%s)"%s/>' % (d, col, ' stroke-dasharray="7 5"' if dash else '', mk,
                                                                                                         svgmeta.arrow_attrs(a, b, kind) if a is not None else '')


def label(kind, cx, cy, shift=None):
    """The opaque label of an arrow, centred on cx, cy: a rectangle and its text (two lines of markup).
    shift (dx, dy): a label BESIDE its shaft (an arrow too short to carry one, route.place_label_beside). Its x and y stay on the shaft,
    so every script finds its arrow the usual way; a transform draws it shift px away. label_box gives the rectangle as drawn."""
    col, w = EDGE[kind][0], label_width(kind)
    tr = ' transform="translate(%.1f,%.1f)"' % shift if shift else ''
    return ['<rect x="%.1f" y="%.1f" width="%s" height="18.0" rx="4" fill="#fffdf7" stroke="%s" stroke-width="0.9"%s/>' % (cx - w / 2, cy - 9, w, col, tr),
            '<text class="lbl" x="%.1f" y="%.1f" text-anchor="middle" style="fill:%s"%s>%s</text>' % (cx, cy + 4, col, tr, esc(kind))]


LABEL_RECT = re.compile(r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)" rx="4" fill="#fffdf7"')
LABEL_SHIFT = re.compile(r' transform="translate\(([-\d.]+),([-\d.]+)\)"')


def label_shift(line):
    """(dx, dy) of a label drawn beside its shaft (draw.label shift), else None."""
    m = LABEL_SHIFT.search(line)
    return (float(m.group(1)), float(m.group(2))) if m else None


def label_box(lines, i):
    """The rectangle of the label at lines[i] as it is drawn (x, y, w, h): label_at's, moved by its shift. Use it for what a label
    covers; use label_at's x, y (on the shaft) to find its arrow."""
    lab = label_at(lines, i)
    if not lab:
        return None
    dx, dy = label_shift(lines[i]) or (0.0, 0.0)
    return lab[0] + dx, lab[1] + dy, lab[2], lab[3]


def label_at(lines, i):
    """Read the label that starts at lines[i]: a rectangle (any height) followed by one or more `<text class="lbl"` lines (a two-line label
    such as "evidence, / does not close" is 30px tall). Returns (x, y, w, h, n_text_lines, word) or None; word joins the text lines."""
    m = LABEL_RECT.match(lines[i])
    if not m:
        return None
    n = 0
    while i + 1 + n < len(lines) and lines[i + 1 + n].startswith('<text class="lbl"'):
        n += 1
    if not n:
        return None
    word = ' '.join(re.sub(r'<[^>]+>', '', lines[i + 1 + k]).replace('&amp;', '&') for k in range(n))
    x, y, w, h = (float(v) for v in m.groups())
    return x, y, w, h, n, word


def move_label(lines, i, cx, cy, shift=None):
    """Put the label at lines[i] with its centre on (cx, cy): the rectangle and every text line move by the same amount, so a label of any
    height stays whole. shift: drawn beside the shaft (see label); without it, a label that was beside its shaft is on it again.
    Edits `lines` in place."""
    x, y, w, h, n, _ = label_at(lines, i)
    dx, dy = (cx - w / 2) - x, (cy - h / 2) - y
    tr = ' transform="translate(%.1f,%.1f)"' % shift if shift else ''
    for k in range(i, i + 1 + n):
        s = LABEL_SHIFT.sub('', lines[k])
        s = re.sub(r'x="([\d.-]+)" y="([\d.-]+)"', lambda m: 'x="%.1f" y="%.1f"' % (float(m.group(1)) + dx, float(m.group(2)) + dy), s, count=1)
        if tr:
            s = re.sub(r'(/?>)', tr + r'\1', s, count=1)
        lines[k] = s


def frame(x, y, w, h, title):
    """A dotted frame that names an area of work (it names no relation)."""
    return ['<rect x="%s" y="%s" width="%s" height="%s" rx="18" fill="#ffffff" fill-opacity="%s" stroke="#8d877e" stroke-width="1.6" stroke-dasharray="2 6" stroke-linecap="round"/>' % (fmt(x), fmt(y), fmt(w), fmt(h), FRAME_FILL_OPACITY),
            '<text class="ftl" x="%s" y="%s">%s</text>' % (fmt(x + 16), fmt(y + 24), esc(title))]


LEGEND_W = 500


def legend(lx, ly, kinds, states):
    """The 'How to read this graph' block: pills for the states in use, the marks, one line per arrow word in use. Returns (lines, height)."""
    lg, y = [], ly + 30
    lg.append('<text class="lgb" x="%s" y="%s" style="font-size:16px">How to read this graph</text>' % (lx + 16, y))
    y += 28                                                      # no line on which way arrows run: each reads as its label says
    shown = [k for k in ('open', 'closed', 'merged', 'waiting', 'draft') if k in states] or ['open', 'closed', 'merged']
    for i, k in enumerate(shown):
        c = STY[k]
        px = lx + 16 + i * 96
        lg.append('<rect x="%s" y="%s" width="88" height="30" rx="7" fill="%s" stroke="%s" stroke-width="1.4"%s/>' % (px, y, c['fill'], c['stroke'], ' stroke-dasharray="6 4"' if c.get('dashed') else ''))
        lg.append('<text class="pill" x="%s" y="%s" text-anchor="middle" style="fill:%s">%s</text>' % (px + 44, y + 19, c['stroke'], c['word']))
    y += 50
    if 'prclosed' in states:
        lg.append('<text class="lg" x="%s" y="%s">Closed pull request, not merged: gray, red stripes, red cross.</text>' % (lx + 16, y))
        y += 20
    if 'handclosed' in states:
        lg.append('<text class="lg" x="%s" y="%s">Red cross on a closed issue: closed by hand, the work not done.</text>' % (lx + 16, y))
        y += 20
    lg.append('<text class="lg" x="%s" y="%s">Red <tspan style="font-weight:700">new</tspan> corner: added in the latest revision.</text>' % (lx + 16, y))
    y += 20
    lg.append('<text class="lg" x="%s" y="%s"><tspan style="font-weight:700">Bold</tspan> lines are claims that hold now (blocks, found, not merged).</text>' % (lx + 16, y))
    y += 14
    for word in [k for k in EDGE if k in kinds]:
        y += 28
        col, dash, mk = EDGE[word][:3]
        lg.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="1.9"%s marker-end="url(#%s)"/>' % (lx + 16, y - 4, lx + 62, y - 4, col, ' stroke-dasharray="7 5"' if dash else '', mk))
        lg.append('<text class="lgb" x="%s" y="%s" style="font-size:12.5px">%s</text>' % (lx + 74, y, esc(word)))
        lg.append('<text class="lg" x="%s" y="%s" style="font-size:12px">%s</text>' % (lx + 200, y, esc(EDGE[word][4])))
    h = y + 22 - ly
    return ['<rect x="%s" y="%s" width="%s" height="%s" rx="14" fill="#fbfaf6" stroke="#b9b3a8" stroke-width="1.2"/>' % (lx, ly, LEGEND_W, h)] + lg, h


def defs():
    markers = ''.join('<marker id="%s" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L12,6 L0,12 z" fill="%s"/></marker>\n' % (mk, col)
                      for mk, col in MARKERS)
    markers += ('<marker id="h-cross" overflow="visible" viewBox="0 0 16 16" refX="8" refY="8" markerWidth="16" markerHeight="16" markerUnits="userSpaceOnUse" orient="auto">'
                '<path d="M2.5,2.5 L13.5,13.5 M13.5,2.5 L2.5,13.5" stroke="#ff2a2a" stroke-width="3" stroke-linecap="round" fill="none"/></marker>\n')
    css = ('.kind{font-size:13.5px;font-weight:700;letter-spacing:.3px}.ttl{font-size:12.5px;fill:%s}.meta{font-size:11px;fill:%s}.mono{font-size:11px;font-family:Menlo,Consolas,monospace;fill:%s}'
           '.note{font-size:11px;font-style:italic;fill:%s}.pill{font-size:10.5px;font-weight:700;letter-spacing:.6px}.lbl{font-size:11.5px;font-weight:600}.ftl{font-size:15px;font-style:italic;fill:#6e6a64;letter-spacing:.4px}'
           '.h1{font-size:30px;font-weight:700;fill:%s}.h2{font-size:15px;fill:%s}.lg{font-size:13px;fill:%s}.lgb{font-size:13px;font-weight:700;fill:%s}') % (INK, INK2, INK, INK2, INK, INK2, INK, INK)
    return '<defs>\n' + markers + '<style>' + css + '</style>\n</defs>'


# ---------------------------------------------------------------- page header: facts as of a commit
FACTS_REST = 'Dotted frames name an area of work only; the arrows carry the relationships.'


def facts(repo, sha=None, branch=None, date=''):
    """The text of the header's facts line: the head commit of the default branch the facts were read against, as a link to it, and
    that branch (`Facts as of 1a2b3c4d5 / main.`); a date only when no commit is known (a first picture before its first refresh)."""
    if sha:
        u = 'https://github.com/%s/commit/%s' % (repo, sha)
        at = '<a href="%s" xlink:href="%s" target="_blank"><tspan style="text-decoration:underline">%s</tspan></a> / %s' % (u, u, sha[:9], esc(branch or ''))
    else:
        at = esc(date)
    return 'Facts as of %s. %s' % (at, FACTS_REST)


def set_header(text, repo, sha=None, branch=None):
    """Rewrite the header of an existing diagram: the facts line says the commit and branch (when sha is given); the old line on how to
    read the arrows (the arrows follow their labels, which need no explanation) goes, and the lines below it move up. The legend's
    matching lines go too (drop_legend_reading). Returns (text, log)."""
    log = []
    lines = text.split('\n')
    old = [i for i, l in enumerate(lines) if l.startswith('<text class="h2"') and 'Arrows point from the earlier item' in l]
    for i in old:
        y = float(re.search(r' y="([\d.]+)"', lines[i]).group(1))
        del lines[i]
        for k, l in enumerate(lines):
            m = re.match(r'(<text class="h2" x="[\d.]+" y=")([\d.]+)(".*)', l)
            if m and float(m.group(2)) > y:
                lines[k] = m.group(1) + ('%g' % (float(m.group(2)) - 24)) + m.group(3)
        log.append('header: the line on how to read the arrows removed')
    for k, l in enumerate(lines):
        m = re.match(r'(<text class="h2" x="[\d.]+" y="[\d.]+">)Facts as of .*</text>$', l)
        if m and sha:                                         # no commit known (no refresh yet): the facts line stays as it is
            new = m.group(1) + facts(repo, sha, branch) + '</text>'
            if new != l:
                lines[k] = new
                log.append('header: facts as of %s / %s' % (sha[:9], branch))
            break
    text, more = drop_legend_reading('\n'.join(lines))
    return text, log + more


LEGEND_READING = ('Arrows run from the earlier item to the later one;', 'blocked by, supersedes and related may point back.')
LEGEND_READING_H = 40          # the height those two lines took in the legend (legend() no longer writes them)


def drop_legend_reading(text):
    """Remove the legend's two lines on which way arrows run (an older file has them; each arrow reads as its label says): the rest of
    the legend moves up LEGEND_READING_H and its box gets as much shorter. Returns (text, log)."""
    lines = text.split('\n')
    if '<!--legend-->' not in lines or '<!--/legend-->' not in lines:
        return text, []
    a, z = lines.index('<!--legend-->'), lines.index('<!--/legend-->')
    hit = [i for i in range(a, z) if any(r in lines[i] for r in LEGEND_READING)]
    if not hit:
        return text, []
    last = max(hit)
    up = lambda ln: re.sub(r'\b(y|y1|y2)="(-?[\d.]+)"', lambda m: '%s="%s"' % (m.group(1), fmt(float(m.group(2)) - LEGEND_READING_H)), ln)
    for i in range(last + 1, z):
        lines[i] = up(lines[i])
    box = next((i for i in range(a, z) if lines[i].startswith('<rect ')), None)
    if box is not None:
        lines[box] = re.sub(r'height="([\d.]+)"', lambda m: 'height="%s"' % fmt(float(m.group(1)) - LEGEND_READING_H), lines[box], count=1)
    for i in sorted(hit, reverse=True):
        del lines[i]
    return '\n'.join(lines), ['legend: the lines on which way arrows run removed']
