#!/usr/bin/env python3
"""Turn a snapshot (written by refresh_meta.py) into the graph.json that build.py reads. Use it to draw a diagram from a list of box numbers.

usage: graph_from_snapshot.py snapshot.json graph.json --repo OWNER/REPO --title "text" --date YYYY-MM-DD [--frames frames.json] [--roots N,N]

frames.json (optional): {"name of a dotted frame": [number, number, ...], ...}. A number not listed in any frame is drawn outside the frames.

Everything here comes from GitHub's own data in the snapshot, so the arrows are only the native relations between two boxes of the snapshot:
  sub-issue            -> `child`       (parent to child)
  closing reference    -> `closed by`   (issue to the pull request that closes it)
  blockedBy            -> `blocked by`  (the blocked box to its blocker)
Relations that GitHub does not store (`follow-up`, `led to`, `supersedes`, `related`, `evidence, does not close`) are said in prose. Read
them with mentions.py, judge each pair, and pass your arrows with --edges edges.json ([[from, to, "kind"], ...]). One arrow is kept per pair
of boxes, the strongest kind first (closed by, child, supersedes, revised by, work done by, evidence, follow-up, spawned, led to, blocked by,
depends on, references, related, mentioned); an issue that a merged pull request closes by its text becomes `closed` with its note.

Rules used for a box (the same as SKILL.md):
  issue state open -> `open`; closed -> `handclosed` (red cross) when rules.close_verdict says closed by hand (the work not done),
  else `closed`; an ASK is drawn by the old test (a merged pull request in the snapshot closes it) and printed
  pull request: merged -> `merged`; draft -> `draft`; open -> `waiting`; closed unmerged -> `prclosed`
  an issue with three or more sub-issues, or `umbrella` in its title, is drawn as an umbrella
  meta line: `opened D . still open | closed D | merged D | waiting for review | draft`
  notes: `Closed by PR #N.` / `Fix in PR #N (open|draft).` on an issue, `Closes #N.` on a pull request, `merge SHA (authors)` on a merged one.
"""
import argparse, json, re, sys


