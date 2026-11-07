#!/usr/bin/env python3
"""Fetch the text of every box (body and comments) and print each sentence in which one box names another, so the agent can READ how
the items relate (follow-up, led to, blocked by, supersedes, evidence, related, ...) and write those arrows itself.

usage: mentions.py OWNER/REPO snapshot.json texts.json [--per-pair 3] [--width 260]

- Box numbers come from the snapshot written by refresh_meta.py. The text is fetched with aliased GraphQL queries, 20 items per call
  (body, every comment with its author, and for a pull request its reviews' bodies), and saved to texts.json, so a second run with the
  same file does not call GitHub again (delete the file to fetch anew).
- A reference is `#N`, `PR #N`, `owner/repo#N` for this repository, or a github.com link to an issue or pull request of it. Only
  references to other boxes are printed: per pair (A names B), the first --per-pair sentences, cut at --width characters, with where
  each was found (`body`, `comment by login`). Sentences with a relation word (blocks, blocked, follow-up, closes, supersede, replace,
  led to, found, depends, evidence, related, ...) come first.
- Nothing here decides a relation. Read the sentences, open an item only when they are not enough, and write each arrow as an edge in
  graph.json (or an add_nodes.py spec) with the word of the vocabulary that fits its meaning. Never paste bodies into the conversation;
  this script prints only the sentences that name another box.
Needs the `gh` CLI, logged in.
"""
import argparse, json, os, re, subprocess, sys

FIELDS = """__typename
  ... on Issue { body comments(first:100){nodes{author{login} body}} }
  ... on PullRequest { body comments(first:100){nodes{author{login} body}} reviews(first:50){nodes{author{login} body}} }"""
WORDS = re.compile(r'block|follow[- ]?up|closes|closed by|fix(es|ed)? |supersed|replac|led to|found|depend|evidence|related|duplicate|'
                   r'split|child|parent|umbrella|prerequisite|after |instead|obsolete|gap|regression|revert', re.I)


def fetch(owner, name, nums):
    out = {}
    for i in range(0, len(nums), 20):
        part = nums[i:i + 20]
        q = 'query{repository(owner:"%s",name:"%s"){%s}}' % (owner, name, ' '.join('i%d:issueOrPullRequest(number:%d){%s}' % (n, n, FIELDS) for n in part))
        r = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + q], capture_output=True, text=True)
        if r.returncode:
            sys.exit('gh failed: ' + r.stderr.strip()[:400])
        d = json.loads(r.stdout)['data']['repository']
        for n in part:
            x = d.get('i%d' % n) or {}
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
        s = snap[str(a)]
        parts = texts.get(str(a), [])
        print('=== #%d %s %s: %s' % (a, s['kind'], s['state'], s['title']))
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo'); ap.add_argument('snapshot'); ap.add_argument('texts')
    ap.add_argument('--per-pair', type=int, default=3); ap.add_argument('--width', type=int, default=260)
    ap.add_argument('--digest', action='store_true', help='print a short digest of every box (to write its notes) instead of the pairs')
    ap.add_argument('--only', default='', help='N,N: limit --digest to these boxes')
    o = ap.parse_args()
    owner, name = o.repo.split('/')
    snap = json.load(open(o.snapshot, encoding='utf-8'))
    nums = sorted(int(k) for k in snap if k != '_meta')
    box = set(nums)
    if os.path.exists(o.texts):
        texts = json.load(open(o.texts, encoding='utf-8'))
    else:
        texts = fetch(owner, name, nums)
        json.dump(texts, open(o.texts, 'w', encoding='utf-8'), indent=0, ensure_ascii=False)
    if o.digest:
        only = {int(x) for x in o.only.replace('#', '').split(',') if x.strip()}
        digest([n for n in nums if not only or n in only], snap, texts, o.width)
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
        print('#%d %s %s: %s' % (a, snap[str(a)]['kind'], snap[str(a)]['state'], snap[str(a)]['title'][:90]))
        for b in mine:
            got = sorted(pairs[(a, b)], key=lambda t: t[0])[:o.per_pair]
            for _, where, s in got:
                s = re.sub(r'\s+', ' ', s)
                print('   -> #%d [%s] %s' % (b, where, s[:o.width] + ('...' if len(s) > o.width else '')))
    print('%d items, %d pairs where one names another' % (len(nums), len(pairs)))


if __name__ == '__main__':
    main()
