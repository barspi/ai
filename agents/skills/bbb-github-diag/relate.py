#!/usr/bin/env python3
"""GitHub-native relations between boxes that the picture does not show yet.

A box whose updatedAt changed may have gained a relation on GitHub: a sub-issue, a parent, blocked by, blocking, closed by a pull
request, a pull request that closes an issue. When the other end is also a box, that relation is an arrow the picture should have.
refresh_meta.py --apply draws each missing one (through add_nodes.py: routed in the picture as it is, its label placed, jump arcs
redone) and reports the rest.

As a module:  relate.missing(svg_text, live, nums, texts, repo) -> (arrows [(from, to, kind)], report lines)
              relate.dropped(svg_text, old, live, nums, texts, repo) -> arrows to take out
  Besides GitHub's own links, the text of each box in nums (body and last comments) is read with the phrase rules of rules.py
  ("Blocked by #N", "Closes #N", "Follow-up to #N", ...; a negated phrase does not count): those relations are drawn too, except the
  weak words (related, references, mentioned), which are reported. A native link a box had at the last refresh and no longer has
  ("unblocked") takes its arrow out, unless the text still states it.
  nums: the boxes to look at (refresh_meta.py passes the ones whose updatedAt changed; a relation is looked at from both of its ends,
  so a change on either end finds it).
  - drawn already with the same word (either direction): nothing;
  - drawn with another word between the same two boxes: reported, not changed (which word is right is a judgment);
  - in the metadata's nopath list (a decision not to draw it, or no clean path before): reported, not drawn;
  - otherwise: returned, to be drawn.
As a command:  relate.py IN.svg [N ...]   prints what --apply would draw, from the records the file keeps (no network); no N: all boxes.
"""
import html, json, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svgmeta


def native(n, rec):
    """The relations of box n, each as an arrow sentence (A, B, word): A word B."""
    r = rec.get('rel') or {}
    out = [(n, c, 'child') for c in r.get('children', [])]
    if r.get('parent'):
        out.append((r['parent'], n, 'child'))
    out += [(n, c, 'blocked by') for c in r.get('blockedBy', [])]
    out += [(c, n, 'blocked by') for c in r.get('blocking', [])]
    out += [(n, c, 'closed by') for c in r.get('closedBy', [])]
    out += [(c, n, 'closed by') for c in r.get('closes', [])]
    return out


WEAK = ('related', 'references', 'mentioned')      # a passing mention: reported from the text, never drawn by itself


def from_text(texts, nums, boxes, kinds, repo):
    """Relations the text of each box in nums states to another box (its body and last comments: texts {n: [str, ...]}), by the phrase
    rules of rules.py, one per pair (rules.strongest). Returns [(kind, from, to, rule, n, sentence)]."""
    import mentions, rules
    owner, name = repo.split('/')
    found = []
    for a in nums:
        for body in texts.get(a, []):
            for s in mentions.sentences(body or ''):
                for b in sorted(x for x in mentions.refs(s, owner, name) if x in boxes and x != a):
                    m = rules.match(s, a, b, kinds, owner, name)
                    if m:
                        found.append(m + (a, re.sub(r'\s+', ' ', s)))
    return rules.strongest(found)


def dropped(text, old, live, nums, texts, repo):
    """Native relations a box in nums had at the last refresh (old records) and has no more on GitHub, still drawn with that word, and
    not stated in its text either: [(from, to, kind)] to take out ("unblocked", a sub-issue moved, a closing link removed)."""
    boxes = set(int(x) for x in re.findall(r'<g id="n(\d+)"', text))
    kinds = {n: (live.get(n) or {}).get('kind') for n in boxes}
    said = {(f, t, k) for k, f, t, *_ in from_text(texts, nums, boxes, kinds, repo)} if texts else set()
    drawn = set()
    for ln in text.split('\n'):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at:
            drawn.add(at)
    out = []
    for n in nums:
        if n not in old or n not in live or live[n].get('missing'):
            continue
        gone = set(native(n, old[n])) - set(native(n, live[n]))
        for a, b, k in sorted(gone):
            if (a, b, k) in drawn and (a, b, k) not in said and (a, b, k) not in out:
                out.append((a, b, k))
    return out


def missing(text, live, nums, texts=None, repo=None):
    """See the module text. texts (with repo): {n: [body, comment, ...]} of the boxes in nums; relations their text states are drawn
    too (the phrase rules of rules.py), except the weak words (related, references, mentioned), which are only reported."""
    boxes = set(int(x) for x in re.findall(r'<g id="n(\d+)"', text))
    drawn = {}
    for ln in text.split('\n'):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at:
            drawn.setdefault(frozenset(at[:2]), set()).add(at[2])
    meta = svgmeta.read(text) or {}
    skip = {(e['from'], e['to']) for e in meta.get('nopath', []) if isinstance(e, dict)}
    want, report, seen = [], [], set()
    rels = [(a, b, k) for n in nums if n in live and not live[n].get('missing') for a, b, k in native(n, live[n])]
    why = {}
    if texts and repo:
        kinds = {n: (live.get(n) or {}).get('kind') for n in boxes}
        for k, f, t, rule, a, s in from_text(texts, nums, boxes, kinds, repo):
            if k in WEAK:
                if not drawn.get(frozenset((f, t))):
                    report.append('#%d %s #%d in the text of #%d (a passing mention, not drawn): %s' % (f, k, t, a, s[:120]))
                continue
            rels.append((f, t, k))
            why[(f, t, k)] = 'the text of #%d says: %s' % (a, s[:120])
    words = {}                                       # every word GitHub has for a pair (a pair can be both child and blocked by)
    for a, b, k in rels:
        words.setdefault(frozenset((a, b)), set()).add(k)
    import rules
    rank = {k: i for i, k in enumerate(rules.RANK)}           # one arrow per pair: the strongest word (rules.RANK)
    for a, b, kind in sorted(rels, key=lambda r: rank.get(r[2], 99)):
        pair = frozenset((a, b))
        if a not in boxes or b not in boxes or a == b or pair in seen:
            continue
        seen.add(pair)
        have = drawn.get(pair, set())
        if have & words[pair]:                       # one arrow with one of GitHub's words is enough
            continue
        if have:
            report.append('#%d %s #%d on GitHub, drawn as %s: change the word by hand if GitHub is right' % (a, kind, b, ', '.join(sorted(have))))
        elif (a, b) in skip:
            report.append('#%d %s #%d on GitHub, in nopath (not drawn on purpose or no clean path): left out' % (a, kind, b))
        else:
            want.append((a, b, kind))
            if (a, b, kind) in why:
                report.append('drawn from the text: #%d %s #%d (%s)' % (a, kind, b, why[(a, b, kind)]))
    return want, report


def records(text):
    return {int(m.group(1)): json.loads(html.unescape(m.group(2))) for m in re.finditer(r'<g id="n(\d+)"[^>]*data-github="([^"]*)"', text)}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    t = open(sys.argv[1], encoding='utf-8').read()
    live = records(t)
    nums = [int(x.lstrip('#')) for x in sys.argv[2:]] or sorted(live)
    want, report = missing(t, live, nums)
    for a, b, k in want:
        print('DRAW #%d %s #%d' % (a, k, b))
    for r in report:
        print(r)
    print('%d to draw, %d reported' % (len(want), len(report)))
