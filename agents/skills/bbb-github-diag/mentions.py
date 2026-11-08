#!/usr/bin/env python3
"""Fetch the text of every box (body and comments) and print each sentence in which one box names another, so the agent can READ how
the items relate (follow-up, led to, blocked by, supersedes, evidence, related, ...) and write those arrows itself.

usage: mentions.py OWNER/REPO SOURCE texts.json [--add N,N] [--candidates [--edges-out edges.json]] [--digest [--only N,N]]
                   [--per-pair 3] [--width 260]

- SOURCE is a diagram (diagram.svg: its boxes and their records) or, for a first picture, the working snapshot of refresh_meta.py
  --snapshot-out. --add names items that are not boxes yet (from refresh_meta.py --discover): their text is read too, and with
  --candidates only the pairs that touch them are printed. The text is fetched with aliased GraphQL queries, 20 items per call
  (body, every comment with its author, and for a pull request its reviews' bodies), and saved to texts.json, so a second run with the
  same file does not call GitHub again (delete the file to fetch anew).
- A reference is `#N`, `PR #N`, `owner/repo#N` for this repository, or a github.com link to an issue or pull request of it. Only
  references to other boxes are printed: per pair (A names B), the first --per-pair sentences, cut at --width characters, with where
  each was found (`body`, `comment by login`). Sentences with a relation word (blocks, blocked, follow-up, closes, supersede, replace,
  led to, found, depends, evidence, related, ...) come first.
- --candidates applies the phrase rules of rules.py (PHRASES, one arrow per pair by RANK) and prints each candidate arrow with the
  rule and the sentence that produced it, then the pairs that no rule matched, with their first sentence. --edges-out writes the
  candidates as [[from, to, "kind"], ...], the --edges input of graph_from_snapshot.py (or the arrows of an add_nodes.py spec).
  Confirm each against the sentence; delete a wrong one, and add an arrow for an unmatched pair only when the text says a relation.
- Without --candidates the pairs are printed for reading. Never paste bodies into the conversation; this script prints only the
  sentences that name another box.
Needs the `gh` CLI, logged in.
"""
import argparse, json, os, re, subprocess, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules

FIELDS = """__typename
  ... on Issue { body comments(first:100){nodes{author{login} body}} }
  ... on PullRequest { body comments(first:100){nodes{author{login} body}} reviews(first:50){nodes{author{login} body}} }"""
WORDS = re.compile(r'block|follow[- ]?up|closes|closed by|fix(es|ed)? |supersed|replac|led to|found|depend|evidence|related|duplicate|'
                   r'split|child|parent|umbrella|prerequisite|after |instead|obsolete|gap|regression|revert', re.I)


def fetch(owner, name, nums):
    out = {'_kind': {}}
    for i in range(0, len(nums), 20):
        part = nums[i:i + 20]
        q = 'query{repository(owner:"%s",name:"%s"){%s}}' % (owner, name, ' '.join('i%d:issueOrPullRequest(number:%d){%s}' % (n, n, FIELDS) for n in part))
        r = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + q], capture_output=True, text=True)
        if r.returncode:
            sys.exit('gh failed: ' + r.stderr.strip()[:400])
        d = json.loads(r.stdout)['data']['repository']
        for n in part:
            x = d.get('i%d' % n) or {}
            out['_kind'][str(n)] = 'PR' if x.get('__typename') == 'PullRequest' else 'ISSUE'
            parts = [('body', x.get('body') or '')]
            for c in (x.get('comments') or {}).get('nodes', []):
                parts.append(('comment by %s' % ((c.get('author') or {}).get('login') or '?'), c.get('body') or ''))
            for c in (x.get('reviews') or {}).get('nodes', []):
                if c.get('body'):
                    parts.append(('review by %s' % ((c.get('author') or {}).get('login') or '?'), c['body']))
            out[str(n)] = parts
    return out


