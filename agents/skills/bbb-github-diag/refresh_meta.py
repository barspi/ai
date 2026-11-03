#!/usr/bin/env python3
"""Refresh the metadata of every box in a lineage diagram with ONE GitHub GraphQL call.

usage: refresh_meta.py OWNER/REPO diagram.svg snapshot.json [--tsv-dir DIR] [--discover] [--since ISO8601]

- Box numbers come from the `<g id="nNNN">` groups of the SVG.
- The snapshot (JSON, kept next to the SVG) stores, per box: updatedAt, state, merged, title, assignees,
  opener, comment/review counts, merge commit and commit authors. `updatedAt` changes on ANY edit, comment,
  label, assignee or state change, so a box whose updatedAt is unchanged needs no reading at all.
- Prints only what changed since the snapshot (new snapshot is then saved), plus every box whose pill in the
  SVG disagrees with the live state. Read the full text of a box only when it is listed as changed.
- With --tsv-dir it also writes assignees.tsv (issue<TAB>login,login) and prauthors.tsv (pr<TAB>opener),
  which a build script can read, so nobody types them by hand.
- With --discover it also lists the issues and pull requests created or changed since the last run (or --since)
  that are NOT boxes yet, one line each: kind, state, title, which boxes they name (`#N` in title or body),
  which boxes' texts name them, and the area tags (the `word:` prefixes of titles) they share with boxes.
  Items listed in the snapshot's `_meta.ignored` (decided "not drawn") are counted, not listed.
  Judge the relation from that line; open the item only when the line is not enough.
- A pull request that is open and a draft has the state `draft`; an open one that is ready is `open` (pill `waiting`).
- Needs the `gh` CLI, logged in. Run it outside any sandbox that blocks TLS to api.github.com.
"""
import json, os, re, subprocess, sys

FIELDS = """
  __typename
  ... on Issue { title state stateReason closedAt updatedAt author{login} comments{totalCount}
                 assignees(first:10){nodes{login}}
                 parent{number} subIssues(first:50){nodes{number}} blockedBy(first:20){nodes{number}}
                 blocking(first:20){nodes{number}} closedByPullRequestsReferences(first:10){nodes{number}} }
  ... on PullRequest { title state isDraft merged mergedAt closedAt updatedAt author{login} comments{totalCount}
                 reviews{totalCount} mergeCommit{oid} mergedBy{login} closingIssuesReferences(first:20){nodes{number}}
                 commits(first:50){nodes{commit{authors(first:5){nodes{name user{login}}}}}} }
"""

