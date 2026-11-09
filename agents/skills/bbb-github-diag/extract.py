#!/usr/bin/env python3
"""Cut an extract out of a finished diagram: keep some boxes where they are, with the arrows between them; drop everything else.

usage: extract.py IN.svg OUT.svg --keep N,N,... [--title TEXT]

Built by selecting from the finished diagram, never by drawing again (SKILL.md, "Extracts"): every kept box, pop-up, link, label and arrow
route is the one the user saw and approved.
1. Every arrow with an end on a box that is not kept goes, with its label (move.take_out). Arrows between kept boxes stay as they are.
2. The boxes that are not kept go, with their pop-ups and hover rules (collapse.remove_boxes).
3. A frame that holds no kept box goes, with its title. A frame that lost boxes shrinks to what it still holds: its kept boxes and the
   arrows that run between two of them, plus the frame's old margins on each side, never beyond its old border (so it cannot run
   into a neighbour). A frame that lost nothing is not touched.
4. Jump arcs and red crosses are redone (hops.py), the canvas shrinks to what is left (the header and the legend stay where they are),
   and the page scripts are the skill's current ones (refresh_scripts.py).
--title replaces the text of the page title (the first line of the header).
A number in --keep that is not a box of IN is printed and skipped. Run check_diag.py OUT.svg afterwards.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse, draw, hops, model, move, refresh_scripts, route, svgmeta


def extract(text, keep, title=None):
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
    # 4. arcs, crosses, title, canvas, scripts
    text, _, _ = hops.add_hops(text)
    if title:
        text = re.sub(r'(<text class="h1"[^>]*>).*?(</text>)', lambda m: m.group(1) + draw.esc(title) + m.group(2), text, count=1, flags=re.S)
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


def main():
    argv = sys.argv[1:]
    if '--keep' not in argv or len(argv) < 4:
        sys.exit(__doc__)
    keep = [int(x.lstrip('#')) for x in re.split(r'[,\s]+', argv[argv.index('--keep') + 1]) if x]
    title = argv[argv.index('--title') + 1] if '--title' in argv else None
    pos = [a for i, a in enumerate(argv) if not a.startswith('--') and (i == 0 or argv[i - 1] not in ('--keep', '--title'))]
    src, out = pos[0], pos[1]
    text = open(src, encoding='utf-8').read()
    res, report = extract(text, keep, title)
    open(out, 'w', encoding='utf-8').write(res)
    for r in report:
        print(r)
    print('next: check_diag.py %s' % out)


if __name__ == '__main__':
    main()
