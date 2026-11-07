#!/usr/bin/env python3
"""Start a new revision of a lineage diagram: copy the file and drop every `new` pill. Nothing else changes.

usage: new_revision.py old.svg new.svg [--keep-new]

- The old file is never touched (a frozen revision stays frozen). The new file must not exist yet.
- `new` pills mark the boxes added since the previous revision. A new revision drops the old ones; add_nodes.py draws a pill on each box
  it adds ("new": true in its spec).
- `--keep-new` keeps the pills the old file has (the user said "build v19.1 and keep the new pills"): the boxes that were new in the old
  revision stay marked, and the boxes added now get theirs too.
- Afterwards: `refresh_meta.py ... --apply` for the state changes, then `check_diag.py new.svg old.svg`.
"""
import os, re, sys


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        sys.exit(__doc__)
    old, new = args
    if os.path.exists(new):
        sys.exit('%s exists: a revision is never overwritten here' % new)
    s = open(old, encoding='utf-8').read()
    # a `new` pill: <g transform="rotate(-45 cx cy)"> rect + text "new" </g>, inside a box group
    pat = re.compile(r'\n?<g transform="rotate\(-45 [\d.]+ [\d.]+\)">\s*<rect [^>]*fill="#ff2a2a"[^>]*/>\s*<text class="pill"[^>]*>new</text>\s*</g>')
    if '--keep-new' in sys.argv:
        out, n = s, 0
        print('%s -> %s: the %d new pills of the old file are kept' % (old, new, len(pat.findall(s))))
    else:
        out, n = pat.subn('', s)
        print('%s -> %s: %d new pills dropped' % (old, new, n))
    open(new, 'w', encoding='utf-8').write(out)
    print('next: refresh_meta.py ... --apply, then check_diag.py %s %s' % (new, old))


if __name__ == '__main__':
    main()
