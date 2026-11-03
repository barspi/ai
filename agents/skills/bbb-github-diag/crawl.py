#!/usr/bin/env python3
"""Walk the GitHub relations from root issues and list the candidates for a lineage diagram. One GraphQL call per level.

usage: crawl.py OWNER/REPO --seed N[,N...] [--window-days 30] [--max-nodes 40] [--depth N] [--known N[,N...]] [--no-up] [--text] [--out graph.json]

- Relations followed (structural, from GitHub): sub-issues and parent, closing references (both ways), blockedBy and blocking.
  A `#N` in a body is printed under "mentions" and never followed.
- Seeds and --known items (already in the chart) are always kept. Any other item is kept when it is open, or closed within
  --window-days (no window: everything is kept). An item outside the window is still kept when it is a DIRECT CHILD of a kept
  item (a sub-issue, or joined by a closing reference), and is flagged ASK: decide with the user. Otherwise it is dropped.
- `--no-up` does not follow a parent: the chart grows downwards only (otherwise an umbrella's parent pulls in all its siblings).
- Relevance and age decide, not a hop count: sub-issues are followed all the way down, and so are closing references. A weaker candidate (a blocker, a cross-referencing pull request that does not close the item) is kept only if it is open or inside the window.
- `--text` also prints, for each kept item, the lines of its body that name another kept item (at most 3 per item), because `follow-up`, `led to`, `related` and `supersedes` are said in prose. Read them; the script does not classify them.
- `--max-nodes` (default 40) stops the walk when that many items are kept, and says how many candidates were not fetched. `--depth N` is an optional hop cap (default: none).
- Relations are followed only from kept items.
- The script judges nothing about meaning. Read the titles and decide; write the scope and every exception in the NOTES file.
Needs the `gh` CLI, logged in.
"""
import argparse, datetime, json, re, subprocess, sys

FIELDS = """__typename
  ... on Issue { number title state stateReason createdAt closedAt updatedAt body
                 parent{number} subIssues(first:50){nodes{number}} blockedBy(first:20){nodes{number}}
                 blocking(first:20){nodes{number}} closedByPullRequestsReferences(first:20){nodes{number}}
                 timelineItems(first:60,itemTypes:[CROSS_REFERENCED_EVENT]){nodes{... on CrossReferencedEvent{willCloseTarget source{__typename ... on PullRequest{number} ... on Issue{number}}}}} }
  ... on PullRequest { number title state isDraft createdAt closedAt mergedAt updatedAt body author{login} labels(first:10){nodes{name}}
                 closeEv: timelineItems(last:1,itemTypes:[CLOSED_EVENT]){nodes{... on ClosedEvent{actor{login}}}}
                 closingIssuesReferences(first:20){nodes{number}} }"""


def fetch(owner, name, nums):
    q = 'query{repository(owner:"%s",name:"%s"){%s}}' % (owner, name, ' '.join('i%d:issueOrPullRequest(number:%d){%s}' % (n, n, FIELDS) for n in nums))
    r = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + q], capture_output=True, text=True)
    if r.returncode:
        sys.exit('gh failed: ' + r.stderr.strip())
    d = json.loads(r.stdout)['data']['repository']
    return {n: d.get('i%d' % n) for n in nums}


def nums(node, key):
    return [x['number'] for x in (node.get(key) or {}).get('nodes', [])]