def sentences(text):
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)                    # code blocks name numbers that are not references
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    for line in text.splitlines():
        line = line.strip().lstrip('-*>#0123456789.) [x]').strip() if not re.match(r'\s*#\d', line) else line.strip()
        for s in re.split(r'(?<=[.;!?])\s+(?=[A-Z(`*])', line):
            if s.strip():
                yield s.strip()


def refs(s, owner, name):
    found = set(int(m) for m in re.findall(r'github\.com/%s/%s/(?:issues|pull)/(\d+)' % (re.escape(owner), re.escape(name)), s, re.I))
    found |= set(int(m) for m in re.findall(r'(?<![\w/&])(?:%s/%s)?#(\d+)\b' % (re.escape(owner), re.escape(name)), s))
    return found


KEY = re.compile(r'\bblock|decision|decided|\b[DQ]\d+\b|found (while|during|by)|came out of|spin-?off|settled|supersed|out of scope|'
                 r'not (in|on) this|remaining|still open|root cause|the fix|fixed by|answer|agreed|deferred|on hold|do not start|'
                 r'regression|reverted?|caveat|left (for|to)|follow-?up', re.I)


def digest(nums, snap, texts, width):
    """What a reader needs to write the box notes: the first paragraph of the body, the lines that say why the item exists, what blocks
    it, what was decided (D1, Q2, ...), what was settled elsewhere and what is left; then each comment's opening and the last comment."""
    def clean(t):
        t = re.sub(r'```.*?```', ' [code] ', t, flags=re.S)
        return re.sub(r'<!--.*?-->', ' ', t, flags=re.S)

    def cut(s, n):
        s = re.sub(r'\s+', ' ', s).strip()
        return s[:n] + ('...' if len(s) > n else '')

    for a in nums:
        s = snap.get(str(a)) or {}
        parts = texts.get(str(a), [])
        print('=== #%d %s %s: %s' % (a, s.get('kind', texts.get('_kind', {}).get(str(a), '?')), s.get('state', '?'), s.get('title', '(not a box yet)')))
        if parts:
            paras = [p for p in re.split(r'\n\s*\n', clean(parts[0][1])) if p.strip() and not p.strip().startswith('#')]
            if paras:
                print('  body: ' + cut(paras[0], width * 2))
        seen = 0
        for where, t in parts:
            for line in clean(t).splitlines():
                line = line.strip().lstrip('-*> ').strip()
                if line and KEY.search(line) and seen < 8:
                    print('  [%s] %s' % (where, cut(line, width)))
                    seen += 1
        comments = parts[1:]
        for w, t in comments[:-1]:
            print('  <%s> %s' % (w, cut(clean(t), 120)))
        if comments:
            print('  <%s, last> %s' % (comments[-1][0], cut(clean(comments[-1][1]), width + 100)))


