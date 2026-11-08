#!/usr/bin/env python3
"""Build a lineage diagram from a graph description. Use it for the first revision of a diagram (see SKILL.md, "First revision").

usage: build.py graph.json out.svg

graph.json (the example next to the sample: example/sample-graph.json):
{ "repo": "owner/name",
  "title": "text for the page title; #N becomes a link",
  "date": "2026-03-22",                                    (the date the facts were read)
  "reading": "optional second header line",                (default: how to read the arrows)
  "nodes": [ {"num": 123, "state": "open|closed|handclosed|merged|waiting|draft|prclosed",
              "title": "...", "meta": "opened 2026-01-05 · still open", "notes": ["line", ...], "mono": "merge abc1234 (a, b)",
              "assignees": ["login"]  (issue)   "author": "login"  (pull request),
              "umbrella": true, "new": true, "frame": "name of the dotted frame", "collapsed": "keywords (on request only)",
              "github": {...the box's record from refresh_meta.py; graph_from_snapshot.py fills it}} ],
  "edges": [ {"from": 10, "to": 12, "kind": "closed by"} ],        (kinds: the arrow vocabulary in SKILL.md; read A, kind, B)
  "meta": {"ignored": [...], "decisions": [...], "notes": "...", "lastRun": "..."} }   (optional: the svgmeta.py block)

The SVG it writes is the diagram's only file from then on: each box carries its frame and GitHub record, each arrow its two boxes and
its kind, and the <metadata> block the rest (svgmeta.py); an arrow with NO PATH goes into the block's "nopath". graph.json is a working
file for this one build: do not keep it.

What it does, with the skill's own modules and nothing else: layout.py puts the boxes in columns and rows and draws the easy arrows;
route.py finds a path for every other arrow in the picture as it is; hops.py draws the jump arcs; collapse.py collapses the boxes
that have "collapsed"; the legend, the header and the find box are written here. It prints what it could not route or label: say so
to the user, and do not draw such an arrow worse by hand. Then run check_diag.py. A box needs no x or y: the layout decides.
"""
import json, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import draw, layout, route, hops, collapse, svgmeta
from fonts import load


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    spec = json.load(open(sys.argv[1], encoding='utf-8'))
    out_path = sys.argv[2]
    if not spec.get('repo'):
        sys.exit('graph.json needs "repo": "owner/name"')
    nodes = spec['nodes']
    nums = [n['num'] for n in nodes]
    prs = {n['num'] for n in nodes if draw.STY[n['state']]['kind'] == 'PR'}
    ctx = draw.Ctx(spec['repo'], {n['num']: n['title'] for n in nodes}, prs)
    edges = []
    for e in spec.get('edges', []):
        if e['kind'] not in draw.EDGE:
            sys.exit('unknown arrow word "%s": use one of %s' % (e['kind'], ', '.join(draw.EDGE)))
        if e['from'] not in nums or e['to'] not in nums:
            sys.exit('arrow %s -> %s names a box that is not in "nodes"' % (e['from'], e['to']))
        edges.append((e['from'], e['to'], e['kind']))

    ftl = load('italic', 60)
    pl_nodes = [dict(num=n['num'], h=draw.box_height(n), frame=n.get('frame'), collapsed=((collapse.HC_TWO if draw.two_lines(ctx, n) else collapse.HC) if n.get('collapsed') else False),
                     title_w=(ftl.getlength(n['frame']) / 4 if n.get('frame') else 0)) for n in nodes]
    if any(n.get('frame') for n in nodes):        # frames are blocks: laid out inside, then packed; the root forks into them
        P = layout.plan_blocks(pl_nodes, edges, spec.get('roots') or ())
    else:
        P = layout.plan(pl_nodes, edges)
    rect = P['rect']

    # ---------------------------------------------------------------- boxes (full size; collapse.process shrinks the collapsed ones)
    boxes, natural = [], {}
    for n in nodes:
        x, y, w, h = rect[n['num']]
        mk, hh = draw.box(ctx, n, x, y, min_h=0 if n.get('collapsed') else h)
        boxes.append(mk)
        natural[n['num']] = hh

    # ---------------------------------------------------------------- page
    right = P['right']
    LX = right + 60
    W = max(int(LX + draw.LEGEND_W + 60), 1500)
    kinds = {k for _, _, k in edges}
    states = {n['state'] for n in nodes}
    leg, leg_h = draw.legend(LX, layout.TOP, kinds, states)
    H = int(max(P['bottom'], layout.TOP + leg_h) + 80)
    reading = spec.get('reading') or 'Arrows point from the earlier item to the item it produced, or from an issue to the pull request that closed it. Read left to right.'
    head = [
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="%d" height="%d" viewBox="0 0 %d %d" font-family="Helvetica Neue, Helvetica, Arial, sans-serif">' % (W, H, W, H),
        '<title>%s</title>' % draw.esc(re.sub(r'\s+', ' ', spec.get('title', 'Lineage diagram'))),
        '<desc>%s</desc>' % draw.esc(spec.get('desc', 'Issues and pull requests of %s: what spawned, closed or replaced what.' % spec['repo'])),
        draw.defs(),
        '<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (W, H, draw.PAGE),
        '<text class="h1" x="80" y="70">%s</text>' % ctx.rich(spec.get('title', 'Lineage diagram')),
        '<text class="h2" x="80" y="100"><tspan style="font-weight:700">Repository: %s</tspan></text>' % draw.esc(spec['repo']),
        '<text class="h2" x="80" y="124">%s</text>' % draw.esc(reading),
        '<text class="h2" x="80" y="148">Facts as of %s. Dotted frames name an area of work only; the arrows carry the relationships.</text>' % draw.esc(spec.get('date', '')),
    ]
    frame_lines = []
    for name, fx, fy, fw, fh in P['frames']:
        frame_lines += draw.frame(fx, fy, fw, fh, name)
    script = open(os.path.join(HERE, 'find-box.js'), encoding='utf-8').read()
    text = '\n'.join(head + frame_lines + ['<!--ARROWS-->'] + boxes + ['<!--LABELS-->', '<!--legend-->'] + leg + ['<!--/legend-->',
                     '<script type="text/javascript"><![CDATA[\n' + script + '\n]]></script>', '</svg>', ''])

    # ---------------------------------------------------------------- collapsed boxes, on request only
    sets = {n['num']: n['collapsed'] for n in nodes if n.get('collapsed')}
    if sets:
        text, log = collapse.process(text, sets)
        lines = text.split('\n')
        for n in sets:
            collapse.set_height(lines, n, rect[n][3])       # collapse.process only knows 62px or what arrows ask for
        text = '\n'.join(lines)

    # ---------------------------------------------------------------- arrows and labels
    pills = [(rect[n['num']][0] + 3 - 26, rect[n['num']][1] + 3 - 26, 52, 52) for n in nodes if n.get('new')]
    titles = [(fx, fy, fw_title + 32, 30) for (name, fx, fy, fw, fh), fw_title in ((f, ftl.getlength(f[0]) / 4) for f in P['frames'])]
    sc = route.Scene(rect, [(f[1], f[2], f[3], f[4]) for f in P['frames']], titles, pills, [], bounds=(30, layout.TOP - 25, LX - 25, int(P['bottom']) + 60))
    arrow_lines, label_lines, problems, nopath = [], [], [], []

    def add(a, b, kind, pts):
        sc.arrows.append(list(pts))
        arrow_lines.append(draw.arrow(pts, kind, a, b))

    easy = P['easy']
    for a, b, kind, pts in easy:
        add(a, b, kind, pts)
    placed = []
    for a, b, kind, pts in easy:
        lab = route.place_label(sc, pts, kind)
        if lab:
            sc.add([], kind, lab)
            sc.arrows.pop()
            label_lines += draw.label(kind, *lab)
        else:
            problems.append('no free straight stretch for the label of #%s %s #%s' % (a, kind, b))

    def span(e):
        ra, rb = rect[e[0]], rect[e[1]]
        return -(abs(ra[0] - rb[0]) + abs(ra[1] - rb[1]))

    # the most important arrows first (draw.IMPORTANCE), each tier longest first: they get the short, simple paths
    for a, b, kind in sorted(P['hard'], key=lambda e: (-draw.IMPORTANCE.get(e[2], 2), span(e))):
        pts = route.route(sc, a, b, '*', '*')        # one search over every side of both boxes: fewest bends and crossings win
        if not pts:
            problems.append('NO PATH for #%s %s #%s: kept in the metadata ("nopath"); name it in the box note, and say what would have to move' % (a, kind, b))
            nopath.append((a, b, kind))
            continue
        add(a, b, kind, pts)
        lab = route.place_label(sc, pts, kind)
        if lab:
            sc.add([], kind, lab)
            sc.arrows.pop()
            label_lines += draw.label(kind, *lab)
        else:
            problems.append('no free straight stretch for the label of #%s %s #%s' % (a, kind, b))

    text = text.replace('<!--ARROWS-->', '\n'.join(arrow_lines)).replace('<!--LABELS-->', '\n'.join(label_lines))
    text, added, removed = hops.add_hops(text)
    import model                                  # the jump arcs exist only now: move every label that sits too near one
    text, moved, failed = model.relabel(text, hop_pad=20)
    for x, y, why in failed:
        problems.append('label near (%d,%d): %s' % (x, y, why))
    import straighten, rules                      # Z-shaped arrows made straight where a box can move; far low arrows from closed work dropped
    st_text, st_done, _, st_problems, st_before, st_after = straighten.straighten(text)
    if st_done and st_after <= st_before:
        text = st_text
        problems += st_problems
        print('straighten: %d arrows made straight' % len(st_done))
    import reroute                                # straightening frees room: an arrow that had to leave its frame tries inside again
    leavers = reroute.leaves_frame(text)
    if leavers:
        before_r = model.repair(text, count_only=True)[1]
        rr, rr_done, _ = reroute.reroute(text, leavers)
        rr, _, _ = hops.add_hops(rr)
        rr, _, _ = model.relabel(rr, hop_pad=20)
        if model.repair(rr, count_only=True)[1] <= before_r:
            text = rr
            print('reroute: %d arrows that left their frame routed again, %d still leave it' % (len(rr_done), len(reroute.leaves_frame(text))))
    if svgmeta.read(text) is None:
        text = svgmeta.write(text, svgmeta.new_meta(spec['repo'], spec.get('roots') or ()))
    for a2, b2, kind2, why2 in rules.far_low(text):
        text = svgmeta.drop(text, a2, b2, 'low importance, from closed work, and too far to draw: %s' % why2)
        print('not drawn: #%s %s #%s (%s)' % (a2, kind2, b2, why2))
    import fit_heights                            # give back the side room the layout reserved and the router did not use
    fitted, changed, _, fit_problems, before, after, _ = fit_heights.fit(text)
    if changed and after <= before:
        text = fitted
        problems += fit_problems
        print('fit_heights: %d collapsed boxes shortened by %.0fpx' % (len(changed), sum(o - h for _, o, h in changed)))
    meta = svgmeta.new_meta(spec['repo'], spec.get('roots') or ())     # the facts with no box or arrow of their own (svgmeta.py)
    meta.update({k: v for k, v in (spec.get('meta') or {}).items() if k not in ('format', 'repo', 'roots')})
    for x in (svgmeta.read(text) or {}).get('nopath', []):             # what the steps above left undrawn (rules.far_low)
        svgmeta.add_nopath(meta, x['from'], x['to'], x['kind'], x['reason'])
    for a, b, kind in nopath:
        svgmeta.add_nopath(meta, a, b, kind, 'no clean path when the diagram was built')
    text = svgmeta.write(text, meta)
    open(out_path, 'w', encoding='utf-8').write(text)
    print('wrote %s: %dx%d, %d boxes, %d arrows (%d by the layout, %d by the router), %d jump arcs' % (
        out_path, W, H, len(nodes), len(arrow_lines), len(easy), len(arrow_lines) - len(easy), added))
    for p in problems:
        print('PROBLEM', p)
    print('next: check_diag.py %s' % out_path)


if __name__ == '__main__':
    main()
