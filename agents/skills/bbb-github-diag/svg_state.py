#!/usr/bin/env python3
"""Patch the state of boxes in a lineage SVG in place, from live GitHub data. No layout work, no rebuild.

Used by `refresh_meta.py --apply`. A box is patched when its pill disagrees with the live state, or its
assignee label, merge line or date line is out of date. Everything is a local text edit on the box group:

  - state change (open, closed, merged, waiting, draft): box fill, stroke, dash, pill (word, width, colour),
    the kind and assignee colours, the divider line, and the `opened ... . still open | closed D | merged D` line;
  - merged pull request: the `merge <sha9> (<authors>)` line (added or refreshed; the notes move down 14px);
  - issue closed by a pull request that is also a box: a note line `Closed by PR #N.` (added once);
  - assignee label of an issue.

A change that makes a box taller (a new merge line or note line) is applied only when the 14px below the box
are free of other boxes and still inside the frame that holds it; otherwise it is reported and left alone.
What needs thought is only reported: a closed pull request that was not merged (stripes, red cross, supersedes
arrow), a kind change (ISSUE to UMBRELLA), stale note text such as `Fix in PR #N (open)`.
A changed title is applied (retitle): rewrapped as draw.py wraps it; when it needs more lines the box grows only where
room_below() allows, else it is reported. Every link's tooltip gets the box's current title (retitle_links).

`apply(svg_text, live, repo)` returns (new_svg_text, log lines, report lines). Pure functions: no network.
"""
import re

import box_header

# state ->(fill, stroke, pill colour, pill width, dashed); the same table as the skill's palette
STY = {
    'open':    ('#f8e8e4', '#8a3030', '#9f2d2d', 47.6, False),
    'closed':  ('#eceae6', '#6e6a64', '#4e4b48', 62.4, False),
    'merged':  ('#e7f0fb', '#1d4e89', '#163e73', 62.4, False),
    'waiting': ('#ffeb85', '#8f6400', '#9a6700', 69.8, False),
    'draft':   ('#fff6c9', '#8f6400', '#9a6700', 55.0, True),
}
DASH = ' stroke-dasharray="6 4"'
DOT = r'(?:&#183;|·)'


def fmt(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')


def blocks(svg, pop=False):
    """num -> (start, end) character offsets of each box group `<g id="nNNN">...</g>` (nested groups counted).
    pop=True: the pop-up groups `<g id="popNNN" class="pop">` of collapsed boxes instead."""
    out = {}
    for m in re.finditer(r'<g id="pop(\d+)" class="pop">' if pop else r'<g id="n(\d+)"(?: data-[\w-]+="[^"]*")*>', svg):
        depth, pos = 0, m.start()
        for t in re.finditer(r'<g[ >]|</g>', svg[pos:]):
            depth += 1 if t.group(0).startswith('<g') else -1
            if depth == 0:
                out[int(m.group(1))] = (pos, pos + t.end())
                break
    return out


def rect_of(blk):
    m = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="(260|252)(?:\.0)?" height="([\d.]+)" rx="(?:10|7)"', blk)
    return float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))


