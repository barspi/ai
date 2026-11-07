#!/usr/bin/env python3
"""Read a lineage diagram back into the graph.json that build.py reads, so an old diagram can be laid out again with the current builder.

usage: graph_from_svg.py IN.svg graph.json [--date YYYY-MM-DD] [--roots N,N] [--keep-new]

What it reads (the structure draw.py writes; check_diag.py relies on the same):
- every box `<g id="nN">`: kind (ISSUE, umbrella, PR), state (pill word; an issue with the red cross is `handclosed`, a pull request
  with `closed` is `prclosed`), the name after the arrow or `by`, the title, meta, note and mono lines (bold tspans become `**...**`).
  A collapsed box keeps its keywords (`data-keywords`); its full lines are read from its pop-up `#popN`.
- its dotted frame: the smallest frame that contains the box.
- every arrow: its tail and tip boxes, and its kind from its label (the word on it), or from its arrowhead when it has no label.
- the page title and the repository line.
`new` pills are dropped unless --keep-new. Nothing is judged here: the boxes, frames and arrows are the old diagram's. Then run
`build.py graph.json new.svg` and `check_diag.py new.svg old.svg` (the box and arrow sets must match).
"""
import argparse, html, json, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import box_header, collapse, draw, model, route

MARK = {'h-child': 'child', 'h-closed': 'closed by', 'h-work': 'work done by', 'h-evid': 'evidence, does not close', 'h-cross': 'supersedes',
        'h-blocked': 'blocked by', 'h-led': 'led to', 'h-ref': 'related'}


def plain(fragment):
    """Text of one SVG text line: bold tspans as **...**, links as their text, entities decoded."""
    s = re.sub(r'<title>.*?</title>', '', fragment, flags=re.S)
    s = re.sub(r'<tspan style="font-weight:700">(.*?)</tspan>(?=(?:[^<]|<(?!/tspan))*$)', r'**\1**', s, flags=re.S)
    s = re.sub(r'<tspan style="font-weight:700">', '**', s)
    out, depth, bold = [], 0, False
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s).replace(' ', ' ').strip()


def lines_of(group):
    title, meta, notes, mono = [], '', [], ''
    for m in re.finditer(r'<text class="(ttl|meta|note|mono)" x="[\d.]+" y="[\d.]+"(?: [^>]*)?>(.*?)</text>', group, re.S):
        cls, body = m.group(1), m.group(2)
        if 'text-anchor="end"' in m.group(0):        # the grey cue of a collapsed box
            continue
        t = bold_aware(body)
        if cls == 'ttl':
            title.append(t)
        elif cls == 'meta':
            meta = t
        elif cls == 'note':
            notes.append(t)
        else:
            mono = t
    return ' '.join(title), meta, notes, mono


