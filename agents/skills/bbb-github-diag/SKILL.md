---
name: bbb-github-diag
disable-model-invocation: true
description: >-
  Draws a directed graph of GitHub issues and pull requests as a
  hand-authored SVG: parent to child, what closed what, what replaced what,
  what blocks what, what is still open. Use ONLY when the user explicitly
  asks (for example /bbb-github-diag, names this skill, or asks for an
  issue/PR lineage diagram). Do not run it because a conversation mentions
  issue numbers.
compatibility: >-
  macOS, Linux or Windows (tested only on macOS; on Windows, native Python
  works and WSL is optional). Needs gh 2.x logged in with network access to
  api.github.com, python3 (tested 3.14) with Pillow, a sans and a mono font
  (found by fonts.py), and rsvg-convert to look at a render. node and a
  headless Chromium are optional. See Requirements in the body.
---

# GitHub issue and pull-request lineage diagram

Apply only on an explicit request. The picture shows how issues and pull requests relate: what spawned, closed or replaced what. Read the facts from `gh`, not from memory.

`example/sample-lineage.svg` is a finished example with invented numbers, titles and people. It uses every box state, the pills, the `new` mark, the bold claim lines, a dotted frame, the legend and the find box. Open it to see the look; `example/make_sample.py` has the code for a box, an arrow and a legend. After you change a style rule here, regenerate it with `python3 example/make_sample.py` and run `check_diag.py` on it (0 failures).

## Requirements

Check these before the first revision (`gh auth status`, `python3 fonts.py`, `rsvg-convert --version`). If one is missing, say which and stop; do not work around it.

| Need | Why | Tested with |
|---|---|---|
| `gh` 2.x, logged in (`gh auth status`), network to `api.github.com` | `refresh_meta.py` (one GraphQL call, REST `issues?since=`), reading items | 2.100.0 |
| `python3` | every script; `refresh_meta.py` uses the standard library only | 3.14.7 (the scripts use f-strings and `argparse`, no newer feature is known to be needed) |
| Python package `Pillow` (`pip install Pillow`) | `check_diag.py` and `example/make_sample.py` measure text with `ImageFont` | 12.3.0 |
| a sans font and a mono font, found by `fonts.py` | the same text measurement. Order: sans Helvetica, Arial, Liberation Sans, Arimo, Nimbus Sans, DejaVu Sans, then `fc-match sans`; mono Menlo, Consolas, Liberation Mono, Cousine, DejaVu Sans Mono, Courier New, then `fc-match monospace`. Folders searched: macOS `/System/Library/Fonts`, `/Library/Fonts`, `~/Library/Fonts`; Linux `/usr/share/fonts`, `/usr/local/share/fonts`, `~/.local/share/fonts`; Windows `%WINDIR%\Fonts`, and `/mnt/c/Windows/Fonts` under WSL. `python3 fonts.py` prints what it chose | Helvetica and Menlo on macOS 26 |
| `rsvg-convert` (librsvg) | rasterize a crop to look at. macOS `brew install librsvg`; Debian, Ubuntu or WSL `sudo apt install librsvg2-bin`; Windows without WSL: MSYS2 `pacman -S mingw-w64-x86_64-librsvg` | 2.61.0 |
| `node` (optional) | `node --check find-box.js` after editing the script | 26.5.1 |
| headless Chromium (optional) | test the find box layout and zoom (see "Interactive find box") | not required |

`gh` needs the sandbox off when a sandbox blocks TLS to `api.github.com`. Pass no tokens on the command line. Writing files outside the working directory (for example under `~`) may also need the sandbox off: shell heredocs and scripts can be blocked there while an editor tool still works.

Platforms. Only macOS was tested; the Linux and Windows paths follow from the standard font folders and are untested. The scripts are plain Python and run natively on Windows. WSL is optional there: it helps only with the shell snippets in this file (`grep`, `sed`, `cp`) and with installing `rsvg-convert`. Helvetica, Arial, Liberation Sans, Arimo and Nimbus Sans have the same character widths, so measurements match. DejaVu is about 10% wider, so text is measured longer than a browser draws it: a passing check still passes, but a line that fits may be flagged. `fonts.py` says when it fell back to a wider font.

## Page and palette

- Page `#f3f0e8`, ink `#1c2430`, secondary ink `#3b4350`, label background `#fffdf7`, legend background `#fbfaf6` with a `#b9b3a8` border, dotted frames `#8d877e`.
- Box colors, one set per state, are in the table under "What a node is". Arrow colors are in the vocabulary table.
- The SVG has a `<title>` and a `<desc>`. Write dashes and arrows as numeric entities (`&#8212;`, `&#8594;`), not as raw characters. Paths are orthogonal (horizontal and vertical segments only). Fonts: Helvetica for text, Menlo for the merge line.
- Header, top left, three lines under the title: `**Repository: OWNER/REPO**` in bold, alone on its line (several repositories: list them, comma separated); one line saying how to read the arrows; one line with the date the facts were read. Write no remarks such as "(invented)" or "(example)" in the picture.
- Look at a raster before you call it done (see "Looking at the picture").

## Scope

A diagram never covers the whole repository. Fix the span before you draw, write it in the NOTES file (section "Scope"), and ask the user, with the GitHub link, when something is unclear.

