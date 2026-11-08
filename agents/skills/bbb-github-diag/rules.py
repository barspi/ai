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
5. Closed by hand (close_verdict()): the red cross on a closed issue means the work was not done (wrong, duplicate, won't do,
   won't fix, superseded, not needed). In this order, the first that applies decides:
   a. the user's recorded answer for that box (`rules.py closed IN.svg N hand|done "reason"`, the block's "closed" list);
   b. GitHub's close reason NOT_PLANNED or DUPLICATE: by hand;
   c. GitHub's close event names a merged pull request or a commit as the closer: done (on the diagram or not);
   d. the text, last comment first, then back to the body: a phrase of HAND_TEXT (duplicate of, won't fix, not planned, superseded,
      no longer needed, closing in favour of, out of scope, cannot reproduce, ...) means by hand, of DONE_TEXT (done in #N, fixed in
      <commit>, landed in, implemented in, closed by PR #N, ...) means done;
   e. otherwise ASK: read the last comments and the history, ask the user when they do not say, and record the answer (a).
   A pull request closed unmerged always has the cross: that is what closed unmerged means.
4. Review (review()): arrows a person should look at again, printed as ASK lines by check_diag.py, never failed:
   - stale-far: a medium or low arrow (not child, closed by, blocked by, depends on) whose tail was closed or merged at least
     STALE_DAYS before the diagram's last refresh (lastRun; today without one), that joins two different frames and is longer than
     FAR_FACTOR times the median arrow. A far origin whose work is over rarely matters to the reader; ask whether to keep it or drop
     it (svgmeta.py nopath). The thresholds come from a 198-arrow diagram, where the arrow a reader dropped was 16 times the median.
   - supersedes-missing: a box closed by hand, or a pull request closed unmerged, whose text names the box that replaced it
     ("superseded by #N", "in favour of #N"; refresh_meta.py stores it as replacedBy) with no arrow between them. Draw `supersedes`
     from the replacing pull request (its head is the red cross).
   - duplicate-missing: an issue closed as a duplicate (GitHub's "marked as duplicate" event, else "duplicate of #N" in its text;
     stored as duplicateOf) of a box, with no arrow between them. Draw `duplicate of` from the closed issue to the one that remains.
   - number-order: a led to, follow-up, spawned or revised by arrow whose tip has a lower number than its tail. GitHub numbers the
     issues and pull requests of a repository in creation order, so the tip was opened first. It can be right (an issue filed from
     the work of a pull request that was opened later); check the text and confirm.
   Once the user has answered, `rules.py accept IN.svg A B CHECK "reason"` stores it in the metadata block ("accepted") and the
   review does not ask again.

usage:
  rules.py frame IN.svg N --arrows 'A>N:kind,N>B:kind'     frame and near for a new box N, with the vote
  rules.py review IN.svg                                    the review findings (exit 0)
  rules.py accept IN.svg A B CHECK "reason"                 record an answer (CHECK: stale-far, number-order)
  rules.py closed IN.svg N hand|done "reason"               record why issue N was closed (wins over every other step)
  rules.py selftest                                         the phrase rules against a fixed set of sentences
"""
import datetime, json, os, re, statistics, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RANK = ['closed by', 'child', 'supersedes', 'duplicate of', 'revised by', 'work done by', 'evidence, does not close', 'follow-up', 'spawned',
        'led to', 'blocked by', 'depends on', 'references', 'related', 'mentioned']
STALE_DAYS = 7          # the tail ended at least this many days before the diagram's last refresh
FAR_FACTOR = 8.0        # and the arrow is longer than this many times the median arrow

# (name, phrase before the reference to B, kind, direction, condition)
# direction 'BA': the arrow goes from B to A (A is the item whose text holds the sentence); 'AB': from A to B.
# condition: None, or 'A_PR' / 'B_PR' / 'A_ISSUE' (the kind of item that end must be for the phrase to mean that relation).
PHRASES = [
    # the reference first: "#B (filed from this work)" in A's text means A's work produced B
    ('filed-from-this', None,                                                                    'led to',     'AB', None),
    ('duplicate-of',  r'\b(?:(?:a\s+)?duplicate\s+of|dup(?:e)?\s+of|duplicates)\s*:?\s*',               'duplicate of', 'AB', 'A_ISSUE'),
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
    (3, 2, 'Closing as a duplicate of #2.', ('duplicate of', 3, 2)),
    (1, 2, 'Duplicate of #2.', None),
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
    rec = {'kind': 'ISSUE', 'state': 'closed', 'stateReason': 'COMPLETED'}
    for t, want in CLOSE_SELFTEST:
        got = close_verdict(rec, [t])[0]
        if got != want:
            bad.append(t)
            print('FAIL close %r: got %s, want %s' % (t, got, want))
    print('rules self-test %s (%d arrow sentences, %d close sentences)' % ('OK' if not bad else 'FAILED', len(SELFTEST), len(CLOSE_SELFTEST)))
    return not bad


# ---------------------------------------------------------------- closed by hand

HAND_TEXT = re.compile(r"\b(?:duplicate\s+(?:of|to)|dup(?:e)?\s+of|won'?t\s+(?:fix|do)|wontfix|will\s+not\s+(?:fix|do)|not\s+planned|"
                       r"closing\s+(?:this\s+)?(?:as|because)\s+(?:invalid|obsolete|stale|a\s+duplicate|not\s+planned|won'?t)|"
                       r"(?:is|now|as)\s+obsolete|superseded\s+by|no\s+longer\s+(?:needed|relevant|applies|applicable)|not\s+needed\s+any\s*more|"
                       r"closing\s+in\s+favou?r\s+of|out\s+of\s+scope|can(?:not|'t)\s+reproduce|abandon(?:ed|ing))\b", re.I)
DONE_TEXT = re.compile(r"\b(?:(?:done|fixed|landed|implemented|resolved|merged|delivered|completed|shipped|addressed)\s+(?:in|by|with|via)\s+"
                       r"(?:(?:one|a|the|this|that)\s+)?(?:PR|pull\s+request|commit)?[\s,:]*(?:#\d+|`?[0-9a-f]{7,40}\b)|"
                       r"closed\s+by\s+(?:PR\s*)?#\d+|implementation\s+(?:PR|pull\s+request)\s*:?\s*#\d+|closing\s*:\s*(?:PR\s*)?#\d+)", re.I)
CLOSE_SELFTEST = [          # (text, verdict) for close_verdict step d; `rules.py selftest` runs them too
    ('Closing as a duplicate of #12.', 'hand'), ("Won't fix: the scheme dropped the field.", 'hand'), ('Superseded by #77; closing.', 'hand'),
    ('No longer needed after the redesign.', 'hand'), ('Fixed in #44.', 'done'), ('All five slices landed in one PR, #1782.', 'done'),
    ('Implementation PR: #1782 (all five sub-issues).', 'done'), ('Closing: #1802 peels the amount, and #1896 covers the rest.', 'done'),
    ('Done in 3229bfa45.', 'done'), ('the DE39 was invalid in the log', 'ask'), ('thanks, looks good', 'ask')]


def close_verdict(rec, texts=None, decided=None):
    """(verdict, why) for a closed issue: 'hand' (red cross), 'done' (no cross) or 'ask'; None for anything else. rec: the box's
    GitHub record (refresh_meta.py: stateReason, closer); texts: [body, comment, ..., last comment]; decided: {'verdict', 'reason'}
    from the block's "closed" list. The order is in the module text (5a to 5e)."""
    if not rec or rec.get('kind') != 'ISSUE' or rec.get('state') != 'closed':
        return None, ''
    if decided:
        return decided['verdict'], 'recorded: %s' % decided.get('reason', '')
    reason = (rec.get('stateReason') or '').upper()
    if reason in ('NOT_PLANNED', 'DUPLICATE'):
        return 'hand', 'GitHub close reason %s' % reason
    c = rec.get('closer') or {}
    if c.get('pr') and c.get('merged'):
        return 'done', 'closed by merged PR #%d' % c['pr']
    if c.get('commit'):
        return 'done', 'closed by commit %s' % c['commit']
    for t in reversed(texts or []):
        h, d = HAND_TEXT.search(t or ''), DONE_TEXT.search(t or '')
        if h or d:
            m = h if h and (not d or h.start() <= d.start()) else d
            return ('hand' if m is h else 'done'), 'text: "%s"' % re.sub(r'\s+', ' ', (t or '')[max(0, m.start() - 40):m.end() + 40]).strip()
    return 'ask', 'closed as %s with no merged pull request or commit as closer, and no phrase in its last comments says why' % (reason or 'completed').lower()


REPLACED_BY = re.compile(r"\b(?:superseded\s+by|replaced\s+by|closing\s+in\s+favou?r\s+of|in\s+favou?r\s+of)\s*:?\s*(?:PR\s*)?#(\d+)", re.I)
DUPLICATE_OF = re.compile(r"\b(?:duplicate\s+of|dup(?:e)?\s+of)\s*:?\s*#(\d+)", re.I)


def _last(pattern, texts):
    for t in reversed(texts or []):
        m = pattern.search(t or '')
        if m:
            return int(m.group(1))
    return None


def replaced_by(texts):
    """The item that replaced this one, from its text (last comment first): "superseded by #N", "in favour of #N"."""
    return _last(REPLACED_BY, texts)


def duplicate_of(texts):
    """The issue this one duplicates, from its text (last comment first): "duplicate of #N"."""
    return _last(DUPLICATE_OF, texts)


def needs_text(rec):
    """True when close_verdict cannot decide from the record alone (step d)."""
    v, _ = close_verdict(rec)
    return v == 'ask'


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
                        '(svgmeta.py drop IN.svg %d %d "reason")' % (
                            a, kind, b, a, ended, (asof - ended).days, length, length / median, a, b, a, b)})
        pass
    drawn_pairs = {(min(a, b), max(a, b)) for (a, b, _), _ in arrows}
    for n, v in sorted(bx.items()):
        g = v.get('github') or {}
        d = g.get('duplicateOf')
        if d and d in bx and d != n and (min(n, d), max(n, d)) not in drawn_pairs and (n, d, 'duplicate-missing') not in done:
            out.append({'check': 'duplicate-missing', 'from': n, 'to': d, 'kind': 'duplicate of', 'message':
                        '#%d was closed as a duplicate of #%d, but no arrow joins them. Draw `duplicate of` from #%d to #%d (add_nodes.py '
                        'arrow), or record why not: rules.py accept IN.svg %d %d duplicate-missing "reason"' % (n, d, n, d, n, d)})
            continue
        r = g.get('replacedBy')
        if r and r in bx and r != n and (min(n, r), max(n, r)) not in drawn_pairs and (r, n, 'supersedes-missing') not in done:
            out.append({'check': 'supersedes-missing', 'from': r, 'to': n, 'kind': 'supersedes', 'message':
                        '#%d was closed for #%d (its text says so), but no arrow joins them. Draw `supersedes` from #%d to #%d when #%d is '
                        'the pull request that replaced it (add_nodes.py arrow), `related` for a duplicate issue, or record why not: '
                        'rules.py accept IN.svg %d %d supersedes-missing "reason"' % (n, r, r, n, r, r, n)})
    for (a, b, kind), length in arrows:
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
    elif cmd == 'closed':
        if len(a) != 5 or a[3] not in ('hand', 'done'):
            sys.exit(__doc__)
        meta = svgmeta.read(text)
        if meta is None:
            sys.exit('%s has no metadata block: run svgmeta.py migrate first' % path)
        n = int(a[2].lstrip('#'))
        meta['closed'] = [x for x in meta.get('closed', []) if x['num'] != n] + [
            {'num': n, 'verdict': a[3], 'reason': a[4], 'date': datetime.date.today().isoformat()}]
        open(path, 'w', encoding='utf-8').write(svgmeta.write(text, meta))
        print('updated %s: #%d closed %s (run refresh_meta.py --apply to draw it)' % (path, n, 'by hand' if a[3] == 'hand' else 'with the work done'))
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
        if check not in ('stale-far', 'number-order', 'supersedes-missing', 'duplicate-missing'):
            sys.exit('CHECK is stale-far, number-order, supersedes-missing or duplicate-missing')
        acc = [x for x in meta.get('accepted', []) if (x['from'], x['to'], x['check']) != (fa, fb, check)]
        meta['accepted'] = acc + [{'from': fa, 'to': fb, 'check': check, 'reason': reason, 'date': datetime.date.today().isoformat()}]
        open(path, 'w', encoding='utf-8').write(svgmeta.write(text, meta))
        print('updated %s' % path)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