def title_keywords(title):
    """Keywords for a collapsed box made from its title: the leading `area:` prefix is dropped (the frame says it), then words are
    dropped from the end until the line fits one line of a collapsed box (collapse.INNER), and a dangling small word goes too.
    Good enough to start from; write better ones in --collapsed (fewer words, the point of the item)."""
    import collapse
    t = re.sub(r'^[\w ./,-]{1,40}?:\s+', '', title.strip())
    words = t.split()
    small = {'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with', 'by', 'its', 'as', 'is', 'at', 'from', 'that', 'than', 'not', 'against', 'into', 'when', 'before', 'after', 'every', 'but', 'so'}
    while words and collapse.tw(' '.join(words)) > collapse.INNER:
        words.pop()
        while words and words[-1].lower().strip(',;:') in small:
            words.pop()
    return ' '.join(words).rstrip(',;:') or t[:20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('snapshot'); ap.add_argument('out')
    ap.add_argument('--repo', required=True); ap.add_argument('--title', required=True); ap.add_argument('--date', required=True)
    ap.add_argument('--frames'); ap.add_argument('--roots', default='', help='N[,N]: the root issues (the left column; each forks into its children)')
    ap.add_argument('--edges', help='edges.json: [[from, to, "kind"], ...], the arrows the agent judged from the text (mentions.py); merged with GitHub\'s')
    ap.add_argument('--notes', help='notes.json: {"N": ["line", ...]}, one or two lines per box that the agent wrote after reading its text '
                                    '(mentions.py --digest): why it exists, what was decided, what blocks it and why, what is left')
    ap.add_argument('--collapsed', help='collapsed.json: {"N": "keywords", ...}, boxes to collapse (on request only; see SKILL.md "Collapsed '
                                        'nodes"). To keep the collapsed boxes of an earlier diagram, read them with graph_from_svg.py')
    ap.add_argument('--collapse-done', action='store_true', help='collapse every closed issue and every merged or closed pull request '
                    '(keywords from --collapsed when given, else from the title: its `area:` prefix dropped, cut to one line). Open work '
                    'stays full size, so the reader sees what is still to do, and the chart gets smaller')
    ap.add_argument('--low-as-notes', action='store_true', help='a low-importance arrow (draw.IMPORTANCE 1: related, mentioned) between two '
                    'different frames is not drawn: it becomes a note on its tail box ("Related: #N."). Such an arrow crosses the chart for '
                    'little meaning; inside one frame it is short and stays')
    o = ap.parse_args()
    raw = json.load(open(o.snapshot, encoding='utf-8'))
    snap = {int(k): v for k, v in raw.items() if k != '_meta'}
    nopath = []                                          # arrows that are true but become notes: kept in the SVG's metadata block
    frames = json.load(open(o.frames, encoding='utf-8')) if o.frames else {}
    frame_of = {int(n): name for name, nums in frames.items() for n in nums}
    nums = sorted(snap)
    has = set(nums)

    def merged_pr(i):
        return any(snap[p]['state'] == 'merged' for p in snap[i]['rel'].get('closedBy', []) if p in has)

    nodes = []
    for n in nums:
        s = snap[n]
        rel = s['rel']
        pr = s['kind'] == 'PR'
        opened = s.get('createdAt') or '?'
        if pr:
            state = {'merged': 'merged', 'draft': 'draft', 'open': 'waiting', 'closed': 'prclosed'}[s['state']]
            tail = {'merged': 'merged ' + s.get('mergedAt', ''), 'draft': 'draft', 'waiting': 'waiting for review', 'prclosed': 'closed ' + s.get('closedAt', '')}[state]
        else:
            if s['state'] == 'open':
                state = 'open'
            else:                                    # the red cross means closed by hand, the work not done (rules.close_verdict)
                import rules
                v, why = s.get('closeVerdict') or rules.close_verdict(s)
                if v == 'ask':
                    v = 'done' if merged_pr(n) else 'hand'
                    print('ASK #%d: %s; drawn %s until the user says (rules.py closed IN.svg %d hand|done "reason")' % (
                        n, why, 'without the cross' if v == 'done' else 'with the red cross', n))
                state = 'handclosed' if v == 'hand' else 'closed'
            tail = 'still open' if state == 'open' else 'closed ' + s.get('closedAt', '')
        notes = []
        if pr:
            closes = [i for i in rel.get('closes', []) if i in has]
            if closes:
                notes.append('Closes ' + ', '.join('#%d' % i for i in closes) + '.')
        else:
            for p in rel.get('closedBy', []):
                if p in has:
                    st = snap[p]['state']
                    if st == 'merged':
                        notes.append('Closed by PR #%d.' % p if state != 'open' else 'PR #%d merged; this issue stays open.' % p)
                    elif st in ('open', 'draft'):
                        notes.append('Fix in PR #%d (%s).' % (p, 'draft' if st == 'draft' else 'open'))
                    else:
                        notes.append('PR #%d was not merged.' % p)
        node = {'num': n, 'state': state, 'title': s['title'], 'meta': 'opened %s · %s' % (opened, tail), 'notes': notes}
        if pr:
            node['author'] = s.get('opener', '?')
            if state == 'merged' and s.get('mergeSha'):
                node['mono'] = 'merge %s (%s)' % (s['mergeSha'], ', '.join(s.get('authors') or [s.get('opener', '?')]))
        else:
            node['assignees'] = list(s.get('assignees') or [])
            if len([c for c in rel.get('children', []) if c in has]) >= 3 or 'umbrella' in s['title'].lower():
                node['umbrella'] = True
        if n in frame_of:
            node['frame'] = frame_of[n]
        node['github'] = s                                   # the box keeps its GitHub record (svgmeta.py data-github)
        nodes.append(node)

    edges = set()
    for n in nums:
        rel = snap[n]['rel']
        for c in rel.get('children', []):
            if c in has:
                edges.add((n, c, 'child'))
        for p in rel.get('closedBy', []):
            if p in has:
                edges.add((n, p, 'closed by'))
        for i in rel.get('closes', []):
            if i in has:
                edges.add((i, n, 'closed by'))
        for b in rel.get('blockedBy', []):
            if b in has:
                edges.add((n, b, 'blocked by'))
        for b in rel.get('blocking', []):
            if b in has:
                edges.add((b, n, 'blocked by'))
    if o.edges:                                   # arrows read from the text; a text `closed by` / `work done by` replaces nothing GitHub stores
        import draw
        for a, b, k in json.load(open(o.edges, encoding='utf-8')):
            if k not in draw.EDGE:
                sys.exit('unknown arrow word "%s" in %s' % (k, o.edges))
            if a in has and b in has and a != b:
                edges.add((a, b, k))
        for a, b, k in list(edges):              # one pair, one arrow: a GitHub `closed by` wins over a text `work done by` for the same pair
            if k == 'work done by' and (a, b, 'closed by') in edges:
                edges.discard((a, b, k))
        import rules
        for n2, s2 in snap.items():               # an issue closed as a duplicate points to the one that remains
            if s2.get('duplicateOf') in has and s2['duplicateOf'] != n2:
                edges.add((n2, s2['duplicateOf'], 'duplicate of'))
        rank = rules.RANK                         # the one strength order (rules.py)
        best = {}
        for a, b, k in edges:                    # one arrow per pair of boxes: the strongest kind (a blocking child is told by its bold lines)
            key = (min(a, b), max(a, b))
            if key not in best or rank.index(k) < rank.index(best[key][2]):
                best[key] = (a, b, k)
        edges = set(best.values())
        by_num = {n['num']: n for n in nodes}
        parents = {}
        for a, b, k in edges:
            if k == 'child':
                parents.setdefault(b, set()).add(a)
        word = {'follow-up': 'Follow-up to', 'led to': 'Came out of', 'spawned': 'Spawned by', 'related': 'Related:', 'references': 'Refers to',
                'depends on': 'Depends on', 'mentioned': 'Mentions'}
        for a, b, k in sorted(edges):            # siblings (two children of one parent) get no arrow between them, only a note (SKILL.md)
            if k in word and parents.get(a, set()) & parents.get(b, set()):
                edges.discard((a, b, k))
                tail, head = (b, a) if k in ('follow-up', 'led to', 'spawned') else (a, b)
                by_num[tail]['notes'].append('%s #%d.' % (word[k], head))
        for a, b, k in edges:                    # an issue a merged pull request closes (by its text) is `closed`, not closed by hand
            n = by_num[a]
            if k == 'closed by' and snap[b]['state'] == 'merged' and n['state'] == 'handclosed':
                n['state'] = 'closed'
            if k == 'closed by' and snap[b]['state'] == 'merged' and n['state'] == 'closed' and not any('#%d' % b in x for x in n['notes']):
                n['notes'] = [x for x in n['notes'] if 'was not merged' not in x] + ['Closed by PR #%d.' % b]
    if o.low_as_notes:
        import draw
        word_of = {'related': 'Related:', 'mentioned': 'Mentions'}
        by_n = {n['num']: n for n in nodes}
        for a, b, k in sorted(edges):
            if draw.IMPORTANCE.get(k, 2) == 1 and by_n[a].get('frame') != by_n[b].get('frame'):
                edges.discard((a, b, k))
                by_n[a]['notes'].append('%s #%d.' % (word_of.get(k, 'See'), b))
                nopath.append({'from': a, 'to': b, 'kind': k, 'reason': 'low importance across frames: a note on #%d instead' % a})
    # The notes the agent wrote from the text, then "Blocked by": bold while the issue and a blocker named on the line are both open
    # (the block is live), plain once either is closed. An arrow `blocked by` with no line about it gets a plain "Blocked by #N." line.
    written = {int(k): v for k, v in json.load(open(o.notes, encoding='utf-8')).items()} if o.notes else {}
    by_num = {n['num']: n for n in nodes}
    is_open = lambda i: i in snap and snap[i]['state'] in ('open', 'draft')
    blockers = {}
    for a, b, k in edges:
        if k == 'blocked by':
            blockers.setdefault(a, []).append(b)
    for n in nodes:
        mine = list(written.get(n['num'], []))
        said = ' '.join(x for x in mine if x.lower().startswith('blocked by'))
        rest = [b for b in sorted(blockers.get(n['num'], [])) if '#%d' % b not in said]
        live = [b for b in rest if is_open(n['num']) and is_open(b)]
        over = [b for b in rest if b not in live]     # a block that is over (either side closed) is history, not a live block
        if live:
            mine.append('Blocked by %s.' % ', '.join('#%d' % b for b in live))
        if over:
            mine.append('Was blocked by %s.' % ', '.join('#%d' % b for b in over))
        out = []
        for x in mine:
            if x.lower().startswith('blocked by') and '**' not in x:
                named = [int(m) for m in re.findall(r'#(\d+)', x)]
                if is_open(n['num']) and any(is_open(b) for b in named):
                    cut = re.search(r'[:.](\s|$)', x)          # bold the block itself ("Blocked by #N (Q1):"), not the explanation after it
                    k = cut.end(0) if cut else len(x)
                    x = ('**%s** %s' % (x[:k].strip(), x[k:].strip())).strip()
            out.append(x)
        n['notes'] = n['notes'] + out
    given = {int(k): kw for k, kw in json.load(open(o.collapsed, encoding='utf-8')).items() if kw} if o.collapsed else {}
    for k, kw in given.items():
        if k in by_num:
            by_num[k]['collapsed'] = kw
    if o.collapse_done:
        for n in nodes:
            if n['state'] in ('closed', 'handclosed', 'merged', 'prclosed') and n['num'] not in given:
                n['collapsed'] = title_keywords(n['title'])
    spec = {'repo': o.repo, 'title': o.title, 'date': o.date, 'asOf': raw.get('_meta', {}).get('asOf'), 'roots': [int(r) for r in o.roots.replace('#', '').split(',') if r.strip()], 'nodes': nodes,
            'edges': [{'from': a, 'to': b, 'kind': k} for a, b, k in sorted(edges)],
            'meta': {'nopath': nopath, 'lastRun': raw.get('_meta', {}).get('lastRun'),
                     'ignored': [x if isinstance(x, dict) else {'num': int(x), 'reason': ''} for x in raw.get('_meta', {}).get('ignored', [])]}}
    json.dump(spec, open(o.out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    kinds = {}
    for _, _, k in edges:
        kinds[k] = kinds.get(k, 0) + 1
    print('%d boxes, %d in frames, %d arrows %s' % (len(nodes), len(frame_of), len(edges), kinds))


if __name__ == '__main__':
    main()
