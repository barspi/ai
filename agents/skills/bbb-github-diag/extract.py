#!/usr/bin/env python3
"""Cut an extract out of a finished diagram: keep some boxes where they are, with the arrows between them; drop everything else.

usage: extract.py IN.svg OUT.svg --keep N,N,... [--title TEXT] [--tab-title TEXT] [--compact [ANCHOR]] [--no-legend]

Built by selecting from the finished diagram, never by drawing again (SKILL.md, "Extracts"): every kept box, pop-up, link, label and arrow
route is the one the user saw and approved.
1. Every arrow with an end on a box that is not kept goes, with its label (move.take_out). Arrows between kept boxes stay as they are.
2. The boxes that are not kept go, with their pop-ups and hover rules (collapse.remove_boxes).
3. A frame that holds no kept box goes, with its title. A frame that lost boxes shrinks to what it still holds: its kept boxes and the
   arrows that run between two of them, plus the frame's old margins on each side, never beyond its old border (so it cannot run
   into a neighbour). A frame that lost nothing is not touched.
4. Jump arcs and red crosses are redone (hops.py), the canvas shrinks to what is left (the header and the legend stay where they are),
   and the page scripts are the skill's current ones (refresh_scripts.py).
--title replaces the text of the page title (the first line of the header) and of the browser tab (the <title> under the root);
--tab-title gives the tab its own text. --no-legend leaves out the "How to read this graph" block
(the user asked for it when the legend sat over arrows; a handout for someone who knows the work may not need it).
A number in --keep that is not a box of IN is printed and skipped. Run check_diag.py OUT.svg afterwards.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, draw, hops, model, move, refresh_scripts, route, svgmeta


def extract(text, keep, title=None, no_legend=False, tab_title=None):
    """Returns (text, report lines)."""
    report = []
    lines, box, _, _ = collapse.parse(text)
    box0 = dict(box)                                       # the boxes as the full diagram has them (old frame margins)
    missing = sorted(n for n in keep if n not in box)
    keep = set(keep) - set(missing)
    for n in missing:
        report.append('not in the diagram, skipped: #%d' % n)
    where0 = svgmeta.drawn_frames(text)
    # 1. arrows with an end outside the kept set, with their labels
    gone = set()
    for i, ln in enumerate(lines):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if svgmeta.is_arrow(ln) and (not at or at[0] not in keep or at[1] not in keep):
            gone.update(move.take_out(lines, i))
    text = '\n'.join(l for k, l in enumerate(lines) if k not in gone)
    # 2. boxes
    text = collapse.remove_boxes(text, sorted(n for n in box if n not in keep))
    # 3. frames
    lines, box, _, frames = collapse.parse(text)
    sc, _ = model.read(text)
    arrows = [(svgmeta.arrow_of(l), route.straight(model.arrow_points(l))) for l in lines if svgmeta.is_arrow(l) and svgmeta.arrow_of(l)]
    drop = set()
    for f in frames:
        had = [n for n, name in where0.items() if name == f['name']]
        now = [n for n in had if n in keep]
        if not now:
            drop.update((f['rl'], f['tl']))
            report.append('frame dropped (no kept box): %s' % f['name'])
            continue
        if len(now) == len(had):
            report.append('frame kept whole: %s (%d boxes)' % (f['name'], len(now)))
            continue
        xs, ys = [], []
        for n in now:
            b = box[n]
            xs += [b['x'], b['x'] + b['w']]
            ys += [b['y'], b['y'] + b['h']]
        for at, p in arrows:
            if at[0] in now and at[1] in now:
                xs += [x for x, _ in p]
                ys += [y for _, y in p]
        # the old margins: from the old frame border to its old boxes, each side
        x, y, w, h = f['x'], f['y'], f['w'], f['h']
        ob = [b0 for n, b0 in box0.items() if n in had]
        ml = min(MARGIN, min(b0['x'] for b0 in ob) - x)          # capped: an old frame may have kept room for boxes that are gone
        mr = min(MARGIN, x + w - max(b0['x'] + b0['w'] for b0 in ob))
        mt = min(b0['y'] for b0 in ob) - y                         # the top margin holds the frame title: kept as it was
        mb = min(MARGIN, y + h - max(b0['y'] + b0['h'] for b0 in ob))
        nx0, ny0 = max(x, min(xs) - ml), max(y, min(ys) - mt)
        nx1, ny1 = min(x + w, max(xs) + mr), min(y + h, max(ys) + mb)
        r = lines[f['rl']]
        for k, v in (('x', nx0), ('y', ny0), ('width', nx1 - nx0), ('height', ny1 - ny0)):
            r = re.sub(r'\b%s="[\d.-]+"' % k, '%s="%s"' % (k, collapse.fmt(v)), r, count=1)
        lines[f['rl']] = r
        lines[f['tl']] = move.shift_line(lines[f['tl']], nx0 - x, ny0 - y)
        report.append('frame shrunk: %s (%d of %d boxes)' % (f['name'], len(now), len(had)))
    text = '\n'.join(l for k, l in enumerate(lines) if k not in drop)
    if no_legend and '<!--legend-->' in text:               # its markers stay (empty), so later scripts still find its place
        text = re.sub(r'(<!--legend-->).*?(<!--/legend-->)', r'\1\n\2', text, count=1, flags=re.S)
        report.append('legend left out')
    # 4. arcs, crosses, title, canvas, scripts
    text, _, _ = hops.add_hops(text)
    if title:
        text = re.sub(r'(<text class="h1"[^>]*>).*?(</text>)', lambda m: m.group(1) + draw.esc(title) + m.group(2), text, count=1, flags=re.S)
    tab = tab_title or title
    if tab:                                                 # the browser tab: the <title> right under the root <svg> (line 2)
        text = re.sub(r'\A(<svg[^>]*>\n)<title>.*?</title>', lambda m: m.group(1) + '<title>%s</title>' % draw.esc(tab), text, count=1, flags=re.S)
    lines, box, _, frames = collapse.parse(text)
    right = [b['x'] + b['w'] for b in box.values()] + [f['x'] + f['w'] for f in frames]
    bottom = [b['y'] + b['h'] for b in box.values()] + [f['y'] + f['h'] for f in frames]
    if '<!--legend-->' in lines:                            # the legend keeps its top; its right edge moves to the drawing's
        a, z = lines.index('<!--legend-->'), lines.index('<!--/legend-->')
        rects = [re.match(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', ln) for ln in lines[a:z]]
        rects = [(float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))) for m in rects if m]
        if rects:
            dx = max(right) - max(x + w for x, _, w, _ in rects)
            if dx < 0:
                lines[a:z] = [move.shift_line(ln, dx, 0) for ln in lines[a:z]]
                rects = [(x + dx, y, w, h) for x, y, w, h in rects]
            right += [x + w for x, _, w, _ in rects]
            bottom += [y + h for _, y, _, h in rects]
        text = '\n'.join(lines)
    W, H = int(max(right) + 60), int(max(bottom) + 60)
    m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)" viewBox="0 0 (\d+) (\d+)"', text)
    text = text.replace(m.group(0), m.group(0).replace('width="%s" height="%s" viewBox="0 0 %s %s"' % m.groups(),
                                                       'width="%d" height="%d" viewBox="0 0 %d %d"' % (W, H, W, H)), 1)
    text = re.sub(r'<rect x="0" y="0" width="[\d.]+" height="[\d.]+"', '<rect x="0" y="0" width="%d" height="%d"' % (W, H), text, count=1)
    meta = svgmeta.read(text)                               # entries about two boxes need both boxes in the extract
    if meta:
        for key in ('nopath', 'accepted'):
            before = meta.get(key) or []
            meta[key] = [e for e in before if not (isinstance(e, dict) and 'from' in e) or (e['from'] in keep and e.get('to') in keep)]
            if len(meta[key]) < len(before):
                report.append('metadata: %d %s entries name a box outside the extract, dropped' % (len(before) - len(meta[key]), key))
        text = svgmeta.write(text, meta)
    report.append('canvas %dx%d, %d boxes, %d arrows' % (W, H, len(box), sum(1 for l in lines if svgmeta.is_arrow(l))))
    return refresh_scripts.refresh(text), report


MARGIN = 60          # the most a shrunk frame keeps between its boxes and its left, right and bottom border

# --compact: the anchor frame moves whole to the top-left; the other frames (satellites) are drawn again, compact, right of it and below it
LEFT = 40            # the anchor frame's left edge
GAP = 260            # between the anchor frame and the satellites: the channel for the arrows that join them
FGAP = 60            # between two satellite frames
COLGAP = 200         # between two columns of boxes inside a satellite (SKILL.md: about 200px between neighbours)
ROWGAP = 50          # between two boxes of one column
FTOP, FSIDE, FBOTTOM = 60, 60, 40   # satellite frame margins (the top one holds the title)


def _shift(line, dx, dy):
    """One line of markup moved by dx, dy: attributes (move.shift_line) and the points of a path."""
    line = move.shift_line(line, dx, dy)
    if line.startswith('<path ') and ' d="' in line:
        d = line.split(' d="', 1)[1].split('"', 1)[0]
        nd = re.sub(r'(-?[\d.]+),(-?[\d.]+)', lambda m: '%s,%s' % (collapse.fmt(float(m.group(1)) + dx), collapse.fmt(float(m.group(2)) + dy)), d)
        line = line.replace(' d="%s"' % d, ' d="%s"' % nd, 1)
    return line


def _canvas(text, W, H):
    m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)" viewBox="0 0 (\d+) (\d+)"', text)
    text = text.replace(m.group(0), m.group(0).replace('width="%s" height="%s" viewBox="0 0 %s %s"' % m.groups(),
                                                       'width="%d" height="%d" viewBox="0 0 %d %d"' % (W, H, W, H)), 1)
    return re.sub(r'<rect x="0" y="0" width="[\d.]+" height="[\d.]+"', '<rect x="0" y="0" width="%d" height="%d"' % (W, H), text, count=1)


def _columns(nums, edges, y_of):
    """Columns of a satellite: the longest chain of its own arrows that reaches each box (layout.py's rule, in small); in a column, boxes
    in the order of y_of (the mean height of the anchor boxes they join, so their arrows cross less)."""
    col = {n: 0 for n in nums}
    for _ in range(len(nums)):
        changed = False
        for a, b in edges:
            if col[b] < col[a] + 1 and col[a] + 1 < len(nums):
                col[b], changed = col[a] + 1, True
        if not changed:
            break
    cols = {}
    for n in nums:
        cols.setdefault(col[n], []).append(n)
    return [sorted(cols[c], key=y_of) for c in sorted(cols)]


def compact(text, anchor=None):
    """Returns (text, report lines). Run on an extract (after extract())."""
    report = []
    lines, box, pop, frames = collapse.parse(text)
    where = svgmeta.drawn_frames(text)
    members = {f['name']: [n for n in box if where.get(n) == f['name']] for f in frames}
    held = [f for f in frames if members[f['name']]]
    if not held:
        return text, ['--compact: no frame holds a kept box, so there is no anchor frame; the extract is left as cut']
    A = next((f for f in held if anchor and f['name'].startswith(anchor)), None) or max(held, key=lambda f: len(members[f['name']]))
    inside = set(members[A['name']])
    arrows = [(i, svgmeta.arrow_of(l)) for i, l in enumerate(lines) if svgmeta.is_arrow(l) and svgmeta.arrow_of(l)]
    # 1. the anchor frame and all it holds (boxes, pop-ups, its own arrows and their labels) move as one piece
    hdr = [float(m.group(1)) for m in re.finditer(r'<text class="h[12]" x="[\d.]+" y="([\d.]+)"', text)]
    dx, dy = LEFT - A['x'], (max(hdr) if hdr else 0) + 50 - A['y']
    idx = {A['rl'], A['tl']}
    for n in inside:
        idx.update(range(box[n]['a'], box[n]['b'] + 1))
        if n in pop:
            idx.update(range(pop[n][0], pop[n][1] + 1))
    for i, at in arrows:
        if at[0] in inside and at[1] in inside:
            idx.update(move.take_out(lines, i))
    for k in idx:
        lines[k] = _shift(lines[k], dx, dy)
    ax0, ay0, ax1, ay1 = LEFT, A['y'] + dy, LEFT + A['w'], A['y'] + dy + A['h']
    report.append('anchor frame moved whole to (%d, %d): %s (%d boxes)' % (ax0, ay0, A['name'], len(inside)))
    # 2. the satellites, drawn again: a compact layout of each, then the frames right of the anchor, then below it
    ycentre = {n: box[n]['y'] + dy + box[n]['h'] / 2 for n in inside}
    sats = []
    free = [n for n in box if not where.get(n)]                # boxes in no frame: a group like a satellite, drawn without a frame
    for f, nums in [(f, members[f['name']]) for f in held if f is not A] + ([(None, free)] if free else []):
        own = [(a, b) for _, (a, b, _) in arrows if a in nums and b in nums]
        link = {n: [ycentre[o] for _, (a, b, _) in arrows for o in ((b,) if a == n else (a,) if b == n else ()) if o in ycentre] for n in nums}
        cols = _columns(nums, own, lambda n: (sum(link[n]) / len(link[n]) if link[n] else 1e9, box[n]['y']))
        pos, x = {}, FSIDE
        for c in cols:
            y = FTOP
            for n in c:
                pos[n] = (x, y)
                y += box[n]['h'] + ROWGAP
            x += max(box[n]['w'] for n in c) + COLGAP
        w = max(x - COLGAP + FSIDE, (collapse.tw(f['name'], 15) + 2 * FSIDE) if f else 0)   # never narrower than its title (ftl, 15px)
        h = max(pos[n][1] + box[n]['h'] for n in nums) + FBOTTOM
        weight = sum(len(link[n]) for n in nums)
        sats.append(dict(f=f, pos=pos, w=w, h=h, weight=weight))
    sats.sort(key=lambda s: -s['weight'])                     # the most joined to the anchor go nearest its top-right
    # the legend first, at the top of the right column
    leg = None
    if '<!--legend-->' in lines:
        a, z = lines.index('<!--legend-->'), lines.index('<!--/legend-->')
        rr = [re.match(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', ln) for ln in lines[a:z]]
        rr = [tuple(float(v) for v in m.groups()) for m in rr if m]
        if rr:
            lx, ly = min(r[0] for r in rr), min(r[1] for r in rr)
            lw, lh = max(r[0] + r[2] for r in rr) - lx, max(r[1] + r[3] for r in rr) - ly
            leg = (a, z, lx, ly, lw, lh)
    rx, ry = ax1 + GAP, ay0
    if leg:
        a, z, lx, ly, lw, lh = leg
        lines[a:z] = [move.shift_line(ln, rx - lx, ry - ly) for ln in lines[a:z]]
        ry += lh + FGAP
    bx, by = ax0, ay1 + GAP
    moves, col_right = {}, rx
    for s in sats:
        f = s['f']
        if ry + s['h'] <= ay1 + GAP / 2:                      # the right column, as far down as the anchor frame reaches
            fx, fy = rx, ry
            ry += s['h'] + FGAP
            col_right = max(col_right, rx + s['w'])
        else:                                                  # then the row below
            fx, fy = bx, by
            bx += s['w'] + FGAP
        if f:
            r = lines[f['rl']]
            for k, v in (('x', fx), ('y', fy), ('width', s['w']), ('height', s['h'])):
                r = re.sub(r'\b%s="[\d.-]+"' % k, '%s="%s"' % (k, collapse.fmt(v)), r, count=1)
            lines[f['rl']] = r
            lines[f['tl']] = move.shift_line(lines[f['tl']], fx - f['x'], fy - f['y'])
        for n, (px, py) in s['pos'].items():
            moves[n] = (fx + px, fy + py)
        report.append('satellite drawn again at (%d, %d), %dx%d: %s (%d boxes)' % (fx, fy, s['w'], s['h'], f['name'] if f else '(boxes in no frame)', len(s['pos'])))
    if leg and col_right > rx + leg[4]:                        # the legend's right edge on the right column's (check_diag.py: top right)
        a, z = leg[0], leg[1]
        lines[a:z] = [move.shift_line(ln, col_right - rx - leg[4], 0) for ln in lines[a:z]]
        rx = col_right - leg[4]
    text = '\n'.join(lines)
    # 3. every arrow with an end on a satellite box is routed again in the new picture (move.py: the most important first), then
    #    one improve pass over them (reroute.py: a cheaper path, a jog under 30px counts against a path)
    text, routed, failed, _ = move.move(text, moves)
    import reroute
    text, _, _ = hops.add_hops(text, marks=False)
    text, better, _ = reroute.reroute(text, [(a, b) for a, b, _, _ in routed], improve=True)
    if better:
        report.append('%d of them improved by a second pass' % len(better))
    text, _, _ = hops.add_hops(text)
    text, _, bad = model.relabel(text, hop_pad=20)
    report.append('%d arrows routed again, %d with no path (left out, in nopath)' % (len(routed), len(failed)))
    for a, b, why in failed:
        report.append('NO PATH #%d -> #%d: %s' % (a, b, why))
    for x, y, why in bad:
        report.append('label near (%d,%d): %s' % (x, y, why))
    lines, box, _, frames = collapse.parse(text)
    right = [b['x'] + b['w'] for b in box.values()] + [f['x'] + f['w'] for f in frames] + ([rx + leg[4]] if leg else [])
    bottom = [b['y'] + b['h'] for b in box.values()] + [f['y'] + f['h'] for f in frames] + ([ay0 + leg[5]] if leg else [])
    for ln in lines:
        if svgmeta.is_arrow(ln):
            p = model.arrow_points(ln)
            right += [x for x, _ in p]
            bottom += [y for _, y in p]
    W, H = int(max(right) + 60), int(max(bottom) + 60)
    report.append('canvas %dx%d' % (W, H))
    return refresh_scripts.refresh(_canvas(text, W, H)), report


def main():
    argv = sys.argv[1:]
    if '--keep' not in argv or len(argv) < 4:
        sys.exit(__doc__)
    keep = [int(x.lstrip('#')) for x in re.split(r'[,\s]+', argv[argv.index('--keep') + 1]) if x]
    title = argv[argv.index('--title') + 1] if '--title' in argv else None
    anchor = argv[argv.index('--compact') + 1] if '--compact' in argv and argv.index('--compact') + 1 < len(argv) \
        and not argv[argv.index('--compact') + 1].startswith('--') else None
    pos = [a for i, a in enumerate(argv) if not a.startswith('--') and (i == 0 or argv[i - 1] not in ('--keep', '--title', '--compact', '--tab-title'))]
    src, out = pos[0], pos[1]
    text = open(src, encoding='utf-8').read()
    tab = argv[argv.index('--tab-title') + 1] if '--tab-title' in argv else None
    res, report = extract(text, keep, title, '--no-legend' in argv, tab)
    if '--compact' in argv:
        res, more = compact(res, anchor)
        report += more
    open(out, 'w', encoding='utf-8').write(res)
    for r in report:
        print(r)
    print('next: check_diag.py %s' % out)


if __name__ == '__main__':
    main()