def relations(n, d, up=True):
    """(kind, a, b): a -> b with the arrow word, taken from one node's data."""
    out = []
    if d['__typename'] == 'Issue':
        out += [('child', n, c) for c in nums(d, 'subIssues')]
        if d.get('parent') and up:
            out.append(('child', d['parent']['number'], n))
        out += [('closed by', n, p) for p in nums(d, 'closedByPullRequestsReferences')]
        out += [('blocked by', n, b) for b in nums(d, 'blockedBy')]
        out += [('blocked by', b, n) for b in nums(d, 'blocking')]
        # a pull request that says "Closes #n" is a closing reference even when it was closed without merging
        # (closedByPullRequestsReferences leaves those out); other cross references are only mentions
        for ev in (d.get('timelineItems') or {}).get('nodes', []):
            src = ev.get('source') or {}
            if src.get('__typename') == 'PullRequest' and ev.get('willCloseTarget'):
                out.append(('closed by', n, src['number']))
            elif src.get('__typename') == 'PullRequest' and src['number'] != n:
                out.append(('xref', n, src['number']))     # a pull request to fetch; kept only when it passes the filters
            # an issue that cross-references an item is a mention: it is never followed
    else:
        out += [('closed by', i, n) for i in nums(d, 'closingIssuesReferences')]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo'); ap.add_argument('--seed', required=True); ap.add_argument('--depth', type=int); ap.add_argument('--max-nodes', type=int, default=40)
    ap.add_argument('--window-days', type=int); ap.add_argument('--known', default=''); ap.add_argument('--no-up', action='store_true'); ap.add_argument('--text', action='store_true'); ap.add_argument('--out')
    o = ap.parse_args()
    owner, name = o.repo.split('/')
    seeds = [int(x) for x in o.seed.split(',')]
    known = {int(x) for x in o.known.split(',') if x}
    today = datetime.datetime.now(datetime.timezone.utc)
    cutoff = today - datetime.timedelta(days=o.window_days) if o.window_days else None

    kept, dropped, edges, why, mention_of, bodies = {}, {}, set(), {}, {}, {}
    level = {n: (0, 'seed' if n in seeds else 'known') for n in seeds + sorted(known - set(seeds))}
    seen = set(level)
    while level:
        data = fetch(owner, name, sorted(level))
        nxt = {}
        for n, (depth, via) in sorted(level.items()):
            d = data[n]
            if not d:
                dropped[n] = ('not found', via); continue
            closed = d.get('mergedAt') or d.get('closedAt')
            is_open = d['state'] == 'OPEN'
            in_window = is_open or cutoff is None or (closed and datetime.datetime.fromisoformat(closed.replace('Z', '+00:00')) >= cutoff)
            via_kind, via_n = via.split(' ')[0], int(via.split('#')[-1]) if '#' in via else 0
            # a pull request found by a cross reference is a direct child only if it really closes the item it references
            direct_child = via_kind in ('child', 'closed') or (via_kind == 'xref' and via_n in nums(d, 'closingIssuesReferences'))
            if depth > 0 and n not in known and not in_window and not direct_child:
                dropped[n] = ('closed %s, outside the window' % (closed or '?')[:10], via); continue
            reason = ''
            if d['state'] == 'CLOSED' and not d.get('mergedAt') and d['__typename'] == 'PullRequest':       # why was it closed unmerged
                actor = next((e['actor']['login'] for e in (d.get('closeEv') or {}).get('nodes', []) if e.get('actor')), '')
                lab = [l['name'] for l in (d.get('labels') or {}).get('nodes', [])]
                author = (d.get('author') or {}).get('login', '')
                reason = ('closed by the author' if actor and actor == author else 'closed as maintainer-only (by %s)' % actor if any('maintainer' in l.lower() for l in lab)
                          else 'closed by %s' % actor if actor else 'closed without merging')
            elif d['state'] == 'CLOSED' and d['__typename'] == 'Issue' and d.get('stateReason'):
                reason = 'closed as ' + d['stateReason'].lower().replace('_', ' ')
            kept[n] = dict(reason=reason, kind='PR' if d['__typename'] == 'PullRequest' else 'ISSUE', state='merged' if d.get('mergedAt') else d['state'].lower(),
                           draft=bool(d.get('isDraft')) and is_open, title=d['title'], closed=(closed or '')[:10], depth=depth, via=via,
                           ask=depth > 0 and n not in known and not in_window)
            bodies[n] = d.get('body') or ''
            for m in set(int(x) for x in re.findall(r'(?<![\w/])#(\d+)\b', d.get('body') or '')) - {n}:
                mention_of.setdefault(m, set()).add(n)
            if o.depth is not None and depth >= o.depth:
                continue
            for k, a, b in relations(n, d, not o.no_up):
                if k != 'xref':
                    edges.add((k, a, b))
                other = b if a == n else a
                if other not in seen:
                    seen.add(other)
                    nxt[other] = (depth + 1, '%s of #%d' % ('child' if k == 'child' else 'closed' if k == 'closed by' else k.split(' ')[0], n))
        if len(kept) >= o.max_nodes and nxt:
            print('CAP: %d items kept (--max-nodes %d); %d candidates were not fetched: %s' % (len(kept), o.max_nodes, len(nxt), ' '.join('#%d' % x for x in sorted(nxt))))
            break
        level = nxt

    edges = {e for e in edges if e[1] in kept and e[2] in kept}
    print('--- kept (%d) ---' % len(kept))
    for n, v in sorted(kept.items(), key=lambda kv: (kv[1]['depth'], kv[0])):
        print('#%d %s %s%s%s | %s | hop %d, %s%s' % (n, v['kind'], 'draft' if v['draft'] else v['state'], ' ' + v['closed'] if v['closed'] else '', '', v['title'][:80], v['depth'], v['via'], '  ASK: outside the window, kept as a direct child' if v['ask'] else '') + ('  [%s]' % v['reason'] if v['reason'] else ''))
    print('--- dropped (%d) ---' % len(dropped))
    for n, (r, via) in sorted(dropped.items()):
        print('#%d %s (reached as %s)' % (n, r, via))
    ment = {m: sorted(s) for m, s in mention_of.items() if m not in kept and m not in dropped}
    print('--- mentioned in a kept body, not followed (%d) ---' % len(ment))
    for m, s in sorted(ment.items()):
        print('#%d named by %s' % (m, ', '.join('#%d' % x for x in s)))
    print('(a pull request that says "Closes #N" counts as a closing reference even when it was closed unmerged)')
    print('--- relations between kept items (%d) ---' % len(edges))
    for k, a, b in sorted(edges, key=lambda e: (e[1], e[2])):
        print('#%d %s #%d' % (a, k, b))
    if o.text:
        print('--- text naming another kept item (read for follow-up, led to, related, supersedes) ---')
        for n in sorted(kept):
            hits = [ln.strip() for ln in bodies.get(n, '').splitlines() if any(int(x) in kept and int(x) != n for x in re.findall(r'(?<![\w/])#(\d+)\b', ln))]
            for ln in hits[:3]:
                print('#%d: %s' % (n, ln[:140]))
    if o.out:
        json.dump({'kept': kept, 'dropped': dropped, 'edges': sorted(edges), 'mentions': ment}, open(o.out, 'w'), indent=1)


if __name__ == '__main__':
    main()
