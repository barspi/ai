# Notes for `<diagram>_vNN.svg`

Diagram-specific instructions. The generic rules are in the skill `bbb-github-diag` (`<path to the skill>/SKILL.md`). Read this file at the start of every revision and update it in the same revision. Keep it short.

## What it is

One or two lines: the repository (`OWNER/REPO`), the root issue(s), the topic. Name the current revision file and how revisions are named (default `vNN`; the file is overwritten until the user asks for a new revision).

## Scope

- Roots: `#A`, `#B` (why each; if you picked a root yourself, say why, with the link).
- Filters the user gave (state, closed within N days, area or label, depth) — quote them.
- Relations followed: sub-issues, closing references, `blockedBy`/`blocking`, text relations.
- Exceptions to the date window: each item kept although it is older, and why (a direct child of `#N`, already in the chart, …).
- Questions asked of the user, and the answers.

## Layout (this diagram only)

Column x positions, frame order, lanes, anything that must stay. Note a size hack here (for example "name of `#N` set at 9px", "name of `#M` on a second line").

## Arrows

One line per non-obvious arrow: the pair, the label, and the evidence (a GitHub relation, or a sentence in a comment with its link). Note arrows left out as too hard.

## Not drawn

One line per item looked at and left out, with the reason. Every item here is also in `_meta.ignored` of the snapshot, so `--discover` does not report it again.

## Build

The exact commands, in order (build script, `refresh_meta.py ... --tsv-dir`, `check_diag.py`), and the expected checker result (0 failures; list any known warnings).

## Revision marks

Which boxes carry a `new` pill and why (first revision: none). When the user asks for a new revision: freeze this file, copy it to the new name, reset the pills.
