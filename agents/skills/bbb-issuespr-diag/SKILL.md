---
name: bbb-issuespr-diag
disable-model-invocation: true
description: >-
  Draws a directed acyclic graph of GitHub issues and pull requests as a
  hand-authored SVG: parent to child, what closed what, what is still open.
  Use ONLY when the user explicitly asks (for example /bbb-issuespr-diag,
  names this skill, or asks for an issue/PR lineage diagram or DAG). Do not
  run it because a conversation mentions issue numbers.
---

# Github issue and pull-request lineage diagram

Apply only on an explicit request. This is not a composition diagram. Do not use it to show how a result is assembled. That is `bbb-code-flow`.

Borrow from `bbb-code-flow` only the drawing hygiene: cream page `#f3f0e8`, ink `#1c2430`, SVG with a title and a description, numeric entities for dashes and arrows, orthogonal paths, and a look at a raster before you call it done. The graph rules below win when they differ.

## What a node is

One box is one issue or one pull request. Read the facts from `gh`, not from memory.

Each box shows:

- `ISSUE`, `UMBRELLA`, or `PR`, and the number, as a link (see Links)
- the title
- opened date, and closed or merged date when it has one
- the merge commit, short, on a pull request
- a design document or memo when one is the source of that item

A status pill sits in the upper right. The word is `open`, `closed`, `merged`, or `waiting`.

| State | Box | Pill fill | Pill text |
|---|---|---|---|
| Open issue or open umbrella | `#f8e8e4` / stroke `#8a3030` | `#9f2d2d` | the box fill `#f8e8e4` |
| Closed issue or closed umbrella | gray `#eceae6` / stroke `#6e6a64` | `#4e4b48` | the box fill `#eceae6` |
| Merged pull request | `#e7f0fb` / stroke `#1d4e89` | `#163e73` | the box fill `#e7f0fb` |
| Pull request waiting for review | saturated yellow `#ffe566` / stroke `#c48a00` | `#e6a100` | the box fill `#ffe566` |

Open issues and open umbrellas are the same color. Say `UMBRELLA` in the label when it is one. Closed is gray, not green.

Set the pill text with a `style="fill:…"` attribute. A shared SVG text class will otherwise paint it black.

## Links

Every issue number and every pull-request number is a link to the GitHub page. Issue `#1752` goes to `https://github.com/ar/mgl/issues/1752`. Pull request `#1757` goes to `https://github.com/ar/mgl/pull/1757`. Use the repository that owns the item. In SVG, wrap the number text in `<a href="…">`.

If the user asks for a PDF, those same numbers are links there too. A PNG cannot hold a link. Do not promise links on a raster.

## What an arrow is

The picture is a directed acyclic graph. Arrows point forward, from the earlier item to the later one.

- A source has no arrow pointing into it. `#1752` is that kind of node for the acquirer-fee lineage.
- A child, a follow-up, or work that exists because X required it: arrow from X to that item. Label it `child`, `follow-up`, `led to`, `spawned`, or `found`, using the word that matches the fact.
- A pull request that closed an issue: arrow from the issue to the pull request, labeled `closed by`. Say the pull request number on the box as well.
- A pull request that did the work but did not close the issue: dashed arrow, labeled `did the work`.
- A reference that is not parentage (`references`, `mentioned`, `uses`, `related`, `implements`): dashed.
- If two items both come from the same item, draw two arrows out of that item. Do not draw an arrow between the two siblings. Parallel is not a chain.
- A node may have no outgoing arrow. An open issue with no pull request is that kind of node. It still has its incoming arrow.

A dotted frame may name an area (`ss-visa`, `ss-mastercard`, `jCard`). The frame does not replace an arrow. Do not put the parentage only in a section title.

## Layout

Use the plane. Rows and columns are for alignment, not a substitute for edges.

- Leave a gap long enough that the label, which has an opaque background, does not cover the whole shaft. The tail and the arrowhead stay visible. A gap under about 150px is too small for a `closed by` label.
- Draw every path first, then every label, so a later path cannot hide an earlier label. Labels sit on top of the stroke.
- Put the label on a long segment of that arrow, not on a stub, and not on a bus shared by many arrows. A shared bus stacks the words.
- When one item has several children, fan the arrows. A vertical column of children with the parent on one side and the closing pull request on the other is the pattern: arrows leave the parent and enter each child; `closed by` arrows leave those children and converge on the pull request. Give each arrow its own vertical position so the labels do not sit on each other, and so each arrowhead can be seen.
- Do not route an arrow through a box. If a box sits between two ends, go around it in a gutter.
- Prefer a wider picture to a crossing.

## Files

Small corrections edit the current SVG. Write a new `_v2`, `_v3`, … file only when the user asks for a new revision or the layout is being replaced. Do not emit a PDF unless the user asks for one. When they do, keep the issue and pull-request numbers as links.

## Check

Rasterize and look. Confirm:

- the source the user named has arrows leaving it
- every `closed` box has a visible `closed by` arrow to a pull request, or the box says why it has none
- no sibling is drawn as the parent of the other
- labels do not cover the tail or the head
- pill text is the box color, not black
- each issue number and each pull-request number is a link to its GitHub page
