#!/usr/bin/env python3
"""One command for a revision: runs every mechanical step, then stops with a numbered list of the points that need a judgment.

usage: revise.py OLD.svg NEW.svg [--add N[,N...]] [--keep-new] [--discover] [--answers FILE] [--render] [--repo OWNER/NAME]

Steps (each one is safe to run again, so a second run with --answers continues where the first stopped):
  1. new_revision.py OLD NEW [--keep-new]          (skipped when NEW exists: a rerun continues on it)
  2. refresh_meta.py --apply [--discover]          states, titles, assignees, relations of every box GitHub changed
  3. the items of --add that are not boxes yet: two GraphQL calls (refresh_meta.fetch_records, fetch_texts); the spec is built
     from GitHub alone: state, title, date line, author or assignees, umbrella, a `new` pill, and an arrow for each link to a box or
     to another added item: GitHub's own (closing reference, sub-issue, parent, blocked by, blocking, closed by) or a phrase of the
     item's body and last comments by the rules of rules.py ("Follow-up to #N", "Blocked by #N", ...; a weak word such as
     "Related:" is a passing mention, not a link); frame and place by rules.frame_for and rules.near_for (add_nodes.py). An item
     with no such link is not added: it is a decision (which arrow, or skip it).
  4. add_nodes.py                                  places the boxes, routes the arrows
  5. refresh_meta.py --apply                       stores the records of the new boxes and draws what their texts state (relate.py)
  6. check_diag.py NEW OLD [--keep-new]
  7. --render: render_region.py of the area of the added boxes (a PNG in the temp folder; look at it)

Prints: what was done, then DECISIONS (numbered) and FAILS. Exit 0 when there are none, 3 otherwise. The full output of every step
is in the log file it names (read it only when a line of the summary is not enough).

--answers FILE (JSON), written after reading the decisions:
  {"arrows": [{"from": 120, "to": 131, "kind": "closed by"}],     extra arrows (for an added item, or between boxes)
   "boxes":  {"131": {"frame": "...", "near": 120}},              spec fields for an added item
   "skip":   [133],                                               --add items not to draw
   "ack":    ["#45: shows ISSUE"]}                                decisions already settled: a line that contains one of these is not listed
"""
import argparse, json, os, re, subprocess, sys, tempfile, time
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PR_STATE = {'draft': 'draft', 'open': 'waiting', 'merged': 'merged', 'closed': 'prclosed'}


def run(log, *args):
    t = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, args[0])] + list(args[1:]), capture_output=True, text=True)
    log.write('\n===== %s (%.1fs, exit %d)\n%s%s' % (' '.join(args), time.time() - t, r.returncode, r.stdout, r.stderr))
    return r


def refresh_lines(out):
    """(done, decisions, candidates) from refresh_meta.py's output."""
    done, need, cand, in_disc = [], [], [], False
    for ln in out.splitlines():
        s = ln.strip()
        if ln.startswith('--- created, closed or merged since'):
            in_disc = True
            continue
        if in_disc:
            if s.startswith('#'):
                cand.append(s)
            continue
        if s.startswith('NEEDS A HUMAN:'):
            need.append(s[len('NEEDS A HUMAN:'):].strip())
        elif ln.startswith('  ') and s and not s.startswith('---'):
            done.append(s)
    return done, need, cand


def box_rect(text, n):
    m = re.search(r'<g id="n%d"[^>]*>.*?<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"' % n, text, re.S)
    return tuple(float(v) for v in m.groups()) if m else None