def bold_aware(body):
    body = re.sub(r'<title>.*?</title>', '', body, flags=re.S)
    parts, out, depth_bold = re.split(r'(<[^>]+>)', body), [], []
    stack = []
    for p in parts:
        if p.startswith('<tspan'):
            b = 'font-weight:700' in p
            stack.append(b)
            if b:
                out.append('**')
        elif p == '</tspan>':
            if stack and stack.pop():
                out.append('**')
        elif p.startswith('<'):
            continue
        else:
            out.append(p)
    return html.unescape(''.join(out)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('svg'); ap.add_argument('out')
    ap.add_argument('--date', default=''); ap.add_argument('--roots', default=''); ap.add_argument('--keep-new', action='store_true')
    o = ap.parse_args()
    text = open(o.svg, encoding='utf-8').read()
    lines, box, pop, frame = collapse.parse(text)
    sc, info = model.read(text)
    rawpops = {int(m.group(1)): m.group(0) for m in re.finditer(r'<g id="pop(\d+)" class="pop">.*?\n</g>', text, re.S)}
    nodes = []
    for n, b in box.items():
        grp = '\n'.join(lines[b['a']:b['b'] + 1])
        full = rawpops.get(n, grp)
        head = re.search(r'<text class="kind"[^>]*>(.*?)</text>', grp, re.S).group(1)
        pr = bool(re.match(r'\s*PR\b', re.sub(r'<[^>]+>', '', head)))
        umb = '☂' in head or 'UMBRELLA' in head
        word = re.search(r'<text class="pill"[^>]*>([^<]+)</text>', grp).group(1).strip()
        cross = bool(re.search(r'<line [^>]*stroke="#ff2a2a"', grp))
        if pr:
            state = {'merged': 'merged', 'waiting': 'waiting', 'draft': 'draft', 'closed': 'prclosed'}[word]
        else:
            state = 'open' if word == 'open' else ('handclosed' if cross else 'closed')
        who = box_header.who_of(grp)
        who = html.unescape(re.sub(r'<[^>]+>', '', who)).strip() if who else None
        title, meta, notes, mono = lines_of(full)
        node = {'num': n, 'state': state, 'title': title, 'meta': meta, 'notes': notes}
        if mono:
            node['mono'] = mono
        if pr:
            node['author'] = re.sub(r'^by\s+', '', who) if who else None
        else:
            if not who or who == '?':
                node['assignees'] = []
            else:
                m = re.match(r'(.+?)\s*\+(\d+)$', who)
                node['assignees'] = [m.group(1)] + ['?'] * int(m.group(2)) if m else [who]
            if umb:
                node['umbrella'] = True
        kw = re.search(r'data-keywords="([^"]*)"', grp)
        if kw:
            node['collapsed'] = html.unescape(kw.group(1))
        if o.keep_new and re.search(r'<g transform="rotate\(-45', grp):
            node['new'] = True
        x, y, w, h = b['x'], b['y'], b['w'], b['h']
        inside = [f for f in frame if f['x'] <= x and x + w <= f['x'] + f['w'] and f['y'] <= y and y + h <= f['y'] + f['h']]
        if inside:
            f = min(inside, key=lambda f: f['w'] * f['h'])
            node['frame'] = plain(lines[f['tl']]) if 'tl' in f else html.unescape(f['name'])     # the visible title (no tooltip text)
        nodes.append(node)

    # arrows: tail and tip boxes; the kind from the label on the arrow, else from the arrowhead
    labels = []
    for i in range(len(lines)):
        lab = draw.label_at(lines, i)
        if lab:
            labels.append((lab[0] + lab[2] / 2, lab[1] + lab[3] / 2, lab[5]))
    edges, unknown = [], 0
    for ln in lines:
        if not (ln.startswith('<path d="M') and 'marker-end' in ln):
            continue
        pts = model.arrow_points(ln)
        ends = [next((n for n, r in sc.boxes.items() if model._side(p, r)), None) for p in (pts[0], pts[-1])]
        if None in ends or ends[0] == ends[1]:
            unknown += 1
            continue
        kind = None
        for cx, cy, wd in labels:
            if any((o2 == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o2 == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1)
                   for o2, c, lo, hi in route.segments(pts)):
                kind = wd if wd in draw.EDGE else kind
        if kind is None:
            mk = re.search(r'marker-end="url\(#([\w-]+)\)"', ln)
            kind = MARK.get(mk.group(1) if mk else '', 'related')
        edges.append({'from': ends[0], 'to': ends[1], 'kind': kind})
    h1 = re.search(r'<text class="h1"[^>]*>(.*?)</text>', text, re.S)
    repo = re.search(r'Repository: ([^<]+)', text)
    spec = {'repo': repo.group(1).strip() if repo else re.search(r'github\.com/([^/"]+/[^/"]+)/(?:issues|pull)/', text).group(1),
            'title': plain(h1.group(1)) if h1 else 'Lineage diagram', 'date': o.date,
            'roots': [int(r) for r in o.roots.replace('#', '').split(',') if r.strip()], 'nodes': nodes, 'edges': edges}
    json.dump(spec, open(o.out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('%d boxes (%d collapsed, %d in frames), %d arrows%s' % (len(nodes), sum(1 for n in nodes if n.get('collapsed')),
          sum(1 for n in nodes if n.get('frame')), len(edges), ('; %d paths with no box at either end were left out (an old legend draws its sample arrows as paths)' % unknown) if unknown else ''))


if __name__ == '__main__':
    main()