def discover(repo, svg_text, live, since, meta):
    """Print items created, closed or merged since `since` that are not boxes, only when they link to a box."""
    r = subprocess.run(['gh', 'api', 'repos/%s/issues?state=all&since=%s&per_page=100&sort=updated&direction=desc' % (repo, since),
                        '--paginate', '--jq', '.[]|{number,title,body,state,pr:(.pull_request!=null),merged:(.pull_request.merged_at//""),created:.created_at,closed:(.closed_at//""),user:.user.login}'],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit('gh failed: ' + r.stderr.strip())
    items = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    boxset = {n for n in live}
    box_text = {}
    for m in re.finditer(r'<g id="n(\d+)"(.*?)</g>', svg_text, flags=re.S):
        box_text[int(m.group(1))] = re.sub(r'<[^>]+>', ' ', m.group(2))
    area = {}
    for n, v in live.items():
        for x in (re.match(r'\s*([^:]{2,40}):', v.get('title', '')) or [None, ''])[1].split(','):
            if x.strip():
                area.setdefault(x.strip(), set()).add(n)
    ignored = set(meta.get('ignored', []))
    print('--- created, closed or merged since %s, not boxes ---' % since)
    n_old = n_ign = n_none = 0
    same_area = {}
    for it in items:
        n = it['number']
        if n in boxset:
            continue
        if not (it['created'] >= since or (it['closed'] and it['closed'] >= since) or (it['merged'] and it['merged'] >= since)):
            n_old += 1          # only commented on or edited: not new, not closed, not merged
            continue
        if n in ignored:
            n_ign += 1
            continue
        txt = (it['title'] or '') + ' ' + (it['body'] or '')
        names = sorted({int(x) for x in re.findall(r'#(\d+)', txt)} & boxset)
        named_by = sorted(b for b, t in box_text.items() if re.search(r'#%d\b' % n, t))
        tags = [x.strip() for x in ((re.match(r'\s*([^:]{2,40}):', it['title'] or '') or [None, ''])[1]).split(',')]
        shared = [t for t in tags if t in area]
        st = 'merged' if it['merged'] else it['state']
        if names or named_by:
            print('#%d %s %s by %s: %s | names boxes %s | named by boxes %s' % (
                n, 'PR' if it['pr'] else 'ISSUE', st, it['user'], (it['title'] or '')[:90], names or '-', named_by or '-'))
        elif shared:
            for t in shared:
                same_area.setdefault(t, []).append(n)
        else:
            n_none += 1
    for t, ns in sorted(same_area.items()):
        print('same area only (%s, no link): %s' % (t, ' '.join('#%d' % x for x in sorted(ns))))
    print('%d unrelated, %d only commented/edited, %d ignored (decided not drawn).' % (n_none, n_old, n_ign))

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('repo'); ap.add_argument('svg'); ap.add_argument('snapshot')
    ap.add_argument('--tsv-dir'); ap.add_argument('--discover', action='store_true'); ap.add_argument('--since')
    ap.add_argument('--umbrellas', action='store_true', help='for an umbrella by title without sub-issues, list the issues its body names')
    ap.add_argument('--relations', action='store_true', help='print every GitHub-native relation between two boxes')
    ap.add_argument('--apply', action='store_true', help='edit the SVG in place: pills, colours, date line, merge line, assignee label, "Closed by PR" note (svg_state.py). Run check_diag.py after it')
    opts = ap.parse_args()
    repo, svg, snap_path, tsv_dir = opts.repo, opts.svg, opts.snapshot, opts.tsv_dir
    import datetime
    run_start = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    owner, name = repo.split('/')
    text = open(svg).read()
    nums = sorted({int(n) for n in re.findall(r'<g id="n(\d+)"', text)})
    pills, kinds = {}, {}
    for m in re.finditer(r'<g id="n(\d+)"(.*?)</g>', text, flags=re.S):
        k = re.search(r'class="kind"[^>]*>(ISSUE|UMBRELLA|PR) ', m.group(2))
        kinds[int(m.group(1))] = k.group(1) if k else '?'
        w = re.findall(r'>(open|closed|merged|waiting|draft)<', m.group(2))
        pills[int(m.group(1))] = w[-1] if w else '?'

    q = 'query{repository(owner:"%s",name:"%s"){%s}}' % (
        owner, name, ' '.join('i%d:issueOrPullRequest(number:%d){%s}' % (n, n, FIELDS) for n in nums))
    out = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + q], capture_output=True, text=True)
    if out.returncode:
        sys.exit('gh failed: ' + out.stderr.strip())
    data = json.loads(out.stdout)['data']['repository']

    live = {}
    for n in nums:
        d = data.get('i%d' % n)
        if not d:
            live[n] = {'missing': True}
            continue
        pr = d['__typename'] == 'PullRequest'
        authors = []
        if pr:
            for c in d['commits']['nodes']:
                for a in c['commit']['authors']['nodes']:
                    who = (a['user'] or {}).get('login') or a.get('name')      # no GitHub login: the git author's name
                    if who and who not in authors:
                        authors.append(who)
        nums_of = lambda key: sorted(x['number'] for x in d[key]['nodes']) if d.get(key) else []
        rel = {'closes': nums_of('closingIssuesReferences')} if pr else {
            'parent': (d['parent'] or {}).get('number'), 'children': nums_of('subIssues'), 'blockedBy': nums_of('blockedBy'),
            'blocking': nums_of('blocking'), 'closedBy': nums_of('closedByPullRequestsReferences')}
        live[n] = {
            'rel': rel,
            'kind': 'PR' if pr else 'ISSUE', 'title': d['title'], 'updatedAt': d['updatedAt'],
            'state': 'merged' if pr and d['merged'] else 'draft' if pr and d['state'] == 'OPEN' and d['isDraft'] else d['state'].lower(),
            'opener': (d['author'] or {}).get('login', '?'),
            'assignees': [] if pr else [a['login'] for a in d['assignees']['nodes']],
            'comments': d['comments']['totalCount'], 'reviews': d['reviews']['totalCount'] if pr else 0,
            'mergeSha': d['mergeCommit']['oid'][:9] if pr and d.get('mergeCommit') else '',
            'mergedBy': (d.get('mergedBy') or {}).get('login', '') if pr else '',
            'authors': authors,
            'closedAt': (d.get('closedAt') or '')[:10], 'mergedAt': (d.get('mergedAt') or '')[:10] if pr else '',
        }

    if opts.apply:          # local text edits on the boxes (see svg_state.py); no layout work, no rebuild
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import svg_state
        text, log, rep = svg_state.apply(text, live, repo)
        open(svg, 'w').write(text)
        print('--- applied to %s (%d edits) ---' % (svg, len(log)))
        for ln in log:
            print('  ' + ln)
        for ln in rep:
            print('  NEEDS A HUMAN: ' + ln)
        pills, kinds = {}, {}
        for m in re.finditer(r'<g id="n(\d+)"(.*?)</g>', text, flags=re.S):
            k = re.search(r'class="kind"[^>]*>(ISSUE|UMBRELLA|PR) ', m.group(2))
            kinds[int(m.group(1))] = k.group(1) if k else '?'
            w = re.findall(r'>(open|closed|merged|waiting|draft)<', m.group(2))
            pills[int(m.group(1))] = w[-1] if w else '?'

    old = json.load(open(snap_path)) if os.path.exists(snap_path) else {}
    changed = 0
    for n in nums:
        o, l = old.get(str(n)), live[n]
        if o is None:
            print('#%d  NEW IN SNAPSHOT (%s, %s)' % (n, l.get('kind'), l.get('state'))) if old else None
            continue
        if o.get('updatedAt') == l.get('updatedAt'):
            continue
        diffs = ['%s: %r -> %r' % (k, o.get(k), l.get(k)) for k in
                 ('state', 'title', 'assignees', 'comments', 'reviews', 'mergeSha', 'opener', 'rel') if o.get(k) != l.get(k)]
        print('#%d  updated %s  %s' % (n, l['updatedAt'], '; '.join(diffs) or 'body or label edit (read it)'))
        if l['state'] == 'merged' and o.get('state') != 'merged':
            print('     merge %s (%s)  merged by %s' % (l['mergeSha'], ', '.join(l['authors']), l['mergedBy']))
        changed += 1
    # an open issue is `open`; an open pull request is `waiting` (ready) or `draft`; the live state says which
    stale = [n for n in nums if not live[n].get('missing') and
             pills.get(n) not in (live[n]['state'], 'waiting' if live[n]['state'] == 'open' and live[n]['kind'] == 'PR' else None)]
    for n in nums:      # the label rule: an issue with sub-issues, or "umbrella" in its title, is an UMBRELLA
        l = live[n]
        if l.get('kind') == 'ISSUE':
            want = 'UMBRELLA' if (l['rel']['children'] or re.search('umbrella', l['title'], re.I)) else 'ISSUE'
            if kinds.get(n) != want:
                print('#%d  LABEL MISMATCH: diagram shows %s, the rule says %s (%d sub-issues; title %r)' % (n, kinds.get(n), want, len(l['rel']['children']), l['title'][:50]))
    for n in stale:
        print('#%d  PILL MISMATCH: diagram shows %s, GitHub says %s' % (n, pills.get(n), live[n]['state']))
    for n in nums:
        if live[n].get('missing'):
            print('#%d  NOT FOUND on GitHub' % n)
    print('%d boxes checked, %d changed since snapshot, %d pill mismatches.' % (len(nums), changed, len(stale)))

    if opts.relations:       # GitHub's own relations, as arrows between two boxes (compare with the diagram)
        S = set(nums)
        print('--- GitHub-native relations between boxes ---')
        for n in nums:
            r = live[n].get('rel') or {}
            for c in r.get('children', []):
                if c in S: print('#%d child #%d   (sub-issue)' % (n, c))
            for c in r.get('blockedBy', []):
                if c in S: print('#%d blocked by #%d' % (n, c))
            for c in r.get('closedBy', []):
                if c in S: print('#%d closed by PR #%d' % (n, c))
            for c in r.get('closes', []):
                if c in S: print('PR #%d closes #%d' % (n, c))
        print('(parent/children counts not shown here are issues outside the diagram)')

    if opts.umbrellas:       # umbrella by title, no sub-issues: its children can only be inferred from its text
        ub = [n for n in nums if live[n].get('kind') == 'ISSUE' and not live[n]['rel']['children'] and re.search('umbrella', live[n]['title'], re.I)]
        if ub:
            q2 = 'query{repository(owner:"%s",name:"%s"){%s}}' % (owner, name, ' '.join('i%d:issue(number:%d){body}' % (n, n) for n in ub))
            r2 = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + q2], capture_output=True, text=True)
            if r2.returncode:
                sys.exit('gh failed: ' + r2.stderr.strip())
            bodies = json.loads(r2.stdout)['data']['repository']
            print('--- umbrellas by title without sub-issues: issues their body names (infer the children from this and the text) ---')
            S = set(nums)
            for n in ub:
                body = (bodies.get('i%d' % n) or {}).get('body') or ''
                task = sorted({int(x) for ln in body.splitlines() if re.match(r'\s*[-*]\s*\[[ xX]\]', ln) for x in re.findall(r'#(\d+)', ln)} - {n})
                other = sorted({int(x) for x in re.findall(r'#(\d+)', body)} - {n} - set(task))
                print('#%d  task list names %s | other mentions %s | boxes among them: %s' % (
                    n, task or '-', other or '-', sorted((set(task) | set(other)) & S) or '-'))

    meta = old.get('_meta', {'ignored': []})
    if opts.discover:
        discover(repo, text, live, opts.since or meta.get('lastRun') or max(v['updatedAt'] for v in live.values() if 'updatedAt' in v), meta)
    if not opts.since:          # an explicit window is a look-back, it must not hide candidates from the next run
        meta['lastRun'] = run_start
    out_snap = {str(n): live[n] for n in nums}
    out_snap['_meta'] = meta
    json.dump(out_snap, open(snap_path, 'w'), indent=1, sort_keys=True)
    if tsv_dir:
        with open(os.path.join(tsv_dir, 'assignees.tsv'), 'w') as f:
            for n in nums:
                if live[n].get('kind') == 'ISSUE':
                    f.write('%d\t%s\n' % (n, ','.join(live[n]['assignees'])))
        with open(os.path.join(tsv_dir, 'prauthors.tsv'), 'w') as f:
            for n in nums:
                if live[n].get('kind') == 'PR':
                    f.write('%d\t%s\n' % (n, live[n]['opener']))

if __name__ == '__main__':
    main()