def frames_of(svg):
    return [tuple(float(v) for v in m.groups()) for m in re.finditer(
        r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="18"[^>]*stroke-dasharray="2 6"', svg)]


_PAIR = re.compile(r'(-?[\d.]+),(-?[\d.]+)')


def bottom_ends(svg, x, y, w, h):
    """Arrows that end on the bottom edge of the box (x, y, w, h): [(start, end) of the d value, index of that point, index of its
    neighbour]. An orthogonal arrow that ends on a bottom edge comes in vertically, so growing the box shortens that last stretch."""
    out = []
    for m in re.finditer(r'<path d="(M[^"]*)"[^>]*marker-end', svg):
        ps = list(_PAIR.finditer(m.group(1)))
        for k, nb in ((0, 1), (len(ps) - 1, len(ps) - 2)):
            if len(ps) > 1 and abs(float(ps[k].group(2)) - (y + h)) < 1.5 and x - 1 <= float(ps[k].group(1)) <= x + w + 1:
                out.append((m.start(1), m.end(1), k, nb))
    return out


def follow_bottom(svg, rect, dy):
    """Move the ends of the arrows that touch the bottom edge of `rect` down by dy, so they still touch the box after it grew."""
    x, y, w, h = rect
    for s0, s1, k, _ in sorted(bottom_ends(svg, x, y, w, h), reverse=True):     # from the end of the text: offsets stay valid
        d = svg[s0:s1]
        p = list(_PAIR.finditer(d))[k]
        d = d[:p.start(2)] + fmt(float(p.group(2)) + dy) + d[p.end(2):]
        svg = svg[:s0] + d + svg[s1:]
    return svg


def room_below(svg, bl, num, dy):
    """True when the box can grow by dy: no other box in the way, still inside its frame, and every arrow that comes in from below
    keeps a straight stretch of at least 20px after its end moves down (follow_bottom)."""
    x, y, w, h = rect_of(svg[bl[num][0]:bl[num][1]])
    for s0, s1, k, nb in bottom_ends(svg, x, y, w, h):
        ps = list(_PAIR.finditer(svg[s0:s1]))
        if abs(float(ps[nb].group(2)) - (y + h)) < dy + 20:
            return False
    for n, (a, b) in bl.items():
        if n == num:
            continue
        ox, oy, ow, oh = rect_of(svg[a:b])
        if ox < x + w and ox + ow > x and oy < y + h + dy + 6 and oy + oh > y + h:
            return False
    for fx, fy, fw, fh in frames_of(svg):
        if fx <= x and x + w <= fx + fw and fy <= y and y + h <= fy + fh:      # the frame that holds the box
            return y + h + dy + 12 <= fy + fh
    return True


def link(repo, n, pr, title):
    u = 'https://github.com/%s/%s/%d' % (repo, 'pull' if pr else 'issues', n)
    t = title.replace('&', '&amp;').replace('<', '&lt;')
    return '<a href="%s" xlink:href="%s" target="_blank"><title>%s</title><tspan style="text-decoration:underline">#%d</tspan></a>' % (u, u, t, n)


TTL_SIZE, TTL_STEP = 12.5, 15        # the title lines of a box (draw.py): 12.5px, 15px apart


def _rich(text, repo, live):
    """One title or note line as draw.py writes it: escaped, every #N a link (with its title as tooltip when it is a box), **bold**,
    ~~struck~~."""
    import draw

    def esc(t):
        return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if '**' in text or '~~' in text:
        return ''.join(('<tspan style="%s">%s</tspan>' % (draw.MARK_STYLE[mk], _rich(p, repo, live))) if mk else _rich(p, repo, live)
                       for p, mk in draw.marked(text))
    out, pos = '', 0
    for m in re.finditer(r'#(\d+)', text):
        n = int(m.group(1))
        info = live.get(n) or {}
        pr = info.get('kind') == 'PR' or text[:m.start()].endswith('PR ')
        out += esc(text[pos:m.start()]) + link(repo, n, pr, info.get('title', ''))
        pos = m.end()
    return out + esc(text[pos:])


def retitle(blk, title, repo, live):
    """The box markup with its title lines rewritten for a new title, the lines below them moved by the change in height and the box
    grown or shrunk by it. Returns (new markup, dy, log text), or (blk, 0, None) when the drawn title already reads so."""
    import draw, html
    tl = list(re.finditer(r'<text class="ttl" x="([\d.]+)" y="([\d.]+)">(.*?)</text>', blk, re.S))
    if not tl:
        return blk, 0, None
    drawn = ' '.join(html.unescape(re.sub(r'<title>.*?</title>|<[^>]+>', '', m.group(3))) for m in tl)
    norm = lambda t: re.sub(r'\s+', ' ', t.replace('**', '')).strip()
    if norm(drawn) == norm(title):
        return blk, 0, None
    rows = draw.wrap_px(title, 'regular', TTL_SIZE)
    x, y0 = tl[0].group(1), float(tl[0].group(2))
    new = '\n'.join('<text class="ttl" x="%s" y="%s">%s</text>' % (x, fmt(y0 + TTL_STEP * k), _rich(r, repo, live)) for k, r in enumerate(rows))
    dy = (len(rows) - len(tl)) * TTL_STEP
    kept = ''
    if dy < 0:          # never shrink: arrows touch the bottom edge and the sides below; a short gap under the title is harmless
        dy, kept = 0, ', box kept its height'
    tail = blk[tl[-1].end():]
    if dy:
        tail = re.sub(r'\b(y|y1|y2)="(-?[\d.]+)"', lambda m: '%s="%s"' % (m.group(1), fmt(float(m.group(2)) + dy)), tail)
    out = blk[:tl[0].start()] + new + tail
    if dy:
        out = grow(out, dy)
    return out, dy, 'title "%s" -> "%s"%s' % (norm(drawn)[:50], norm(title)[:50], (', box %+dpx' % dy) if dy else kept)


def retitle_links(svg, live, repo):
    """The tooltip (<title>) of every link to a box, anywhere in the picture, says that box's title as GitHub has it now."""
    def fix(m):
        info = live.get(int(m.group(3))) or {}
        t = info.get('title')
        if not t:
            return m.group(0)
        return m.group(1) + t.replace('&', '&amp;').replace('<', '&lt;') + m.group(5)
    pat = r'(<a href="https://github\.com/%s/(issues|pull)/(\d+)" xlink:href="[^"]*" target="_blank"><title>)(.*?)(</title>)' % re.escape(repo)
    return re.sub(pat, fix, svg, flags=re.S)


def authors_text(authors):
    return ', '.join(authors) if len(authors) <= 2 else authors[0] + ' et al.'


def pill_word(state, kind):
    return 'waiting' if state == 'open' and kind == 'PR' else state


NOTE_LINE = re.compile(r'<text class="note" x="([\d.]+)" y="([\d.]+)">(.*?)</text>', re.S)
NOTE_STEP = 14                       # note lines (draw.py): 11px italic, 14px apart


def _plain(markup):
    import html
    return html.unescape(re.sub(r'<title>.*?</title>|<[^>]+>', '', markup, flags=re.S))


def blocks_stated(svg):
    """{(a, b)}: the blocks the picture states, "a blocked by b": a drawn `blocked by` arrow, or one in the metadata's nopath list (a
    true block the picture could not draw)."""
    import svgmeta
    out = set()
    for ln in svg.split('\n'):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at and at[2] == 'blocked by':
            out.add(at[:2])
    for e in (svgmeta.read(svg) or {}).get('nopath', []):
        if isinstance(e, dict) and e.get('kind') == 'blocked by':
            out.add((e.get('from'), e.get('to')))
    return out


def blocker_holds(n, b, records, stated):
    """Whether #b still blocks box n, as far as #b goes: True, False, or None when not known (#b is not a box with a record). Over
    when #b is closed, and also while #b is open when GitHub no longer links #b as a blocker of n (n's record knows its links) and
    the picture states no such block either (blocks_stated): the link was removed, so the note's claim is stale. A block known only
    from a text has its arrow (or a nopath entry) and keeps its claim."""
    rb = records.get(b) or {}
    if not rb.get('state') or rb.get('missing'):
        return None
    if rb['state'] not in ('open', 'draft'):
        return False
    rel = (records.get(n) or {}).get('rel')
    if rel is not None and b not in (rel.get('blockedBy') or []) and (n, b) not in stated:
        return False
    return True


def reblock(blk, box_open, blocker_open, repo, live):
    """The box markup with every "Blocked by" note rewritten by rules.blocked_notes: one line per blocker, bold while that block
    holds, struck through once the box or that blocker is closed. A note is the run of note lines from one that starts a sentence to
    the one that ends it ('.'); a "Blocked by" or "Was blocked by" line always starts one. The lines below a rewritten note move by
    the change in height. Returns (markup, dy: the change in height, the notes changed as plain text)."""
    import draw, html, rules
    lines = list(NOTE_LINE.finditer(blk))
    if not lines:
        return blk, 0, []
    starts = re.compile(r'(?:was\s+)?blocked\s+by\b', re.I)
    paras, cur = [], []
    for m in lines:
        t = _plain(m.group(3)).strip()
        if cur and starts.match(t):
            paras.append(cur)
            cur = []
        cur.append(m)
        if t.endswith('.'):
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    links = r'<a href="https://github\.com/[^"]+/(issues|pull)/(\d+)"[^>]*>(?:<title>(.*?)</title>)?'

    def below(s, ymin, d):                                       # move by d what lies at or below ymin (not a pill or cross on top)
        if not d:
            return s
        return re.sub(r'\b(y|y1|y2)="(-?[\d.]+)"',
                      lambda m: '%s="%s"' % (m.group(1), fmt(float(m.group(2)) + d)) if float(m.group(2)) >= ymin else m.group(0), s)

    top = float(lines[0].group(2))                               # the notes start here: what lies above (pill, cross) never moves
    out, pos, dy, changed = '', 0, 0, []
    for para in paras:
        text = ' '.join(_plain(m.group(3)).strip() for m in para)
        if not starts.match(text):
            continue
        known = dict(live)                                       # kinds and tooltips of items that are not boxes: from the links drawn
        for kind, n, tip in re.findall(links, ''.join(m.group(3) for m in para)):
            known.setdefault(int(n), {'kind': 'PR' if kind == 'pull' else 'ISSUE', 'title': html.unescape(tip or '')})
        notes = rules.blocked_notes(text, box_open, blocker_open)
        rows = [r for nt in notes for r in draw.wrap_px(nt, 'italic', 11)]
        x, y0 = para[0].group(1), float(para[0].group(2))
        new = '\n'.join('<text class="note" x="%s" y="%s">%s</text>' % (x, fmt(y0 + dy + NOTE_STEP * k), _rich(r, repo, known))
                        for k, r in enumerate(rows))
        if new != below(blk[para[0].start():para[-1].end()], y0, dy):
            changed.append(' | '.join(n.replace('**', '*').replace('~~', '~') for n in notes))
        out += below(blk[pos:para[0].start()], top, dy) + new
        pos = para[-1].end()
        dy += (len(rows) - len(para)) * NOTE_STEP
    out += below(blk[pos:], top, dy)
    return (out, dy, changed) if changed else (blk, 0, [])


def grow(blk, dy):
    return re.sub(r'(<rect x="[\d.]+" y="[\d.]+" width="(?:260|252)(?:\.0)?" height=")([\d.]+)(" rx="(?:10|7)")',
                  lambda m: m.group(1) + fmt(float(m.group(2)) + dy) + m.group(3), blk, count=2)


def apply(svg, live, repo, boxes_live=None):
    """Two passes. The boxes as drawn (a collapsed box gets only what its compact form shows: colour, pill, assignee), then the
    pop-ups of the collapsed boxes, which are full copies that float over the picture: they get every edit and need no room."""
    log, report, bands = [], [], []
    svg = _apply(svg, live, repo, log, report, False, bands)
    if bands:                         # boxes whose Blocked by lines had no room: a band of free space under each, then once more
        for num, more in bands:
            svg = make_room(svg, num, more, log, report)
        svg = _apply(svg, live, repo, log, report, False)
    svg = _apply(svg, live, repo, log, report, True)
    tips = retitle_links(svg, live, repo)
    if tips != svg:
        log.append('link tooltips: titles brought up to date')
        svg = tips
    return svg, log, sorted(set(report))


def make_room(svg, num, more, log, report):
    """A band of `more` px of free space (band.py) just under box num: below its bottom, above the next box under it in its column and
    inside its own frame, at the first y that cuts no box, label or jump arc. The box can then grow; nothing else changes shape."""
    import band
    bl = blocks(svg)
    if num not in bl:
        return svg
    x, y, w, h = rect_of(svg[bl[num][0]:bl[num][1]])
    hi = min([ry for n, (a, b) in bl.items() if n != num for rx, ry, rw, rh in [rect_of(svg[a:b])]
              if rx < x + w and rx + rw > x and ry >= y + h] + [1e18])
    own = [f for f in frames_of(svg) if f[0] <= x and x + w <= f[0] + f[2] and f[1] <= y and y + h <= f[1] + f[3]]
    if own:
        hi = min(hi, min(f[1] + f[3] for f in own))
    at = band.free_y(svg, y + h + 0.5, hi)
    if at is None:
        report.append('#%d: needs %dpx more room below it and no band fits under it: move boxes, then refresh again' % (num, more))
        return svg
    log.append('#%d: a band of %dpx inserted at y %s to make room (everything below moved down)' % (num, more, fmt(at)))
    return band.insert(svg, at, more)


def _apply(svg, live, repo, log, report, pop, bands=None):
    bl = blocks(svg, pop)
    stated = blocks_stated(svg)
    room_below_ = (lambda *a: True) if pop else room_below       # a pop-up grows over the picture: nothing to push
    for num in sorted(bl):
        l = live.get(num)
        if not l or l.get('missing'):
            continue
        a, b = bl[num]
        blk = svg[a:b]
        before = blk
        compact = (not pop) and 'data-collapsed="1"' in blk       # the small form has no date line, merge line or notes
        tag = '#%d%s' % (num, ' (pop-up)' if pop else '')
        kind = l['kind']
        want = pill_word(l['state'], kind)
        have = (re.findall(r'>(open|closed|merged|waiting|draft)<', blk) or ['?'])[-1]
        x, y, w, h = rect_of(blk)
        if 'url(#stripes' in blk:
            if want != 'closed':
                report.append('#%d: closed pull request (stripes) is now %s: restyle by hand' % (num, want))
            continue
        if kind == 'PR' and l['state'] == 'closed':
            report.append('#%d: pull request closed without merging: needs stripes, red cross and a supersedes or work-done-by arrow' % num)
            continue
        if have != want and have in STY and want in STY:
            f0, s0, p0, w0, d0 = STY[have]
            f1, s1, p1, w1, d1 = STY[want]
            blk = blk.replace('fill="%s" stroke="%s" stroke-width="1.6"%s' % (f0, s0, DASH if d0 else ''),
                              'fill="%s" stroke="%s" stroke-width="1.6"%s' % (f1, s1, DASH if d1 else ''), 1)   # no closing '/>': a collapsed rect has more attributes
            blk = blk.replace('style="fill:%s' % s0, 'style="fill:%s' % s1)                    # the kind text, which holds the assignee
            blk = blk.replace('stroke="%s" stroke-opacity="0.35"' % s0, 'stroke="%s" stroke-opacity="0.35"' % s1)
            blk = re.sub(r'<rect x="[\d.]+" y="([\d.]+)" width="%s" height="20" rx="10" fill="%s"/>' % (re.escape(fmt(w0)), p0),
                         lambda m: '<rect x="%s" y="%s" width="%s" height="20" rx="10" fill="%s"/>' % (fmt(x + 248 - w1), m.group(1), fmt(w1), p1), blk, count=1)
            blk = re.sub(r'(<text class="pill" x=")[\d.]+(" y="[\d.]+" text-anchor="middle" style="fill:)%s(">)%s' % (f0, have),
                         lambda m: m.group(1) + fmt(x + 248 - w1 / 2) + m.group(2) + f1 + m.group(3) + want, blk, count=1)
            log.append('%s: pill %s -> %s' % (tag, have, want))
        elif have != want:
            report.append('#%d: pill %s, GitHub says %s: not patched' % (num, have, want))
            continue
        # date line (the small form of a collapsed box has none)
        mm = None if compact else re.search(r'(<text class="meta" x="[\d.]+" y="([\d.]+)">opened )([\d-]+)( %s )(still open|closed [\d-]+|merged [\d-]+|draft[^<]*)(</text>)' % DOT, blk)
        if mm:
            new = ('merged ' + l['mergedAt']) if l['state'] == 'merged' else ('closed ' + l['closedAt']) if l['state'] == 'closed' else 'still open'
            opened = l.get('createdAt') or mm.group(3)              # dates in the reader's zone (refresh_meta.local_day)
            if (mm.group(3), mm.group(5)) != (opened, new):
                blk = blk[:mm.start(3)] + opened + mm.group(4) + new + blk[mm.end(5):]
                log.append('%s: date line "opened %s %s" -> "opened %s %s"' % (tag, mm.group(3), mm.group(5), opened, new))
            meta_y = float(mm.group(2))
        else:
            meta_y = None
            if not compact:
                report.append('#%d: no date line found' % num)
        # merge line
        if kind == 'PR' and l['state'] == 'merged' and l.get('mergeSha') and meta_y is not None:
            text = 'merge %s (%s)' % (l['mergeSha'], authors_text(l['authors'])) if l['authors'] else 'merge %s' % l['mergeSha']
            mono = re.search(r'(<text class="mono" x="[\d.]+" y="[\d.]+">)([^<]*)(</text>)', blk)
            if mono:
                pass          # an existing merge line is kept: the diagram's author list may follow a convention that GitHub data does not carry
            else:
                tail = re.search(r'<text class="meta" x="([\d.]+)" y="%s">[^<]*</text>' % re.escape(mm.group(2)), blk)
                if not room_below_(svg, bl, num, 14):
                    report.append('#%d: merge line needs 14px more room below the box: rebuild or move boxes' % num)
                else:
                    blk = re.sub(r'(<text class="note" x="[\d.]+" y=")([\d.]+)(")', lambda m: m.group(1) + fmt(float(m.group(2)) + 14) + m.group(3), blk)
                    ins = '\n<text class="mono" x="%s" y="%s">%s</text>' % (tail.group(1), fmt(meta_y + 14), text)
                    blk = blk[:tail.end()] + ins + blk[tail.end():]
                    blk = grow(blk, 14)
                    log.append('%s: merge line added, box 14px taller' % tag)
        # a closing pull request that is a box
        if not compact and kind == 'ISSUE' and l['state'] == 'closed' and 'Closed by' not in re.sub(r'<[^>]+>', '', blk):
            prs = [p for p in l.get('rel', {}).get('closedBy', []) if p in live and p != num]
            # under the last note; a box with no note yet: under its date line or merge line (the lowest line of text)
            notes = (list(re.finditer(r'<text class="note" x="([\d.]+)" y="([\d.]+)"', blk)) or
                     sorted(re.finditer(r'<text class="(?:meta|mono)" x="([\d.]+)" y="([\d.]+)"', blk), key=lambda m: float(m.group(2))))
            if prs:
                if not room_below_(svg, bl, num, 14):
                    report.append('#%d: closed by PR #%s: note line needs 14px more room below the box' % (num, prs[0]))
                elif not notes:
                    report.append('#%d: closed by PR #%s: no line of text to put the note under' % (num, prs[0]))
                else:
                    last = notes[-1]
                    end = blk.index('</text>', last.start()) + len('</text>')
                    line = '\n<text class="note" x="%s" y="%s">Closed by PR %s.</text>' % (
                        last.group(1), fmt(float(last.group(2)) + 14), ' and '.join(link(repo, p, True, live[p]['title']) for p in prs[:2]))
                    blk = grow(blk[:end] + line + blk[end:], 14)
                    log.append('%s: note "Closed by PR #%s." added, box 14px taller' % (tag, prs[0]))
        # the red cross on a closed issue: closed by hand, the work not done (rules.close_verdict decides, refresh_meta.py stores it)
        if kind == 'ISSUE' and l['state'] == 'closed' and l.get('closeVerdict'):
            v, why = l['closeVerdict']
            crossed = bool(re.search(r'<line [^>]*stroke="#ff2a2a"', blk))
            if v == 'done' and crossed:
                blk = re.sub(r'\n?<line [^>]*stroke="#ff2a2a"[^>]*/>', '', blk)
                log.append('%s: red cross removed (%s)' % (tag, why))
            elif v == 'hand' and not crossed:
                pm = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="[\d.]+" height="20" rx="10" fill="#4e4b48"/>\n<text class="pill"[^\n]*', blk)
                if pm:
                    kx, ky = float(pm.group(1)) - 13, float(pm.group(2)) + 10
                    cross = ''.join('\n<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#ff2a2a" stroke-width="2.8" stroke-linecap="round"/>' % (
                        fmt(kx + s1 * 6), fmt(ky - 6), fmt(kx - s1 * 6), fmt(ky + 6)) for s1 in (-1, 1))
                    blk = blk[:pm.end()] + cross + blk[pm.end():]
                    log.append('%s: red cross added (%s)' % (tag, why))
                else:
                    report.append('#%d: closed by hand (%s) but no closed pill found to put the cross beside' % (num, why))
            elif v == 'ask' and not pop:
                report.append('ASK #%d: %s; %s now. Read its last comments, ask the user when they do not say, then: '
                              'rules.py closed IN.svg %d hand|done "reason"' % (num, why, 'red cross' if crossed else 'no cross', num))
        # assignee label
        if kind == 'ISSUE':
            names = l.get('assignees') or []
            label = '?' if not names else names[0] + (' +%d' % (len(names) - 1) if len(names) > 1 else '')
            esc_label = label.replace('&', '&amp;').replace('<', '&lt;')
            new_blk, old_label = box_header.set_who(blk, esc_label)          # the login is a tspan of the kind text (box_header.py)
            if old_label is None:
                am = re.search(r'(<text class="meta" x="[\d.]+" y="[\d.]+" style="fill:#[0-9a-f]{6};font-size:11.5px;font-weight:600">)([^<]*)(</text>)', blk)
                if am:                                                          # a box still drawn the old way: run box_header.py restyle
                    new_blk, old_label = blk[:am.start(2)] + esc_label + blk[am.end(2):], am.group(2)
                    report.append('#%d: drawn the old way (separate arrow and name): run box_header.py restyle' % num)
            if old_label is not None and old_label != esc_label:
                blk = new_blk
                log.append('%s: assignee %s -> %s' % (tag, old_label, label))
        # the first line, on EVERY box: a login (or a wider pill) may no longer end before the pill. Only that is fixed: a header on
        # two lines that would fit on one again stays (harmless; the box and its pop-up keep the same form)
        fit, n0, n1 = box_header.refit(blk)
        if n1 is not None and n1 > n0:
            if compact:                                                 # the keywords sit under the first line: collapse.py places them
                report.append('#%d: its first line needs %d line(s) on a collapsed box: run collapse.py --set %d="<its keywords>" '
                              'again' % (num, n1, num))
            else:                                                       # a full box has room: the second line sits above the title
                blk = fit
                log.append('%s: first line on %d line(s) (%s)' % (tag, n1, box_header.who_of(blk)))
        # title: a full box or a pop-up shows it (a collapsed box shows its keywords); rewrapped as draw.py wraps it (12.5px, 232px)
        if not compact and l.get('title'):
            nb, dy, msg = retitle(blk, l['title'], repo, live)
            if msg and dy > 0 and not room_below_(svg, bl, num, dy + rect_of(blk)[3] - h):     # with what this box grew already
                report.append('#%d: new title needs %dpx more room below the box: move boxes, then refresh again' % (num, dy))
            elif msg:
                blk = nb
                log.append('%s: %s' % (tag, msg))
        # "Blocked by" notes, on EVERY box at each refresh (a blocker that closes changes the boxes it blocked, which GitHub does not
        # mark as updated): one line per blocker, bold while that block holds, struck once the box or that blocker is closed, or
        # once GitHub and the picture no longer state that block (blocker_holds)
        if not compact:
            holds = lambda b, n=num: blocker_holds(n, b, live, stated)
            nb, dyb, what = reblock(blk, l['state'] in ('open', 'draft'), holds, repo, live)
            if what:
                more = max(dyb, 0)                                      # fewer lines: the box keeps its height
                if more and not room_below_(svg, bl, num, more + rect_of(blk)[3] - h):
                    if bands is not None:                               # apply() inserts a band under it, then runs again
                        bands.append((num, more))
                    else:
                        report.append('#%d: its Blocked by lines need %dpx more room below the box: move boxes, then refresh again' % (num, more))
                else:
                    blk = grow(nb, more) if more else nb
                    log.append('%s: Blocked by lines: %s%s' % (tag, '; '.join(what), (', box %+dpx' % more) if more else ''))
        # report only: things that need thought
        shown = box_header.kind_of(blk)
        if shown and kind == 'ISSUE':
            wantk = 'UMBRELLA' if (l['rel']['children'] or re.search('umbrella', l['title'], re.I)) else 'ISSUE'
            if shown != wantk:
                report.append('#%d: shows %s, the rule says %s: relabel by hand (the tag, the thick border and the inner frame)' % (num, shown, wantk))
        if not compact and want in ('closed', 'merged') and re.search(r'\((?:open|draft)\)', re.sub(r'<[^>]+>', '', blk)):
            report.append('#%d: a note still says "(open)" or "(draft)": edit the note' % num)
        if blk != before:
            svg = svg[:a] + blk + svg[b:]
            if not pop and rect_of(blk)[3] > h:            # the box grew: the arrows that come in from below follow its bottom edge
                svg = follow_bottom(svg, (x, y, w, h), rect_of(blk)[3] - h)
            bl = blocks(svg, pop)          # offsets moved
    return svg
