#!/usr/bin/env python3
"""Rebuild a diagram from its saved inputs with one command, so any revision can be made again later, by anyone.

usage: make_diagram.py DIR/diagram.json [--hover] [--out OTHER.svg]

A diagram keeps its inputs in a folder next to its SVG (see SKILL.md, "Diagram folder"). diagram.json names them; paths are relative to
the folder:
{ "repo": "owner/name", "title": "text; #N becomes a link", "date": "YYYY-MM-DD (the day the snapshot was read)",
  "roots": [100], "out": "../name_v3.svg",
  "snapshot": "snapshot.json",                       (refresh_meta.py)
  "frames": "frames.json", "edges": "edges.json", "notes": "notes.json", "collapsed": "collapsed.json",   (each optional)
  "options": {"collapse_done": true, "low_as_notes": true},                                            (graph_from_snapshot.py flags)
  "decisions": ["YYYY-MM-DD: what the user decided, e.g. an arrow dropped, and why"] }

Steps: graph_from_snapshot.py writes DIR/graph.json; the manifest and the skill version go into it as "provenance", and build.py writes
them into the SVG's <metadata>, so the picture says how it was made; build.py draws; check_diag.py and metrics.py report. --hover also
runs test_hover.mjs on every collapsed box (it starts a headless browser). --out writes the SVG elsewhere (a trial rebuild). Exit status 1 when check_diag.py reports a FAIL.
"""
import hashlib, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = {'collapse_done': '--collapse-done', 'low_as_notes': '--low-as-notes'}


def skill_version():
    """The git commit of the skill (with +dirty when files differ from it) and a hash of the scripts' contents: the hash alone pins
    the exact code, the commit tells a reader where to find it."""
    h = hashlib.sha256()
    for name in sorted(os.listdir(HERE)):
        if name.endswith(('.py', '.js', '.mjs')):
            h.update(name.encode() + b'\0' + open(os.path.join(HERE, name), 'rb').read())
    v = {'scripts_sha256': h.hexdigest()[:16]}
    try:
        v['commit'] = subprocess.run(['git', '-C', HERE, 'describe', '--always', '--dirty=+dirty', '--abbrev=12'],
                                     capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    return v


def run(cmd, **kw):
    print('$ ' + next((os.path.basename(c) for c in cmd if c.endswith(('.py', '.mjs'))), cmd[0]), flush=True)
    return subprocess.run(cmd, text=True, **kw)


def main():
    sys.stdout.reconfigure(line_buffering=True)    # our lines and the scripts' output in the order they happen
    argv = sys.argv[1:]
    other = None
    if '--out' in argv:
        i = argv.index('--out')
        other = os.path.abspath(argv[i + 1])
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith('--')]
    if len(args) != 1:
        sys.exit(__doc__)
    mpath = os.path.abspath(args[0])
    d = os.path.dirname(mpath)
    m = json.load(open(mpath, encoding='utf-8'))
    for k in ('repo', 'title', 'date', 'snapshot', 'out'):
        if not m.get(k):
            sys.exit('%s: "%s" is missing' % (args[0], k))
    at = lambda p: os.path.join(d, p)
    graph, out = at('graph.json'), other or os.path.normpath(at(m['out']))
    py = [sys.executable, '-B']
    cmd = py + [os.path.join(HERE, 'graph_from_snapshot.py'), at(m['snapshot']), graph,
                '--repo', m['repo'], '--title', m['title'], '--date', m['date']]
    if m.get('roots'):
        cmd += ['--roots', ','.join(str(r) for r in m['roots'])]
    for k in ('frames', 'edges', 'notes', 'collapsed'):
        if m.get(k):
            cmd += ['--' + k, at(m[k])]
    for k, on in (m.get('options') or {}).items():
        if k not in FLAGS:
            sys.exit('unknown option "%s": use %s' % (k, ', '.join(FLAGS)))
        if on:
            cmd.append(FLAGS[k])
    if run(cmd).returncode:
        sys.exit('graph_from_snapshot.py failed')

    g = json.load(open(graph, encoding='utf-8'))
    g['provenance'] = {'manifest': os.path.basename(mpath), 'inputs': {k: m[k] for k in ('snapshot', 'frames', 'edges', 'notes', 'collapsed') if m.get(k)},
                       'options': m.get('options') or {}, 'decisions': m.get('decisions') or [], 'skill': skill_version()}
    json.dump(g, open(graph, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    if run(py + [os.path.join(HERE, 'build.py'), graph, out]).returncode:
        sys.exit('build.py failed')
    chk = run(py + [os.path.join(HERE, 'check_diag.py'), out], capture_output=True)
    print(chk.stdout.rstrip())
    run(py + [os.path.join(HERE, 'metrics.py'), out])
    if '--hover' in sys.argv:
        nums = [str(n['num']) for n in g['nodes'] if n.get('collapsed')]
        if nums:
            run(['node', os.path.join(HERE, 'test_hover.mjs'), out] + nums)
    fails = [ln for ln in chk.stdout.splitlines() if ln.startswith('FAILS ') and ln.split()[1] != '0']
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
