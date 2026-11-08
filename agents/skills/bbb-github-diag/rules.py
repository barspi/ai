#!/usr/bin/env python3
"""The decisions of a diagram that used to be judgment, written as fixed rules with fixed tie-breaks, so every agent and model that uses
this skill decides them the same way. A rule proposes; the agent confirms against GitHub and the user decides what a rule cannot.

1. Arrow kind from text (PHRASES, candidates()). A sentence in A's text that names box B, matched against an ordered list of phrases:
   the first phrase that matches gives the kind and the direction. One arrow per pair: the strongest kind (RANK). A sentence that names
   three or more boxes and matches no phrase is a list ("Refs #a, #b, #c") and gives nothing. mentions.py --candidates prints each
   candidate with the sentence and the rule that produced it, and the pairs no rule matched, for the agent to judge.
2. Frame of a new box (frame_for()). Each arrow between the new box and a box already drawn votes for that box's frame (no frame is a
   candidate too) with its importance (draw.IMPORTANCE: 3, 2, 1); the roots do not vote. Highest total wins; ties: a frame before
   none, then more arrows, then the frame of the lowest-numbered neighbour (the oldest item). A box whose only arrows go to a root is
   an ASK: no rule knows its topic. add_nodes.py applies it to a box whose spec has no "frame".
3. The box a new one is placed beside (near_for()): the neighbour with the most important arrow; ties: the lowest number.
4. Review (review()): arrows a person should look at again, printed as ASK lines by check_diag.py, never failed:
   - stale-far: a medium or low arrow (not child, closed by, blocked by, depends on) whose tail was closed or merged at least
     STALE_DAYS before the diagram's last refresh (lastRun; today without one), that joins two different frames and is longer than
     FAR_FACTOR times the median arrow. A far origin whose work is over rarely matters to the reader; ask whether to keep it or drop
     it (svgmeta.py nopath). The thresholds come from a 198-arrow diagram, where the arrow a reader dropped was 16 times the median.
   - number-order: a led to, follow-up, spawned or revised by arrow whose tip has a lower number than its tail. GitHub numbers the
     issues and pull requests of a repository in creation order, so the tip was opened first. It can be right (an issue filed from
     the work of a pull request that was opened later); check the text and confirm.
   Once the user has answered, `rules.py accept IN.svg A B CHECK "reason"` stores it in the metadata block ("accepted") and the
   review does not ask again.

usage:
  rules.py frame IN.svg N --arrows 'A>N:kind,N>B:kind'     frame and near for a new box N, with the vote
  rules.py review IN.svg                                    the review findings (exit 0)
  rules.py accept IN.svg A B CHECK "reason"                 record an answer (CHECK: stale-far, number-order)
  rules.py selftest                                         the phrase rules against a fixed set of sentences
"""
import datetime, json, os, re, statistics, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RANK = ['closed by', 'child', 'supersedes', 'revised by', 'work done by', 'evidence, does not close', 'follow-up', 'spawned',
        'led to', 'blocked by', 'depends on', 'references', 'related', 'mentioned']
STALE_DAYS = 7          # the tail ended at least this many days before the diagram's last refresh
FAR_FACTOR = 8.0        # and the arrow is longer than this many times the median arrow