- **Roots.** The issues the user names. If the user allows it ("you may find better roots"), look for items with more related or child issues, and say which you picked and why, with links.
- **Relations to follow** from a box, in order of trust: GitHub sub-issues (`parent`, `subIssues`), closing references (`closingIssuesReferences`, `closedByPullRequestsReferences`), `blockedBy` and `blocking`, then relations the text states (`Related:`, `Blocks`, `Follow-up`, a "Children" list). A passing mention is listed but not followed; a pull request that cross-references an item is a candidate, an issue that does is only listed.
- **Filters** come from the user's prompt: state (for example open items, and closed ones closed within N days), area or label, date. Do not invent a filter; if none was given, ask.
- **The date window applies only to an item that is not in the chart yet and is not a direct child of a box already there.** An item already in the chart stays, whatever its age. A direct child (a GitHub sub-issue, a closing reference, an item the text presents as the box's child) may stay even outside the window; if unsure whether to keep it, ask. Write each such exception in NOTES.
- **Ask once, not per item.** When many older direct children qualify (when the whole chart is older than the window, they all do), list them in NOTES as a table (number, closing date, why kept) and put one question to the user: keep all, keep only the children of open items, or drop what is older than a date.
- **An issue reached only by a cross reference or a mention is not drawn.** List it under "Not drawn" with its link.
- **Relevance and age decide what is followed, not a hop count.** Follow without a depth limit, even outside the window: sub-issues all the way down, closing references (`closed by`), and the `follow-up` relation (the strongest after a child). `led to` is a little weaker and still important. A `blocked by` is followed while the blocker is open or inside the window. `related`, `depends on` and `references` are followed only for items that are open or inside the date window (about 30 days: a guide, not a hard rule). A mention is listed, not followed. `crawl.py` follows the structure GitHub stores (sub-issues, closing references, blockers); `follow-up` and `led to` live in the text, so read the kept items' text for them and add those items yourself.
- **Size.** Stop at the cap the user gave (default about 40 boxes) and ask what to cut: keep the roots, the open items, the closer relations and the most recent ones. There is no hop limit; `crawl.py --depth N` is only an optional safety cap.
- **Not drawn.** Every item you looked at and left out goes in the NOTES "Not drawn" list with the reason, and in `_meta.ignored`, so `--discover` does not report it again.
- **`crawl.py` does the walk** in one GraphQL call per level: `python3 crawl.py OWNER/REPO --seed N[,N] [--window-days 30] [--max-nodes 40] [--known N,N] [--no-up] [--out graph.json]` (`--no-up` stops it following parents, so an umbrella's siblings do not flood the chart). It prints each candidate with how it was reached, its state and closing date, and flags `ASK` where an item outside the window was kept as a direct child. A pull request that only cross-references an item is a candidate too: it counts as a direct child only if it really closes that item (this finds pull requests closed unmerged, which `closedByPullRequestsReferences` omits). Mentions in a body are printed apart and never followed; `--text` prints the lines of each kept body that name another kept item, which is how to find `follow-up`, `led to` and `supersedes` in prose. The judgement stays with you: it cannot see that a comment calls two items the same cause, so read the titles and the dropped list.

## What a node is

One box is one issue or one pull request.

Each box shows:

- `ISSUE`, `UMBRELLA`, or `PR` , and the number, as a link (see Links)
- the title
- opened date, and closed or merged date when it has one
- the merge commit, short, on a pull request
- on a merged pull request, in parentheses right after the merge commit, the usernames of its commit authors in first-commit order: `merge 3229bfa45 (alice, bob)`. With more than two, write the first and `et al.`: `(alice et al.)`. Read them with `gh api repos/OWNER/REPO/pulls/N/commits` (`.author.login`). The account that opened the pull request is a different fact; do not substitute it. A commit with no GitHub login (a null user) is named by its git author name; that is the main author. When the account that opened the pull request is different, name it after the main author: `(Yuna Seol, yunaseoul)`. With several commit authors, the main one is the author of most commits (ties: the first commit). This pair is long: put it on its own mono line so it does not run into the red cross. If the parentheses do not fit on the 11px mono line, put the authors on a second mono line. A pull request that is not merged has no merge commit, so it shows no merge line and no authors; the `by <opener>` label after `PR #N` still says who opened it.
- on an issue or umbrella that has an assignee, right after the label and number (`ISSUE #120`): a tiny arrow and the assignee's username, `ISSUE #120 → alice`. Read it with `gh api repos/OWNER/REPO/issues/N` (`.assignees[].login`). With several assignees, write the first username and `+N`. Draw the arrow as a short polyline, about 10px long with a 2.6px head, 4.6px above the label baseline. Set the username at 11.5px, semi-bold, in the same color as the label (the box stroke color), about 6px after the label's end plus the arrow. The name must end before the status pill, and before the red cross on a closed pull request (the cross's left edge is 19px left of the pill; keep 6px clear). If it does not fit at 11.5px, set it at 9px. If it still does not fit, move the name together with its `by` or its tiny arrow to a second line under the `ISSUE #N` or `PR #N` label (baseline 13px below the label's, same x, 11.5px). Never truncate a name; never overlap the pill or the cross. An unassigned issue shows the arrow and a `?`: `ISSUE #121 → ?`. A pull request shows `by` and the username of the account that opened it (`gh api repos/OWNER/REPO/pulls/N`, `.user.login`), with no arrow, in the same style: `PR #122 by alice`. This is the submitter, which can differ from the commit authors.
- a design document or memo when one is the source of that item

A status pill sits in the upper right. The word is `open`, `closed`, `merged`, `waiting`, or `draft`.

| State | Box | Pill fill | Pill text |
|---|---|---|---|
| Open issue or open umbrella | `#f8e8e4` / stroke `#8a3030` | `#9f2d2d` | the box fill `#f8e8e4` |
| Closed issue or closed umbrella | gray `#eceae6` / stroke `#6e6a64` | `#4e4b48` | the box fill `#eceae6` |
| Merged pull request | `#e7f0fb` / stroke `#1d4e89` | `#163e73` | the box fill `#e7f0fb` |
| Pull request ready, waiting for review | soft yellow `#ffeb85` / stroke `#8f6400` | `#9a6700` | the box fill `#ffeb85` |
| Draft pull request (open, `isDraft`) | paler yellow `#fff6c9` / stroke `#8f6400`, **dashed** (`stroke-dasharray="6 4"`) | `#9a6700`, word `draft` | the box fill `#fff6c9` |
| Pull request closed without merging | gray, as a closed issue (`#eceae6` / `#6e6a64`), label `PR`, plus wide soft red stripes under the text (see below) | `#4e4b48`, word `closed`, with a red cross just left of it | the box fill `#eceae6` |

A draft pull request (GitHub `isDraft`, open) is drawn like a waiting one with three differences: pill word `draft` (55.0px wide), paler fill (`#fff6c9`), dashed border. All else is the same: the `PR #N by user` label, the amber pill and text, the `closed by` arrow from the issue it will close, and the note `Fix in PR #N (open).` on that issue. When the author marks it ready it becomes `waiting`: solid border, `#ffeb85`. A draft closed without merging is a closed pull request: no dash, stripes and cross. A draft is never `merged`. `refresh_meta.py` reads `isDraft` and reports the state `draft`, so a pill that still says `waiting` (or `draft` after it was marked ready) is listed as a mismatch.

A pull request closed without merging (superseded by another one) keeps its box. Its note says `Not merged: superseded by PR #N.` The arrow from the issue it meant to close becomes `work done by` (the issue was closed by the other pull request). Its follow-ups get `follow-up` arrows from it.

Marks for a closed, unmerged pull request (chosen from an experiment, option C): (1) stripes: a 22px pattern rotated 45°, a red `#b84a4a` band 9px wide at 10% opacity, drawn as a box-sized rect with the box's `rx` right after the box rect and under the text; if a later script rewrites `x`/`y` attributes, write the pattern's inner `rect` without them; (2) a red cross, two 12px lines in `#ff2a2a` (the `new` pill's red), width 2.8, round caps, centred 13px left of the `closed` pill; (3) when another pull request replaced it, a `supersedes` arrow from the replacing pull request to it. A closed issue that no merged pull request closed (closed by hand, or with only unmerged pull requests) gets the same red cross by its pill (no stripes), and its note says how it was closed (`Closed as not planned.`, `PR #N was not merged.`). Check that the cross does not touch the `ISSUE #n → user` text. To look at one region, cut a copy of the SVG with a smaller `viewBox` (and no `<script>`) and rasterize it with `rsvg-convert`; the preview pane shows local SVG files only as static snapshots.

Open issues and open umbrellas are the same color. Closed is gray, not green.

**What an `UMBRELLA` is.** An umbrella is an issue that groups other issues: it has many child issues, and it is a tracker, not work to do directly. An issue is drawn with the label `UMBRELLA` (not `ISSUE`) when either of these holds:

1. It has child issues through GitHub's native **sub-issue** relation (`subIssues`, `subIssuesSummary.total` above 0 in the GraphQL query). This is the strong signal.
2. Its title says "umbrella" (for example `[Umbrella] …`). This covers umbrellas that have no sub-issues yet or that list their children in the body only.

Either is enough. A pull request is never an umbrella. A label such as `epic`, an issue form or an issue type is a project convention: it does not make an umbrella unless the user says so in the diagram's NOTES file. `refresh_meta.py` lists every box whose label disagrees with this rule.

**An umbrella by title only has no GitHub children, so infer them.** When an issue is an umbrella only by its title (rule 2, no sub-issues), do not leave it childless and do not guess from the title; read its text:

1. Run `refresh_meta.py ... --umbrellas`. One extra GraphQL call, for those umbrellas' bodies only (never all boxes); it prints, for each, the issues named in a task list, the other issues mentioned, and which are boxes. Run it when the umbrella is new or its `updatedAt` changed, not on every revision. Never paste the body into the conversation.
2. Decide from the sentences, not from the position of the number. A **child** is an issue the body presents as work or a part of this umbrella: a "Children", "Tasks", "Scope" or "Work items" list, "this umbrella covers", "split into". A task list can also hold things that are not children: a blocker, a prerequisite, background, an earlier decision, a sibling umbrella. Words such as "blocked by", "after", "depends on", "see", "context" mark those, and they get `blocked by`, `depends on` or `related` arrows, not `child`.
3. Draw a `child` arrow for each issue you judge a child, and write in the umbrella's box `Lists #A and #B as children (read from the body).` so the reader knows GitHub does not hold the relation.
4. If it is not clear whether an issue is a child, do not draw the arrow. Ask the user, with the GitHub link of the umbrella and of the issue, and write the answer in the diagram's NOTES file so the question is not asked again.
5. Thematic similarity alone (same area, similar title) is not enough to make a child.
6. When the umbrella later gets real sub-issues on GitHub, those replace the inferred list.

Set the pill text with a `style="fill:…"` attribute. A shared SVG text class will otherwise paint it black.

### The `new` pill

A `new` pill tells the reader what to look at first. It marks the boxes added since the previous **revision** (see "Revisions"), not since the previous edit. Mark only boxes added, never boxes whose state changed.

- An update inside the current revision keeps every `new` pill and adds one to each box it adds, however many: the revision is not over, so no pill is removed.
- When the user asks for a new revision, remove all the old `new` pills first, then put a pill on exactly the boxes that are not in the previous revision's file. Compare against that file (the frozen previous revision), not against your memory of what was added.

- Position: on the top-left corner of the box, centered on the corner (nudge it about 2px inside), rotated −45° so it reads up and to the right across the corner. It is a corner ribbon, not a label inside the box.
- Color: bright red `#ff2a2a`, white text, a thin stroke in the page color `#f3f0e8` so it separates from the box edge.
- Size: the text is 1.5 times the status-pill text: 15.75px bold, letter-spacing 0.9px, set with an inline `style` (the shared `pill` class is 10.5px). The word `new` has only x-height letters, so centre the glyphs, not the text box: the baseline sits 4.2px below the pill centre, the text x is 0.45px right of the centre (letter-spacing adds a trailing gap), and there is 6.4px of space round the glyphs on every side. The pill is 47.0px wide and 21.7px tall, with fully rounded ends. Center it 3px inside the box corner, and keep a 26px half-width square around that center free of arrows and labels. (The first size, 10.5px, looked smaller than the status pills once it was rotated.)
- The `waiting` yellow is kept soft, with a dark amber border, pill and `PR #…` text, so the text contrasts with the yellow background. The `draft` yellow is paler still and keeps the same dark amber for border, pill and text.
- Keep arrows and labels clear of it. Treat it as an obstacle when you route.

## Links

Every issue number and every pull-request number is a link to the GitHub page. Issue `#N` goes to `https://github.com/OWNER/REPO/issues/N`. Pull request `#M` goes to `https://github.com/OWNER/REPO/pull/M`. Use the repository that owns the item. In SVG, wrap the number text in `<a href="…">` and underline it (`<tspan style="text-decoration:underline">#N</tspan>` inside the link).

- Underline EVERY issue or pull-request number that is a link, not only the one in the box heading: the mentions in a title, a note (`Blocks #2125`), the legend, the page header and a frame title too. A clickable number with no underline looks like plain text.
- Put a `<title>` child inside each `<a>` with the item's title (browsers show it as a tooltip on hover): the box's title for a box, otherwise the title read with `gh`; leave it out if unknown. Escape the text.

If the user asks for a PDF, those same numbers are links there too. A PNG cannot hold a link. Do not promise links on a raster.

## What an arrow is

The picture is a directed graph, not a tree and not an acyclic graph. Most arrows point forward in time, from the earlier item to the later one (`child`, `follow-up`, `led to`, `spawned`, `revised by`, `closed by`, `work done by`). A few point back or sideways by design: `blocked by` runs from the blocked item to the blocker, `supersedes` from the newer pull request to the older one, and `related`, `depends on`, `references` and `mentioned` have no direction in time. So a cycle can appear (an item that blocks another item it also led to). That is fine: do not drop a true relation to avoid a loop, and do not call the picture acyclic in the title, description or legend.

- A source is an item no forward arrow (`child`, `follow-up`, `led to`, `spawned`, `revised by`, `closed by`, `work done by`) points into. The root issue (or umbrella) the diagram starts from is that kind of node. When the user starts from several initial issues, each is a source.
- Read every arrow as a sentence from tail to head: A, label, B. `#10 closed by #12`. When the later item acts on the earlier one, the label is passive (`closed by`, `revised by`, `work done by`). A noun label (`child`, `follow-up`) names what B is to A.
- Use only the labels in the vocabulary below. If none fits, add one to the table first, with its definition; never invent a label in the picture or use two labels for one meaning.
- When a pull request closed an issue, say the pull request number on the issue box as well.
- If two items both come from the same item, draw two arrows out of that item. Do not draw an arrow between the two siblings. Parallel is not a chain.
- A node may have no outgoing arrow. An open issue with no pull request is that kind of node. It still has its incoming arrow.
- A relation named in a box's text has an arrow, if both items are boxes. This holds for `Related: #N`, `Blocks #N`, `Blocked by #N` and a decision on one item that another item must wait for (issue A is blocked by the decision recorded on issue B). On every revision, compare the boxes named in each new or updated item's text with the arrows, with a small script: list each pair where one text names the other and no arrow joins them, then read only the "Related", "Blocks", "Closes", "Follow-up" and "Found" lines. A passing mention does not need an arrow (`mentioned`). If the route would cross the whole picture, say so to the user instead of dropping it silently.
- An open pull request that closes an issue gets the same blue `closed by` arrow as a merged one (state is in the pill, not in the arrow). Each issue it closes ends its note with `Fix in PR #N (open).`; when the pull request merges, that line becomes `Closed by PR #N.` A pull request's box repeats only its own facts (`Closes #A and #B.`, tests, evidence); it does not name other boxes unless an arrow joins them. Relations that appear only in the pull request's description, far from it in the picture, are left out unless the user asks.
- Two open pull requests that close the same issue each get a `closed by` arrow from that issue, and each says "PR #N also closes it."
- An umbrella may list a child that is older than the umbrella (umbrella `#40` lists `#25`, which `spawned` it). Do not draw a `child` arrow: it would run against the `spawned` arrow and make a loop of forward arrows, which reads as a mistake. Write the child in the umbrella's box (`Lists #25 and #31 as children.`) and use the bold `Blocks` / `Blocked by` lines.

### Arrow vocabulary

| Label | Line | `A → B` means |
|---|---|---|
| `child` | solid, ink | B is a formal child of umbrella A: B is a GitHub sub-issue of A (`parent`), or, where sub-issues are not used, A lists B or B names A as its parent. |
| `follow-up` | solid, brown | B was filed to finish something that A left out. |
| `led to` | solid, brown | Work on A produced B, including a defect that work on A exposed. (There is no separate `found` arrow. The box text says "Found ...".) |
| `spawned` | solid, brown | A caused B to be filed as a new umbrella or work stream. |
| `revised by` | solid, brown | B is a later pull request that changes what pull request A delivered. |
| `closed by` | solid, blue | B is the pull request that closed issue A. |
| `work done by` | dashed, blue | B did work for A but did not close it. A was closed by hand, or stays open. This includes a pull request that tried to close A and was closed unmerged, whether or not another pull request replaced it. |
| `evidence, does not close` | dashed, amber | B gives evidence for A. A stays open. |
| `supersedes` | solid, red `#b02a2a`; the head is a red cross `#ff2a2a` (about 16px, its centre exactly on the box border; the marker needs `overflow="visible"`, and the path is drawn after the boxes so the cross lies on top of the border and is whole) instead of an arrowhead | A is the pull request that replaced B. B was closed unmerged. The arrow runs from A to B. Put the label on a long vertical stretch, not on a short horizontal one: a red-cross head leaves little shaft. Draw it when GitHub or the text says, in any wording, that one replaced the other: "supersedes", but also "we prefer X, so Y is closed", or Y's approach is wrong, obsolete or stale and X takes over. Judge by meaning, not by keywords. Two pull requests for the same issue, with nothing like that said, are not enough: keep `work done by` and `closed by`, and ask. |
| `blocked by` | solid, dark red `#8a3030` | A cannot be finished until B is done: A's text, or B's, says B blocks A. The arrow runs from the blocked item to the blocker. |
| `depends on` | dashed, gray | A needs the result of B, but B does not block A's work. Use `blocked by` when the text says "blocked by" or "blocks". |
| `references` | dashed, gray | A's text points to B as relevant prior work. |
| `mentioned` | dashed, gray | A names B in passing. B is not part of this lineage. |
| `related` | dashed, gray | A and B are related work. Neither is the parent of the other. |

### Bold claims in the box text

A claim that is true now, and that a reader must not miss, is bold. Write it with `**...**` in the note text.

- `Found ...` (where the defect came from) and `Blocks #N.` / `Blocked by #N, #M.` are bold while the box is **open**.
- `Not merged: superseded by PR #N.` (or another reason for a closed, unmerged pull request) is bold: it is the one fact that tells a reader the box delivered nothing, and it stays bold because the box will never change state again. Read the reason from GitHub, not from guesswork: who closed it (`closed by the author`, `closed by a maintainer`, or `closed as maintainer-only` when it carries such a label; `crawl.py` prints it) and, for a closed issue, its state reason (`Closed as completed.`, `Closed as not planned.`); write `closed without merging` when it is unknown.
- `Decision needed: ...` (a question a human must answer before the work can go on) is bold on every line while the issue is **open**. When it closes, the line is not bold and reads `Decision was needed: ...` (or the decision itself, if known).
- When the box is closed or merged, the `Blocks` line goes away (it blocks nothing now; the `blocked by` arrow stays as history). `Found ...` stays, but not bold.
- An open umbrella is `Blocked by` its open children, and each open child says `Blocks #umbrella.` This holds only while the umbrella is open: if it was closed (or any blocked item was closed, merged or abandoned), write neither line, because closing it shows it was not blocked; the open child is then just an open child. Write this only when the item is a formal child of the umbrella, or the umbrella's text lists it. The reverse is not implied: if umbrella `#40` lists `#25` in its task list, `#25` blocks `#40`; a sibling umbrella that does not list `#25` gets no line.
- An item can block several umbrellas: `#31` says `Blocks #1 and #40.` One relation is written once on each box (`Blocks #U` on the child, `Blocked by #C` on the umbrella). It is not a mutual block.
- When an umbrella's body lists children, its box says so (`Lists #25 and #31 as children.`) and names the decisions that have no issue yet. Do not leave `No child issue yet.` after the body has changed. Re-read the umbrella body on every revision.
- Do not bold `Closes ...` or `Closed by ...`. They are frequent and the `closed by` arrow already shows them.
- When a box grows (note lines added), check its bottom edge is still inside its dotted frame; if not, grow the frame and move the frames below it.
- When you add a line to a box, grow only the two box rectangles (width 260 and 252). Never grow a rectangle by its `rx` alone: the status pill has `rx="10"` too, and it doubled in height once.

A dotted frame may name an area (a module, a component, a theme). The frame does not replace an arrow. Do not put the parentage only in a section title.

## Layout

Use the plane. Rows and columns are for alignment, not a substitute for edges.

- Leave a gap long enough that the opaque label does not cover the whole shaft: tail and arrowhead stay visible. A gap under about 150px is too small for a `closed by` label.
- Draw every path first, then every label, so a later path cannot hide an earlier label. Labels sit on top of the stroke.
- Put the label on a long segment of its arrow, not on a stub or on a bus shared by many arrows (a shared bus stacks the words).
- When one item has several children, fan the arrows. A vertical column of children with the parent on one side and the closing pull request on the other is the pattern: arrows leave the parent and enter each child; `closed by` arrows leave those children and converge on the pull request. Give each arrow its own vertical position so labels do not overlap and every arrowhead shows.
- **Fork from a root (required).** Put the root level with the middle of its children, so its arrows spread up, straight ahead and down, not all downwards. Give the root's right edge one exit per child, 14 to 16px apart, and make the root box taller if it needs the room. The arrows share one vertical bus between the root and its children, nested so none crosses; never send all the arrows downwards, and do not leave from the bottom edge in a staircase. Lane order, so nothing crosses: for arrows going up, the topmost exit takes the lane nearest the root; for arrows going down, the lowest exit takes the nearest lane (the exit farthest from the middle is the nearest lane). Size the gap between the root and its children at 14px per lane plus about 60px at each end (never under 205px). The root box must be tall enough that every exit leaves from its right edge: an exit below the box is a defect, and the checker flags a tail that does not touch a box. Keep each exit-to-child jog at 30px or more, or make it straight: when neighbouring exits are packed and cannot move, move the arrow's entry point along the child's left edge (anywhere at least 20px from the corners) instead. The lane count for the gap formula is the larger of the up group and the down group.
- **Several roots.** Each root has its own cluster (its children and its frames); do not run a root's arrows across another cluster, and repeat a shared theme as a frame in each cluster. There are two layouts, and the user may choose: (a) every cluster starts in the first column, stacked, so the x axis is one timeline from root to outcome; (b) the second cluster sits to the right of the first, which keeps the canvas near square. Default (hybrid): stack (a) while the canvas stays shorter than about 1.3 times its width, and start the next cluster to the right when it would not; side by side also when the user asks. If the finished canvas is at least twice as tall as wide (or twice as wide as tall), stop and ask the user before going on; `check_diag.py` prints a note then. The legend does not move: it stays in the top row, with its right edge at the right edge of the rightmost box or frame of the whole drawing (the farthest right node edge fixes it; or further right, in a column of its own). Never leave it left of that edge. A cluster placed to the right of the first starts below the legend, not beside it.
- Do not route an arrow through a box. If a box sits between two ends, go around it in a gutter.
- A closed side branch (an item and its pull request, often in their own frame) is a candidate for removal. The more of these signals hold, the stronger the candidate:
  - It is a side topic, not part of the lineage.
  - Everything in it is closed or merged.
  - All the work was done by someone else (the authors and assignees are not the person who asked for the diagram).
  - Nothing open waits on it.
  - Only a weak arrow reaches it (`depends on`, `related`, `references`, `mentioned`).
  - It closed before the lineage's own work started.
  - It sits alone in its own frame.

  When you remove one, keep one line in the box that used it (`Used #30 (closed by PR #31).`). A branch with only one or two signals stays. If you are unsure, ask with the GitHub link.
- The "How to read this graph" legend is compact and always sits in the top row, with its right edge at the farthest right edge of the nodes (the top-right of the chart; see "Several roots" for a second cluster). When columns are added on the right, move the legend with them. It has no "Still open on <date>" summary. It explains the pills, the arrow words and the bold lines.
- Frames stacked in one column share a left edge, with about 34px between them. A frame must never overlap a frame of another column: compare all frame extents after every change. When a frame grows or is inserted, the frames below it move down by the same amount with their boxes, arrows and labels. Order stacked frames so the arrows from the source nest without crossing (see the lane rule below).
- Trunk arrows that run down a gutter beside a column of frames each get their own lane, about 14px apart, in the same order as their start points on the source (so they do not cross), and enter their box from the left. Put their labels on the last straight stretch.
- The canvas ends about 80px below the lowest box or frame. Compute it from the final geometry, not from numbers the build used before frames moved.
- Anything that is specific to one diagram (the order of its frames, its column widths, a frame that must stay, a lane assignment, where its build scripts live) goes in a companion file next to the SVG, `<diagram>_NOTES.md`, or in an XML comment at the top of the SVG. Start the NOTES file from `example/NOTES_template.md`. Read it at the start of every revision and update it in the same revision. This skill holds only rules that hold for any repository.
- **Every revision starts with `refresh_meta.py` (in this skill's directory), and re-checks every box, not only the ones the user mentioned.** `python3 refresh_meta.py OWNER/REPO diagram.svg diagram_snapshot.json --tsv-dir <build dir>` makes ONE GraphQL call for all boxes (box numbers come from the `<g id="nN">` groups). GitHub's `updatedAt` changes on any edit, comment, label, assignee or state change, so the script compares it with the stored snapshot and prints only the boxes that changed, with the differing fields (state, title, assignees, comment and review counts, merge commit and its commit authors, opener). It also prints every box whose pill disagrees with the live state, and it writes `assignees.tsv` and `prauthors.tsv` for the build, so nobody types them by hand. Read the full text of a box only when it is listed as changed. Keep the snapshot next to the SVG (`<diagram>_snapshot.json`) and do not delete it. Run it outside a sandbox that blocks TLS. Fix every difference in the same revision, and say in the answer how many boxes were checked and which changed. The cost of a no-change revision is this one call.
- **Use GitHub's own relations, not only the text.** GitHub stores real relations between issues and pull requests. Ask for them in the same single GraphQL query as the metadata (`refresh_meta.py` does, and `--relations` lists every one that joins two boxes):
  - Parent and child: `Issue.parent{number}`, `Issue.subIssues(first:50){nodes{number}}` and `subIssuesSummary{total completed}`. A sub-issue is a **real** `child` of its parent. Draw a `child` arrow for it, and treat the old rule (the body lists it, or it names the parent) as the fallback for repositories that do not use sub-issues. Compare `subIssuesSummary.total` with the children you drew: a difference is a child that is not a box.
  - Closing: `PullRequest.closingIssuesReferences{nodes{number}}` (what a pull request closes) and `Issue.closedByPullRequestsReferences{nodes{number}}`. These are the `closed by` arrows, and they are more reliable than a `Closes #N` line in a body, which can be wrong or edited. A pull request can close several issues, and an issue can be closed by several pull requests.
  - Blocking: `Issue.blockedBy(first:20){nodes{number}}` and `Issue.blocking(first:20){nodes{number}}` (GitHub's issue dependencies) give the `blocked by` arrows. When they are empty, the box text is the only source.
  - Where a relation exists on GitHub but not in the diagram, draw it. Where the diagram shows a relation GitHub does not have (a `Related:` line, a decision), keep it: the text is evidence, not an error.
- **Minimize GitHub API calls.** One aliased GraphQL query for all boxes (about 3 s for 91 boxes, about 4 points of the hourly budget; add `rateLimit{cost remaining}` for the real cost). Detect change with `updatedAt` against the snapshot and read a box's text only when it changed. The relations above ride in that same query, so they cost no extra call. When a box changed and you need its new comments, ask for `comments(last:N)` with `N` from the comment count difference, never for all of them. Do not call `gh issue view` or `gh pr view` per box, do not fetch bodies you do not need, and never print a body into the conversation. Everything the diagram shows (title, state, assignees, opener, merge commit, authors, relations) is in the one query. Not measured: whether a relation change alone moves `updatedAt`; `refresh_meta.py` therefore stores the relations in the snapshot and prints any difference.
- **Speed and token tips (measured on 87 boxes: 48 s with one `gh api` call per box, 3 s with one GraphQL call):**
  - One query with aliases, `i123: issueOrPullRequest(number:123){...}`, asking only for the fields the diagram shows (title, state, `updatedAt`, assignees, opener, comment count, merge commit). 87 boxes cost 3 of 5000 rate-limit points. Above about 200 boxes, split into several queries.
  - Never reread the text of a box whose `updatedAt` did not change.
  - Find new items with `gh api 'repos/OWNER/REPO/issues?state=all&since=T&per_page=100' --paginate --jq '<only the fields needed>'`, filter in the script, and print only the items that link to a box. Never print issue bodies into the conversation.
  - Do the sync in one command and the build, check and snapshot refresh in a second one. A revision should need about five tool calls: refresh and discover, read only the changed or new items, edit and rebuild, render one crop, update notes.
  - `gh` sandbox and token rules: see Requirements.
  - Most of the elapsed time is the model's reasoning, not the scripts (measured: about 85% model, 12% tools). So decide placement from the stored geometry and the NOTES file instead of rereading the build script, and keep a new box in a free column or lane rather than shifting neighbours.
- **Finding new items:** add `--discover`. It lists the issues and pull requests created, closed or merged since the last run (stored in the snapshot's `_meta.lastRun`; `--since ISO8601` looks further back and does not move it) that are not boxes yet. It prints in full only the ones that name a box (`#N` in the title or body) or are named by a box's text. The rest is compressed: same-area items (the `area:` title prefix) as a list of numbers, and counts of unrelated, only-commented and ignored items. Items that were only commented on or edited are not candidates. Judge thematic relation from the title and the area list; open an item only when that is not enough. Every reported candidate must end the revision as a new box, or as a decision: ask the user about doubtful ones (with the GitHub link), then add the declined ones to `_meta.ignored` in the snapshot so they are not reported again.
- A candidate that only mentions a box in passing is not worth a box. Draw a new item only when it closes, blocks, follows up, supersedes or decides something about a box, or sits in the same thread of work. When in doubt, the diagram stays smaller: ask, and put every "no" in `_meta.ignored`.
- Without `--discover` the script finds changes only in boxes that already exist.
- A revision that adds boxes the user has not confirmed is written to a separate file (the user names the version, for example `<diagram>_vX.Y.test.svg`), and the kept file stays untouched. Updating existing boxes (state, assignee, text) still goes to the kept file. When the user says to keep the same version, overwrite that file.
- When a frame moves, only the arrows that cross its border change. Redraw those through the gaps between frames, use a jump arc where they cross another arrow, and move a label that the new route would cover. Then run the check script.
- Prefer a wider picture to a crossing. When a crossing cannot be avoided, see "Hard arrows" below.

### Compactness

Make the picture as compact as clarity allows, so it fits a screen or a page better. The order of priority is: clarity first, then no unintended overlap and no crossing, then compactness.

- Use both directions. Do not let the picture grow only down a long column or only across a long row.
- Keep gaps tight. Between stacked boxes, about 25–30px. Between dotted frames, about 35px of visible space. Frame padding, about 40px above (room for the frame title) and 20px below. A horizontal gap is as wide as its longest label plus about 50px of visible shaft, and no wider.
- Boxes sit in aligned columns with the same gap (about 200px) between neighbours. Only a gap that carries a fan of many nested lanes may be wider (about 14px per lane plus margins). When you narrow a gap, keep each lane's distance to its box edge and squeeze only the middle.
- A label longer than the gap minus about 100px goes on two lines (for example `evidence,` over `does not close`, in a label about 98px wide and 30px tall). Do not widen a gap for one long label.
- Look for large blank areas and consider moving a node, or a whole framed group, into one, only if the arrows stay easy to follow: no new crossing, no arrow that doubles back across the picture, no box that hides the flow from earlier to later.
- A column that holds a single box at the end of a chain can often fold under its neighbor, with a vertical arrow. Keep the vertical gap long enough for the label and a visible tail and head (about 80px for `closed by`: an 18px label, about 25px of straight shaft above and below it, and the arrowhead). Measure the shaft as the straight line only, from the tail to the base of the arrowhead (tip minus about 11px), and center the label on it so both visible shafts are equal, even when shorter than on a horizontal arrow. An error up to about 6px is fine; centering on the tail-to-tip span, off by half the arrowhead, is acceptable.
- Good groups to move have few incoming arrows and none leaving, such as a separate umbrella linked to the source only by dashed references; moving such a frame from the bottom of a long column into a blank area can cut the height by about 20%.
- When a moved group's incoming arrows must cross a column of boxes, give them a corridor: leave a horizontal gap between two frames (about 30px per arrow), run each arrow along its own line in it, then turn toward the target in the gutter before the target's frame. Treat the corridor height as the arrow's target height when ordering trunks, so it nests with the others and nothing crosses. Put the label on the last segment, which enters the box. One corridor is fine; each additional long one makes the source's fan harder to read, so weigh it against the height it saves.
- Keep an arrow at least about 30px from a frame's dotted border when it runs parallel to it. A dashed arrow next to a dotted border reads as one line.
- When a change makes the picture smaller, compare the before and after rasters. If following an arrow is harder after the change, undo it.

### Hard arrows

Some arrows have no clean path: the tail's side is full of other arrows, or a column of boxes sits between the ends. Do not let them shape the layout. Finish the main layout with every easy arrow first, then route the hard ones, fewest options first, with a script on a grid (5px is enough), not by eye.

Rules for a hard arrow:

- Never draw it under a box or under a label. Keep it about 26px from boxes and 10px from labels, and clear of any `new` pill.
- Never run it parallel to another line closer than about 36px. Two lines closer than that read as one.
- It may cross another line only at a right angle, and only on a long straight stretch: at least about 30px from either line's bends and from its arrowhead. Never turn on top of a line.
- Draw each crossing as a small jump: a semicircle of about 7px radius, over the line already there. A horizontal arrow hops up. A vertical arrow hops to the right. The older line stays straight.
- Minimize crossings first, then bends. Do not leave a jog shorter than about 30px; a flat lane at a slightly different height is better.
- Put the label on a long straight stretch, away from every jump and from other lines.
- Each hard arrow keeps its own entry point on the target's edge, about 40px from the others, and enters it straight for at least 25px before the arrowhead.
- If no path meets the rules, leave that arrow out of the picture, name it in the box note and in your report, and say what would have to move to make room. Do not draw it with a worse path.

## Files

### Revisions

A **revision** is a named, frozen version of the diagram. It is the unit the `new` pills are measured against. The default naming is a `vNN` suffix on the file name, starting at `<diagram>_v1.svg` (later `<diagram>_v11.svg`, `<diagram>_v12.svg`); if the user names versions another way (dates, tags, `rev-3`), use theirs and keep it consistent. Ask once if it is unclear, and write the choice in the companion NOTES file.

- **An update is not a revision.** A refresh, a state change, a new assignee, a new box, a new arrow, a text fix: all of these edit the current revision's file in place: same file name, `new` pills not reset (see "The `new` pill").
- **A new revision starts only when the user asks for one** ("make a new revision", "this is v13", "start v13"). Then copy the current file to the new name, leave the old file frozen (never edit it again), reset the pills as described above, and put the revision name in the title block or the NOTES file.
- A variant of the current revision (for example a more compact layout) takes a decimal, `_v7.1`, and is a separate file.
- When the user says to keep the same version, overwrite that file.
- A new box is not a reason to start a revision. If you are unsure whether the user wants a new revision, keep editing the current one and say so in the answer.

Small corrections edit the current SVG; write a new `_v2`, `_v3`, … file only when the user asks for a new revision or the layout is being replaced.

An extract is a separate SVG of one dotted frame with its boxes, arrows and labels, cut at the frame border with a clip. It keeps the `new` pills, and it may carry the "How to read this graph" block above it (without the "Still open" lists). Build it by selecting elements from the finished diagram, not by drawing it again.

Do not emit a PDF unless the user asks for one. When they do, keep the issue and pull-request numbers as links.

### Interactive find box

Embed `find-box.js` (in this skill's folder) in the SVG, in a `<script type="text/javascript"><![CDATA[ … ]]></script>` element as the last child of the root, in the full diagram and in extracts. The script builds everything itself, so a renderer that ignores scripts shows the unchanged static picture; it never changes the geometry. At load it moves the drawing into an inner `<svg>` inside a `foreignObject` that fills the window, in a scrollable HTML container, with the find box in the same overlay but outside the scrolling area. If the window gives the container no size (a thumbnail, for example), it puts the drawing back as it was. The find box keeps about the same size on screen when the browser zoom changes: the script scales the box by the inverse of the zoom from its bottom-left corner (`comp()`, called from `fit()` and from the 300 ms safety net). The zoom is absolute: `devicePixelRatio / nativeDpr`. Never use the zoom at load as the reference: a reload keeps the page zoom, so a page reloaded at 20% would treat 20% as 100% (this shipped once). `nativeDpr()` picks the ratio at 100% from 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 3, 4: the one whose implied zoom is closest (within 20%) to `outerWidth/innerWidth`, else the page is taken as 100% at load. A docked devtools panel spoils the ratio (a small error); Firefox gives about 1, so a reload there while zoomed is not corrected. `window.lineageZoom()` returns the numbers for debugging. Pinch zoom on a touch screen is not compensated. Build scripts must embed this file itself, not a private copy. Look (user choice): deep blue box (`#163e73`, 2px `#0e2b52` border), white input, `#1d4e89` buttons, light-blue note text, so it stands out from every status fill of the diagram.

- Size the root, the `foreignObject` and the container in explicit pixels from `window.innerWidth` and `window.innerHeight`, and redo it on `resize`, `orientationchange` and `visualViewport` resize, with a 300ms check as a safety net. Do not use `100%` for these sizes: some browsers do not re-resolve a percentage after the window or the zoom changes, and then part of the screen stays undrawn after a zoom-out. Set `overflow:hidden` on the root so it adds no scrollbars of its own.
- The find box is pinned at the bottom-left of the window, above the scrollbar. It stays there whatever is scrolled, horizontally or vertically, searched, focused or zoomed. Do not position it by following scroll events: that lags and drifts. Press `/` to focus it.
- A number (`120` or `#120`) jumps to that box, centered, and highlights it. If no box has that number, it matches numbers that start with what was typed.
- Any other text (`alice`, `bob merged`) matches every box whose text contains all the words, so it finds assignees, `by` submitters, commit authors and titles. Matches get an orange glow, the other boxes and the arrows fade, and the current match has a magenta border. Enter and Shift+Enter, or the arrow buttons, move between matches. Escape (pressed anywhere on the page, not only inside the box), a double-click anywhere on the diagram outside the find box, or the cross clears the box and all highlights.
- `file.svg#120` and `file.svg#find=alice` run the search on load, so a link can point at a box.
- It runs only when the SVG is opened directly in a browser, or embedded with `<object>` or `<iframe>`. It does not run in `<img>`, in GitHub's preview, in Quick Look or in a PDF. The built-in browser pane has no real viewport (its window reports 0×0), so test the matching logic there with `window.lineageFind('alice')`, which returns the numbers of the matches, and test the layout with a headless Chromium instead, for example `chrome-headless-shell --window-size=1300,800 --virtual-time-budget=6000 --screenshot=out.png "file:///path/diagram.svg#120"`. The hash search jumps instantly, so the screenshot shows the centered box, the faded rest, and the find box at the bottom-left. A browser started from the sandbox needs the sandbox off for that one command. To test a zoom, load the page in a headless Chromium with a remote-debugging port, then change the viewport after load (`Emulation.setDeviceMetricsOverride` through the DevTools protocol) and read back the sizes of the root, the `foreignObject` and the scrolling container: all three must equal the new window size each time.

## Check

Check from the SVG text and geometry, with a script, not by looking. A script costs seconds and no image tokens. Look at a rendered image only at the end (see "Looking at the picture").

The checks below are implemented in `check_diag.py` in this skill's folder: `python3 check_diag.py new.svg [previous.svg]` (it needs Pillow and the fonts found by `fonts.py`). It prints every failure and exits 1 on a failure. Keep working copies of build scripts in the scratch folder, but keep this checker in the skill folder; a scratch copy of it was lost once.

### SVG structure the checker reads

`check_diag.py` finds things by pattern, so keep this structure (`example/make_sample.py` writes it):

- Root `<svg width height viewBox>`; plain decimal numbers in every attribute (no exponents).
- A box is `<g id="nN">` whose first child is `<rect x y width height rx="10" …>` (width 260). Inside: `<text class="kind" x y style="fill:STROKE">` with `ISSUE`, `UMBRELLA` or `PR` and the link; `<text class="meta" x y style="…font-size:11.5px…">` for the name; the status pill as `<rect … height="20" rx="10">` plus `<text class="pill">`; then `<text class="ttl|meta|note|mono" x y>` lines with x = box x + 14 and no `style` attribute (the width check reads only those).
- An arrow is `<path d="M x,y L x,y …" fill="none" … marker-end="url(#h-…)">` with horizontal and vertical segments only. A jump is an `A7 7` arc, and a path with an arc is left out of the crossing test. Draw legend sample arrows as `<line>`, never `<path>`: a path is read as a diagram arrow whose tip must touch a box.
- An arrow label is `<rect … rx="4" fill="#fffdf7">` followed by `<text class="lbl">`, centred on a straight stretch of its own arrow.
- A dotted frame is `<rect … rx="18" fill="#ffffff" …>`. A `new` pill is a `<g transform="rotate(-45 cx cy)">`.

### Measure text once

- Measure the width of each text style one time, with the real font, and keep the table: title, meta, mono, note, status pill, `new` pill, edge label. Use the table for every occurrence. Do not measure again for each box.
- The pill words and the edge labels are a small, fixed set (`open`, `closed`, `merged`, `waiting`, `draft`, `new`, and each label in the vocabulary). Measure each word once, then set the pill or label width from it: text width plus the padding. Do not guess a width per pill.
- Wrap titles and notes with the table, not by a character count: the inner width is 232px (box 260 minus 14px each side), and a bold claim line must fit on one line. Fail the check when any line is wider than the inner width of its box.

### Checks on every run (script)

- The SVG is well-formed XML. Every node has a box, a kind, a number link, a status pill and a pill word that matches the state read from `gh` (an open draft pull request is `draft`, an open ready one `waiting`).
- Content, by text search: every item in the revision appears once, as a link to the right page (`issues` or `pull`); every merged pull request shows its merge commit and its authors; every issue shows its assignee after the number, or `?` when it has none, and every pull request shows `by` and its submitter; every `closed` box has a `closed by` arrow or says why not; the source has arrows leaving it; no arrow joins two siblings; every label is in the vocabulary; pill text uses the box color; the legend and the date line name the current items and the current date.
- Geometry, from the path points and the box and label rectangles: no segment passes through a box, a label or a pill; no unintended crossing; no two parallel lines closer than the spacing rules; no label covers the tail or the head; every arrowhead enters its box straight; no jog shorter than about 30px (a warning, not a failure); every endpoint, tail and tip, touches the edge of its box; the legend is in the top row and not left of the farthest right edge of the boxes and frames (a warning); no name runs into the pill or the cross, and none is smaller than 9px.
- Revision marks: exactly the boxes that are in this file and not in the previous revision's file have a `new` pill on the top-left corner, and no other box has one. Run `python3 check_diag.py current.svg previous_revision.svg`; the second file is the frozen previous revision, not a copy of the file before this edit.
- Report the largest empty rectangle. If a node or a framed group could fill it without making an arrow harder to follow, move it.
- Any arrow left out as too hard is named in the report.

When a check fails, fix the cause and run the script again. Do not look at an image to find out what is wrong.

### Looking at the picture

Look at most twice. Look only at crops of the regions that changed, at reduced size, not at the whole picture.

1. After the main layout, when boxes moved or arrows were added: one look at the changed regions.
2. At the end, after the hard arrows are routed: one look at the regions with jumps and `new` pills. Check that each hop bumps the right way and still reads as one line, and that nothing looks like clutter. Do not look at the jumps before this step.

Skip both looks when only states, dates or text changed. A PNG is only for this look. Do not keep it unless the user asks for one.