def spec_for(repo, live, adds, boxes, answers, texts=None, kinds=None):
    """The add_nodes.py spec for the items in adds (records in live), the decisions for the ones nothing links to a box, and a note
    for each arrow taken from a text. A link is GitHub's own (relate.native) or a phrase of the item's text (texts {n: [body,
    comment, ...]}; relate.from_text with the phrase rules of rules.py, "Follow-up to #N", "Blocked by #N", ...); a weak word
    (relate.WEAK: related, references, mentioned) is a passing mention and is not a link. kinds {n: 'ISSUE'|'PR'} of the boxes."""
    import relate, rules
    rank = {k: i for i, k in enumerate(rules.RANK)}
    ends = set(boxes) | set(adds)
    extra = answers.get('arrows', [])
    kinds = dict(kinds or {})
    kinds.update({n: (live.get(n) or {}).get('kind') for n in adds})
    out_boxes, arrows, need, notes, seen = [], [], [], {}, set()
    for n in adds:
        rec = live.get(n) or {}
        if rec.get('missing'):
            need.append('#%d: not found on GitHub: skip it' % n)
            continue
        rels = [r for r in relate.native(n, rec) if (r[1] if r[0] == n else r[0]) in ends and r[0] != r[1]]
        if (texts or {}).get(n):
            for k, f, t, rule, a, s in relate.from_text({n: texts[n]}, [n], ends, kinds, repo):
                if k not in relate.WEAK:
                    rels.append((f, t, k))
                    notes.setdefault((f, t, k), 'the text of #%d says: %s' % (a, s[:100]))
        rels = sorted(rels, key=lambda r: rank.get(r[2], 99))
        rels += [(a['from'], a['to'], a['kind']) for a in extra if n in (a['from'], a['to'])]
        if not rels:
            need.append('#%d (%s, %s): no link to a box, on GitHub or in its text. Give it an arrow in --answers ("arrows"), '
                        'or "skip" it' % (n, rec.get('kind'), rec.get('title', '')[:80]))
            continue
        pr = rec['kind'] == 'PR'
        st = rec['state']
        if pr:
            state = PR_STATE.get(st, st)
        else:
            v = rules.close_verdict(rec, None, None)[0] if st == 'closed' else None
            state = 'handclosed' if v == 'hand' else st
        end = ('merged ' + rec['mergedAt']) if st == 'merged' else ('closed ' + rec['closedAt']) if st == 'closed' else 'still open'
        b = {'num': n, 'state': state, 'title': rec['title'], 'meta': 'opened %s · %s' % (rec['createdAt'], end), 'new': True}
        if pr:
            b['author'] = rec.get('opener', '?')
            if st == 'merged' and rec.get('mergeSha'):
                from svg_state import authors_text
                b['mono'] = 'merge %s (%s)' % (rec['mergeSha'], authors_text(rec.get('authors') or [rec.get('opener', '?')]))
        else:
            b['assignees'] = rec.get('assignees', [])
            if (rec.get('rel') or {}).get('children'):
                b['umbrella'] = True
        b.update({k: v for k, v in (answers.get('boxes', {}).get(str(n)) or {}).items()})
        out_boxes.append(b)
        for a, c, k in rels:
            if frozenset((a, c)) not in seen:
                seen.add(frozenset((a, c)))
                arrows.append({'from': a, 'to': c, 'kind': k})
    for a in extra:                                   # arrows between boxes already drawn
        if a['from'] not in adds and a['to'] not in adds and frozenset((a['from'], a['to'])) not in seen:
            arrows.append({'from': a['from'], 'to': a['to'], 'kind': a['kind']})
    return {'repo': repo, 'boxes': out_boxes, 'arrows': arrows}, need, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('old'); ap.add_argument('new')
    ap.add_argument('--add', default=''); ap.add_argument('--keep-new', action='store_true')
    ap.add_argument('--discover', action='store_true'); ap.add_argument('--answers')
    ap.add_argument('--render', action='store_true'); ap.add_argument('--repo')
    o = ap.parse_args()
    t0 = time.time()
    answers = json.load(open(o.answers)) if o.answers else {}
    ack = answers.get('ack', [])
    adds = [int(x.lstrip('#')) for x in re.split(r'[,\s]+', o.add) if x.strip()]
    adds = [n for n in adds if n not in answers.get('skip', [])]
    logp = os.path.join(tempfile.gettempdir(), os.path.basename(o.new) + '.revise.log')
    log = open(logp, 'a', encoding='utf-8')
    done, need, fails, cand = [], [], [], []
    keep = ['--keep-new'] if o.keep_new else []

    if not os.path.exists(o.new):
        r = run(log, 'new_revision.py', o.old, o.new, *keep)
        if r.returncode:
            sys.exit('new_revision.py failed: ' + (r.stderr or r.stdout).strip())
        done.append(r.stdout.splitlines()[0] if r.stdout else 'new revision made')
    else:
        done.append('%s exists: continuing on it' % o.new)
    text = open(o.new, encoding='utf-8').read()
    repo = o.repo or re.search(r'https://github\.com/([\w.-]+/[\w.-]+)/(?:issues|pull)/\d+', text).group(1)

    r = run(log, 'refresh_meta.py', repo, o.new, '--apply', *(['--discover'] if o.discover else []))
    if r.returncode:
        sys.exit('refresh_meta.py failed: ' + r.stderr.strip())
    d, n_, cand = refresh_lines(r.stdout)
    done += d; need += n_

    text = open(o.new, encoding='utf-8').read()
    boxes = sorted({int(x) for x in re.findall(r'<g id="n(\d+)"', text)})
    adds = [n for n in adds if n not in boxes]
    added = []
    if adds:
        import refresh_meta, svgmeta
        live, _ = refresh_meta.fetch_records(*repo.split('/'), adds)
        texts = refresh_meta.fetch_texts(*repo.split('/'), [n for n in adds if not live.get(n, {}).get('missing')])
        kinds = {b: r['github'].get('kind') for b, r in svgmeta.boxes(text).items() if r.get('github')}
        spec, n_, notes = spec_for(repo, live, adds, boxes, answers, texts, kinds)
        need += n_
        if spec['boxes'] or spec['arrows']:
            fd, sp = tempfile.mkstemp(suffix='.json')
            with os.fdopen(fd, 'w') as f:
                json.dump(spec, f)
            r = run(log, 'add_nodes.py', o.new, o.new, sp)
            if r.returncode:
                sys.exit('add_nodes.py failed: ' + r.stderr.strip())
            need += [ln[len('PROBLEM'):].strip(' :') for ln in r.stdout.splitlines() if ln.startswith('PROBLEM')]
            added = [b['num'] for b in spec['boxes']]
            done += ['added #%d (%s), frame by %s' % (b['num'], b['state'], 'answer' if 'frame' in b else 'rule') for b in spec['boxes']]
            done += ['arrow #%d %s #%d%s' % (a['from'], a['kind'], a['to'],
                                              ' (%s)' % notes[(a['from'], a['to'], a['kind'])] if (a['from'], a['to'], a['kind']) in notes else '')
                     for a in spec['arrows']]
            r = run(log, 'refresh_meta.py', repo, o.new, '--apply')          # records of the new boxes; what their texts state
            d, n_, _ = refresh_lines(r.stdout)
            done += [x for x in d if x not in done]; need += [x for x in n_ if x not in need]

    r = run(log, 'check_diag.py', o.new, o.old, *keep)
    fails = [ln for ln in r.stdout.splitlines() if ln.startswith('FAIL ')]

    png = None
    if o.render and added:
        text = open(o.new, encoding='utf-8').read()
        rs = [box_rect(text, n) for n in added]
        rs = [x for x in rs if x]
        if rs:
            x0 = min(x for x, y, w, h in rs) - 350; y0 = min(y for x, y, w, h in rs) - 250
            x1 = max(x + w for x, y, w, h in rs) + 350; y1 = max(y + h for x, y, w, h in rs) + 250
            png = os.path.join(tempfile.gettempdir(), os.path.basename(o.new) + '.added.png')
            run(log, 'render_region.py', o.new, png, *['%d' % v for v in (x0, y0, x1 - x0, y1 - y0)])

    need = [x for x in dict.fromkeys(need) if not any(a in x for a in ack)]
    print('== %s -> %s  (%.0fs; full log %s)' % (os.path.basename(o.old), os.path.basename(o.new), time.time() - t0, logp))
    for x in done:
        print('  done: ' + x)
    if cand:
        print('NEW ON GITHUB, not boxes (add with --add N, or leave out):')
        for x in cand:
            print('  ' + x)
    if need:
        print('DECISIONS:')
        for i, x in enumerate(need, 1):
            print('  %d. %s' % (i, x))
    print('FAILS: %d' % len(fails))
    for x in fails:
        print('  ' + x)
    if png:
        print('render: ' + png)
    sys.exit(3 if need or fails else 0)


if __name__ == '__main__':
    main()