# (name, phrase before the reference to B, kind, direction, condition)
# direction 'BA': the arrow goes from B to A (A is the item whose text holds the sentence); 'AB': from A to B.
# condition: None, or 'A_PR' / 'B_PR' / 'A_ISSUE' (the kind of item that end must be for the phrase to mean that relation).
PHRASES = [
    # the reference first: "#B (filed from this work)" in A's text means A's work produced B
    ('filed-from-this', None,                                                                    'led to',     'AB', None),
    ('closes',        r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*',                    'closed by',  'BA', 'A_PR'),
    ('closed-by',     r'\b(?:closed|fixed|resolved)\s+(?:by|in)\s*:?\s*',                        'closed by',  'AB', 'B_PR'),
    ('superseded-by', r'\bsuperseded\s+by\s*:?\s*',                                              'supersedes', 'BA', None),
    ('supersedes',    r'\b(?:supersedes|replaces)\s*:?\s*',                                      'supersedes', 'AB', None),
    ('follow-up-to',  r'\bfollow[- ]?up\s+(?:to|of|for|from|on)\s*:?\s*',                        'follow-up',  'BA', None),
    ('follow-up-in',  r'\bfollow[- ]?ups?\s*(?::|(?:(?:are|is|was|were)\s+)?(?:\bin\b|\bfiled\s+as\b|\btracked\s+in\b)|\bis\b)\s*',
                                                                                                  'follow-up',  'AB', None),
    ('found-while',   r'\b(?:found\s+(?:while|during|in|by)|filed\s+from|spun\s+off\s+from|spin-?off\s+(?:of|from)|came\s+out\s+of|split\s+(?:out\s+)?(?:of|from))\b[^.;,()#]{0,40}?\(?',
                                                                                                  'led to',     'BA', None),
    ('led-to',        r'\b(?:led\s+to|spawned|filed\s+as|moved\s+to)\s*:?\s*',                 'led to',     'AB', None),
    ('blocked-by',    r'\b(?:blocked\s+(?:by|on)|on\s+hold\s+until|do\s+not\s+start\s+until|waiting\s+(?:for|on))\s*:?\s*',
                                                                                                  'blocked by', 'AB', None),
    ('blocks',        r'\bblocks\s*:?\s*',                                                       'blocked by', 'BA', None),
    ('depends-on',    r'\b(?:depends\s+on|needs\s+the\s+result\s+of|requires|lands?\s+(?:with\s+or\s+)?after)\s*:?\s*',
                                                                                                  'depends on', 'AB', None),
    ('part-of-pr',    r'\b(?:part\s+of|towards?|contributes\s+to|does\s+not\s+close|partially\s+(?:fixes|addresses))\s*:?\s*',
                                                                                                  'work done by', 'BA', 'A_PR'),
    ('child-of',      r'\b(?:epic|child\s+of|parent\s*:|umbrella\s*:|part\s+of)\s*:?\s*',          'child',      'BA', 'A_ISSUE'),
    ('revises',       r'\b(?:revises|amends|reworks|re-?lands)\s*:?\s*',                                   'revised by', 'BA', 'A_PR'),
    ('evidence-for',  r'\bevidence\s+(?:for|of)\s*:?\s*',                                        'evidence, does not close', 'BA', None),
    ('related',       r'\b(?:related(?:\s+to)?|see\s+also|cf\.?)\s*:?\s*',                       'related',    'AB', None),
]


LIST = r'(?:(?:(?:PR\s*)?(?:[\w.-]+/[\w.-]+)?#\d+|https?://\S+)(?:\s*\([^()]{0,60}\))?\s*(?:,|\band\b|&|/)\s*){0,8}'   # "Closes #1, #2 and #3": the phrase covers every item of a list


def ref_pattern(owner, name, b):
    """A reference to item b in GitHub text: #b, PR #b, owner/name#b, or a link to its issue or pull page."""
    return (r'(?:(?:PR|pull request|issue)\s*)?(?:(?:%s/%s)?#%d\b|https?://github\.com/%s/%s/(?:issues|pull)/%d\b)'
            % (re.escape(owner), re.escape(name), b, re.escape(owner), re.escape(name), b))


NEGATION = re.compile(r'(?:\b(?:not|no longer|never|without|instead of|remove[sd]?|drop(?:ped|s)?|rather than)\b[^.;]{0,12}|["\'`\u201c\u2018])\s*$', re.I)
SUBJECT = re.compile(r'#(\d+)\)?\s*:?\s*$')


def match(sentence, a, b, kinds, owner, name):
    """(kind, from, to, rule name) for the first phrase that relates A (the text's item) and B in this sentence, or None.
    A phrase does not count when it is negated or quoted just before it ("do not close", "Remove 'Closes #N'"), or when another item's
    number stands right before it ("#X closed by #B" in A's text is about X, not A)."""
    ref = ref_pattern(owner, name, b)
    sentence = re.sub(r'\*{1,3}|_{2,3}', '', sentence)             # markdown emphasis: "Follow-up:** #N" reads "Follow-up: #N"
    for rule, phrase, kind, direction, cond in PHRASES:
        if cond == 'A_PR' and kinds.get(a) != 'PR' or cond == 'A_ISSUE' and kinds.get(a) != 'ISSUE' or cond == 'B_PR' and kinds.get(b) != 'PR':
            continue
        if phrase is None:                                   # filed-from-this: the reference, then the phrase
            if re.search(ref + r'\s*\(\s*(?:filed|found|spun off)\s+(?:from|during|in)\s+this\s+(?:work|pr|pull request|issue)\b', sentence, re.I):
                return (kind, a, b, rule)
            continue
        for m in re.finditer(phrase + LIST + ref, sentence, re.I):
            before = sentence[:m.start()]
            subj = SUBJECT.search(before)
            if NEGATION.search(before) or (subj and int(subj.group(1)) != a):
                continue
            return (kind, b, a, rule) if direction == 'BA' else (kind, a, b, rule)
    return None


def strongest(cands):
    """One arrow per pair of boxes: the strongest kind by RANK; ties keep the first found. cands: [(kind, from, to, ...)]."""
    best = {}
    for c in cands:
        key = (min(c[1], c[2]), max(c[1], c[2]))
        if key not in best or RANK.index(c[0]) < RANK.index(best[key][0]):
            best[key] = c
    return [best[k] for k in sorted(best)]


# A fixed set of sentences and the arrow each must give (owner "acme", name "shop"; 1 and 4 are pull requests, the rest issues).
# `rules.py selftest` runs them: a change to PHRASES must keep them all.
SELFTEST_KINDS = {1: 'PR', 2: 'ISSUE', 3: 'ISSUE', 4: 'PR', 5: 'ISSUE'}
SELFTEST = [
    (1, 2, 'Closes #2.', ('closed by', 2, 1)),
    (1, 3, 'Closes #2, #3 and #5.', ('closed by', 3, 1)),
    (2, 4, 'Fixed in PR #4.', ('closed by', 2, 4)),
    (1, 2, 'This does not close #2.', ('work done by', 2, 1)),
    (3, 2, 'This does not close #2.', None),
    (1, 2, 'Remove "Closes #2" from the description.', None),
    (3, 4, '#5 closed by #4.', None),
    (3, 2, 'Follow-up to #2: the remaining fields.', ('follow-up', 2, 3)),
    (2, 3, 'Follow-up:** #3', ('follow-up', 2, 3)),
    (4, 3, 'The follow-ups are filed as #5 (the pin) and #3 (the short field).', ('follow-up', 4, 3)),
    (3, 1, 'Found while reviewing PR #1.', ('led to', 1, 3)),
    (3, 2, 'Found while working on the contracts (#2).', ('led to', 2, 3)),
    (4, 3, 'Related: #3 (filed from this work), #5, #2.', ('led to', 4, 3)),
    (4, 5, 'Related: #3 (filed from this work), #5, #2.', ('related', 4, 5)),
    (3, 2, 'Blocked by #2 (Q1).', ('blocked by', 3, 2)),
    (2, 3, 'This blocks #3.', ('blocked by', 3, 2)),
    (4, 1, 'Superseded by #1.', ('supersedes', 1, 4)),
    (1, 4, 'Re-lands #4, which was reverted.', ('revised by', 4, 1)),
    (4, 2, 'Part of #2, does not close it.', ('work done by', 2, 4)),
    (3, 5, 'Child of #5', ('child', 5, 3)),
    (3, 2, 'Depends on acme/shop#2.', ('depends on', 3, 2)),
    (1, 4, 'Land with or after #4.', ('depends on', 1, 4)),
    (3, 5, 'Related: #5', ('related', 3, 5)),
    (3, 5, 'See also https://github.com/acme/shop/issues/5', ('related', 3, 5)),
    (3, 5, 'Refs #5, #2, #1', None),
    (3, 5, 'See https://github.com/acme/shop/issues/5 for the log', None),
]


def selftest():
    bad = [(a, b, s, want, match(s, a, b, SELFTEST_KINDS, 'acme', 'shop')) for a, b, s, want in SELFTEST]
    bad = [(a, b, s, want, got[:3] if got else None) for a, b, s, want, got in bad if (got[:3] if got else None) != want]
    for a, b, s, want, got in bad:
        print('FAIL A=#%d B=#%d %r: got %s, want %s' % (a, b, s, got, want))
    print('rules self-test %s (%d sentences)' % ('OK' if not bad else 'FAILED', len(SELFTEST)))
    return not bad


# ---------------------------------------------------------------- frame and near for a new box

def frame_for(num, arrows, frames, roots=()):
    """arrows: [(from, to, kind)] that touch num; frames: {box: frame name or None} for the boxes already placed; roots: the
    diagram's roots, which do not vote (a root forks into every frame, so its own place says nothing about the new box).
    Returns (frame or None, vote list [(frame, score, count, lowest neighbour)], reason)."""
    import draw
    vote, to_root = {}, False
    for a, b, kind in arrows:
        other = b if a == num else a
        to_root = to_root or other in roots
        if other == num or other not in frames or other in roots:
            continue
        f = frames[other]
        s, c, low = vote.get(f, (0, 0, other))
        vote[f] = (s + draw.IMPORTANCE.get(kind, 2), c + 1, min(low, other))
    if not vote:
        if to_root:
            return None, [], 'ASK: its only arrows go to a root, which does not say which frame; ask the user (outside every frame until then)'
        return None, [], 'no arrow to a box already drawn: outside every frame'
    ranked = sorted(vote.items(), key=lambda kv: (-kv[1][0], kv[0] is None, -kv[1][1], kv[1][2]))
    table = [(f, s, c, low) for f, (s, c, low) in ranked]
    win = table[0]
    tie = len(table) > 1 and table[1][1] == win[1]
    reason = 'importance %d from %d arrow(s)%s' % (win[1], win[2], ', tie broken (a frame before none, more arrows, lowest neighbour)' if tie else '')
    return win[0], table, reason


def near_for(num, arrows, placed):
    """The placed box joined to num by the most important arrow; ties: the lowest number."""
    import draw
    cands = [((b if a == num else a), draw.IMPORTANCE.get(kind, 2)) for a, b, kind in arrows]
    cands = [(o, w) for o, w in cands if o != num and o in placed]
    return min(cands, key=lambda ow: (-ow[1], ow[0]))[0] if cands else None


# ---------------------------------------------------------------- review

def _day(s):
    try:
        return datetime.date.fromisoformat((s or '')[:10])
    except ValueError:
        return None


def review(text):
    """[{'check', 'from', 'to', 'kind', 'message'}] for the arrows a person should look at again (see the module text)."""
    import draw, model, svgmeta
    meta = svgmeta.read(text) or {}
    done = {(x.get('from'), x.get('to'), x.get('check')) for x in meta.get('accepted', [])}
    bx = svgmeta.boxes(text)
    arrows = []
    for ln in text.split('\n'):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at:
            pts = model.arrow_points(ln)
            arrows.append((at, sum(abs(x2 - x1) + abs(y2 - y1) for (x1, y1), (x2, y2) in zip(pts, pts[1:]))))
    if not arrows:
        return []
    median = statistics.median(l for _, l in arrows)
    asof = _day(meta.get('lastRun')) or datetime.date.today()
    out = []
    for (a, b, kind), length in arrows:
        ga, gb = (bx.get(a) or {}).get('github') or {}, (bx.get(b) or {}).get('github') or {}
        ended = _day(ga.get('mergedAt') or ga.get('closedAt'))
        if (a, b, 'stale-far') not in done and draw.IMPORTANCE.get(kind, 2) < 3 and ended and (asof - ended).days >= STALE_DAYS \
                and bx.get(a, {}).get('frame') != bx.get(b, {}).get('frame') and length > FAR_FACTOR * median:
            out.append({'check': 'stale-far', 'from': a, 'to': b, 'kind': kind, 'message':
                        '#%d %s #%d: #%d ended %s, %d days before the last refresh; the arrow joins two frames and is %.0fpx long '
                        '(%.1f x the median). Keep it (rules.py accept IN.svg %d %d stale-far "reason"), or drop it '
                        '(svgmeta.py nopath IN.svg %d %d "%s" "reason", then remove the path)' % (
                            a, kind, b, a, ended, (asof - ended).days, length, length / median, a, b, a, b, kind)})
        if (a, b, 'number-order') not in done and kind in ('led to', 'follow-up', 'spawned', 'revised by') and b < a:
            out.append({'check': 'number-order', 'from': a, 'to': b, 'kind': kind, 'message':
                        '#%d %s #%d, but #%d was opened first (lower number; opened %s and %s). Right when #%d was filed from the work '
                        'that #%d later carried; check the text, then record it: rules.py accept IN.svg %d %d number-order "reason"' % (
                            a, kind, b, b, gb.get('createdAt', '?'), ga.get('createdAt', '?'), b, a, a, b)})
    return out


# ---------------------------------------------------------------- command line

def main():
    a = sys.argv[1:]
    if a == ['selftest']:
        sys.exit(0 if selftest() else 1)
    if len(a) < 2:
        sys.exit(__doc__)
    cmd, path = a[0], a[1]
    text = open(path, encoding='utf-8').read()
    import svgmeta
    if cmd == 'frame':
        if len(a) != 5 or a[3] != '--arrows':
            sys.exit(__doc__)
        num = int(a[2].lstrip('#'))
        arrows = []
        for part in a[4].split(','):
            m = re.match(r'\s*#?(\d+)\s*>\s*#?(\d+)\s*:\s*(.+?)\s*$', part)
            if not m:
                sys.exit('arrow %r: write A>B:kind' % part)
            arrows.append((int(m.group(1)), int(m.group(2)), m.group(3)))
        frames = {n: v['frame'] for n, v in svgmeta.boxes(text).items()}
        f, table, why = frame_for(num, arrows, frames, (svgmeta.read(text) or {}).get('roots', ()))
        print('frame: %s  (%s)' % (repr(f) if f else 'outside every frame', why))
        for fr, s, c, low in table:
            print('  %-60s importance %d, %d arrow(s), lowest neighbour #%d' % ((fr or '(no frame)')[:60], s, c, low))
        print('near: #%s' % near_for(num, arrows, set(frames)))
    elif cmd == 'review':
        fs = review(text)
        for f in fs:
            print('ASK %s: %s' % (f['check'], f['message']))
        print('%d review findings' % len(fs))
    elif cmd == 'accept':
        if len(a) != 6:
            sys.exit(__doc__)
        meta = svgmeta.read(text)
        if meta is None:
            sys.exit('%s has no metadata block: run svgmeta.py migrate first' % path)
        fa, fb, check, reason = int(a[2].lstrip('#')), int(a[3].lstrip('#')), a[4], a[5]
        if check not in ('stale-far', 'number-order'):
            sys.exit('CHECK is stale-far or number-order')
        acc = [x for x in meta.get('accepted', []) if (x['from'], x['to'], x['check']) != (fa, fb, check)]
        meta['accepted'] = acc + [{'from': fa, 'to': fb, 'check': check, 'reason': reason, 'date': datetime.date.today().isoformat()}]
        open(path, 'w', encoding='utf-8').write(svgmeta.write(text, meta))
        print('updated %s' % path)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
