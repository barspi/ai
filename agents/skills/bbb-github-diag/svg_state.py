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
arrow), a kind change (ISSUE to UMBRELLA), a changed title, stale note text such as `Fix in PR #N (open)`.

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
    for m in re.finditer(r'<g id="pop(\d+)" class="pop">' if pop else r'<g id="n(\d+)">', svg):
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


def room_below(svg, bl, num, dy):
    """True when the box can grow by dy: no other box in the way and still inside its frame."""
    x, y, w, h = rect_of(svg[bl[num][0]:bl[num][1]])
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


def authors_text(authors):
    return ', '.join(authors) if len(authors) <= 2 else authors[0] + ' et al.'


def pill_word(state, kind):
    return 'waiting' if state == 'open' and kind == 'PR' else state


def grow(blk, dy):
    return re.sub(r'(<rect x="[\d.]+" y="[\d.]+" width="(?:260|252)(?:\.0)?" height=")([\d.]+)(" rx="(?:10|7)")',
                  lambda m: m.group(1) + fmt(float(m.group(2)) + dy) + m.group(3), blk, count=2)


def apply(svg, live, repo, boxes_live=None):
    """Two passes. The boxes as drawn (a collapsed box gets only what its compact form shows: colour, pill, assignee), then the
    pop-ups of the collapsed boxes, which are full copies that float over the picture: they get every edit and need no room."""
    log, report = [], []
    svg = _apply(svg, live, repo, log, report, False)
    svg = _apply(svg, live, repo, log, report, True)
    return svg, log, sorted(set(report))


def _apply(svg, live, repo, log, report, pop):
    bl = blocks(svg, pop)
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
        mm = None if compact else re.search(r'(<text class="meta" x="[\d.]+" y="([\d.]+)">opened [\d-]+ %s )(still open|closed [\d-]+|merged [\d-]+|draft[^<]*)(</text>)' % DOT, blk)
        if mm:
            new = ('merged ' + l['mergedAt']) if l['state'] == 'merged' else ('closed ' + l['closedAt']) if l['state'] == 'closed' else 'still open'
            if mm.group(3) != new:
                blk = blk[:mm.start(3)] + new + blk[mm.end(3):]
                log.append('%s: date line "%s" -> "%s"' % (tag, mm.group(3), new))
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
            if prs:
                if not room_below_(svg, bl, num, 14):
                    report.append('#%d: closed by PR #%s: note line needs 14px more room below the box' % (num, prs[0]))
                else:
                    notes = list(re.finditer(r'<text class="note" x="([\d.]+)" y="([\d.]+)"', blk))
                    last = notes[-1]
                    end = blk.index('</text>', last.start()) + len('</text>')
                    line = '\n<text class="note" x="%s" y="%s">Closed by PR %s.</text>' % (
                        last.group(1), fmt(float(last.group(2)) + 14), ' and '.join(link(repo, p, True, live[p]['title']) for p in prs[:2]))
                    blk = grow(blk[:end] + line + blk[end:], 14)
                    log.append('%s: note "Closed by PR #%s." added, box 14px taller' % (tag, prs[0]))
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
            bl = blocks(svg, pop)          # offsets moved
    return svg