def candidates(nums, box, texts, kinds, owner, name, added, o):
    """Candidate arrows from the phrase rules (rules.py), each with its evidence; then the pairs no rule matched."""
    found, unmatched = [], {}
    for a in nums:
        for where, body in texts.get(str(a), []):
            for s in sentences(body):
                named = [b for b in refs(s, owner, name) if b in box and b != a]
                for b in sorted(named):
                    if added and a not in added and b not in added:
                        continue
                    m = rules.match(s, a, b, kinds, owner, name)
                    if m:
                        found.append(m + (a, where, re.sub(r'\s+', ' ', s)))
                    elif len(named) < 3:                       # a sentence naming three or more boxes is a list: no relation
                        unmatched.setdefault((min(a, b), max(a, b)), (a, where, re.sub(r'\s+', ' ', s)))
    best = rules.strongest(found)
    for kind, f, t, rule, a, where, s in best:
        print('#%d %s #%d   [%s, in #%d %s] %s' % (f, kind, t, rule, a, where, s[:o.width] + ('...' if len(s) > o.width else '')))
    have = {(min(c[1], c[2]), max(c[1], c[2])) for c in best}
    rest = [(k, v) for k, v in sorted(unmatched.items()) if k not in have]
    if rest:
        print('--- pairs no rule matched (judge each; most are passing mentions) ---')
        for (x, y), (a, where, s) in rest:
            print('#%d ~ #%d   [in #%d %s] %s' % (x, y, a, where, s[:o.width] + ('...' if len(s) > o.width else '')))
    print('%d candidate arrows, %d pairs without a rule' % (len(best), len(rest)))
    if o.edges_out:
        json.dump([[f, t, kind] for kind, f, t, *_ in best], open(o.edges_out, 'w', encoding='utf-8'), indent=0)
        print('wrote %s' % o.edges_out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo'); ap.add_argument('source'); ap.add_argument('texts')
    ap.add_argument('--add', default='', help='N,N: items that are not boxes yet')
    ap.add_argument('--candidates', action='store_true', help='apply the phrase rules (rules.py) and print candidate arrows')
    ap.add_argument('--edges-out', help='with --candidates: write them as [[from, to, kind], ...]')
    ap.add_argument('--per-pair', type=int, default=3); ap.add_argument('--width', type=int, default=260)
    ap.add_argument('--digest', action='store_true', help='print a short digest of every box (to write its notes) instead of the pairs')
    ap.add_argument('--only', default='', help='N,N: limit --digest to these boxes')
    o = ap.parse_args()
    owner, name = o.repo.split('/')
    if o.source.endswith('.svg'):
        import svgmeta
        snap = {str(n): (v['github'] or {}) for n, v in svgmeta.boxes(open(o.source, encoding='utf-8').read()).items()}
    else:
        snap = {k: v for k, v in json.load(open(o.source, encoding='utf-8')).items() if k != '_meta'}
    added = {int(x) for x in o.add.replace('#', '').split(',') if x.strip()}
    nums = sorted({int(k) for k in snap} | added)
    box = set(nums)
    texts = json.load(open(o.texts, encoding='utf-8')) if os.path.exists(o.texts) else {}
    missing = [n for n in nums if str(n) not in texts]
    if missing:                                   # only what the cache does not have yet
        got = fetch(owner, name, missing)
        texts.setdefault('_kind', {}).update(got.pop('_kind'))
        texts.update(got)
        json.dump(texts, open(o.texts, 'w', encoding='utf-8'), indent=0, ensure_ascii=False)
    kinds = {int(k): v for k, v in texts.get('_kind', {}).items()}
    kinds.update({int(k): v['kind'] for k, v in snap.items() if v.get('kind')})
    if o.digest:
        only = {int(x) for x in o.only.replace('#', '').split(',') if x.strip()}
        digest([n for n in nums if not only or n in only], snap, texts, o.width)
        return
    if o.candidates:
        candidates(nums, box, texts, kinds, owner, name, added, o)
        return
    pairs = {}
    for a in nums:
        for where, body in texts.get(str(a), []):
            for s in sentences(body):
                for b in refs(s, owner, name):
                    if b in box and b != a:
                        pairs.setdefault((a, b), []).append((0 if WORDS.search(s) else 1, where, s))
    for a in nums:
        mine = sorted(b for (x, b) in pairs if x == a)
        if not mine:
            continue
        s = snap.get(str(a)) or {}
        print('#%d %s %s: %s' % (a, kinds.get(a, '?'), s.get('state', '?'), s.get('title', '(not a box yet)')[:90]))
        for b in mine:
            got = sorted(pairs[(a, b)], key=lambda t: t[0])[:o.per_pair]
            for _, where, s in got:
                s = re.sub(r'\s+', ' ', s)
                print('   -> #%d [%s] %s' % (b, where, s[:o.width] + ('...' if len(s) > o.width else '')))
    print('%d items, %d pairs where one names another' % (len(nums), len(pairs)))


if __name__ == '__main__':
    main()
