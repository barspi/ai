---
name: bbb-annotations
disable-model-invocation: true
description: >-
  Reviews inline document annotations fenced as ==BBB ...== (surgical edits),
  ==QQQ ...== (questions answered in chat, then removed), and ==RRR-N ...==
  (numbered issues resolved iteratively in chat; marker stays until the user
  says to remove that RRR-N). Applies BBB edits only at the annotated locus;
  answers QQQ and RRR in chat. Use ONLY when the user explicitly requests it
  (for example /bbb-annotations, names this skill, says to review / address /
  process / apply their annotations, or to work on or remove a specific
  RRR-N). NEVER apply this skill automatically during regular project work,
  planning, or document editing, even if ==BBB, ==QQQ, or ==RRR-N markers are
  present. If a BBB looks like extra work outside the document, ask the user
  and leave the marker in place — do not act.
---

# BBB annotations

This skill is to be applied ONLY UPON USER'S REQUEST!!!
NEVER apply or execute this skill automatically.

Do not run this skill because you saw `==BBB` / `==QQQ` / `==RRR-N` while
coding, planning, implementing a task, or editing a document. Presence of
markers is not a trigger. Finishing a task is not a trigger. "Helpful"
cleanup of leftover annotations is not a trigger.

Apply it only when the user clearly asks you to — e.g. `/bbb-annotations`,
names this skill, tells you to review / address / process / apply their
BBB/QQQ/RRR annotations, or to iterate on / edit for / remove a specific
`RRR-N`.

The user reviews a document (pre-existing or agent-written) and leaves
inline annotations for the agent. Three types exist today. All are fenced
with `==` so Markdown highlighters show them as highlights while drafting.

Handle **only** these three forms. Ordinary `==highlighted text==` is
**not** an annotation — leave it untouched.

## Annotation syntax

Markers appear **right next to** (typically **right after**) the text they
refer to. They may sit in prose, a list item, a table cell, after an image,
or anywhere else in the file.

### BBB — surgical edit in the document

```
Some regular lorem ipsum text..  ==BBB change this to all uppercase and add links to the relevant material==
```

Address the annotation with a **surgical** edit of the referred-to text,
then remove the annotation (the fencing and its contents) — **unless** it
looks like extra work outside the document or is ambiguous (see below).

When you say SURGICAL edits, it means only the annotated/referred to text
should be edited, and not the general structure of the document.

### QQQ — question answered in chat

```
Some regular lorem ipsum text..  ==QQQ what is the origin of Lorem ipsum, and why did you choose to use that text here instead of some russian poem?==
```

All QQQ annotations are meant for the agent to answer BACK TO ME (not in
the doc itself). They should be removed from the text anyway, after the
agent has given me a response.

The response should include at least the first few words of my question, as
many as needed to unequivocally identify which question you're answering.

### RRR-N — interactively resolving issues

```
Some regular lorem ipsum text..  ==RRR-N  some issue to resolve==
```

`N` is an integer used for reference. IDs do not need to be consecutive in
the file.

These new annotations are meant to be similar to QQQ in that I will be
asking you a question because I don't like what is written in the text,
and we're going to be iterating until we resolve it.

So when you find a `==RRR-N ... ==` comment, you will

- answer my question here in the chat, as with QQQ using the `RRR-N`
  string with the reference number instead of the N of course
- You WILL NOT DELETE the annotation from the source file
- We will iterate here until I tell you how you should address the
  RRR-N. And if addressing the issue involves editing the file, you
  will do the JUST THE REQUESTED edits, leaving the annotation in the
  file for me to study your changes.
- When I'm satisfied, I'll tell you to remove the RRR-N annotation
  (and only THAT one) and we'll consider the issue resolved. Other
  RRR-N ocurrences must be kept in the file.

Do not remove an `RRR-N` marker because you answered it, because you
edited nearby text, because other markers were stripped, or because
another `RRR-M` was resolved. Remove it only when the user names that
exact ID for removal.

## When to run

Only after an explicit user request (see the rule at the top). Then:

- If they name file(s), use those.
- If they name a specific `RRR-N` (iterate, edit, or remove), handle
  that ID only — do not sweep the rest of the file unless they asked
  to review annotations generally.
- If they do not name files, search the workspace for `==BBB`, `==QQQ`,
  and `==RRR-` (skip `node_modules`, `.git`, lockfiles, and this skill's
  own files).

If none are found, say so and stop. Do not rewrite the file.

### When NOT to run

- Ordinary coding, refactoring, debugging, or other project work
- Drafting or updating PLAN.md / PROGRESS.md / other docs as part of a task
- Reading or editing a file that happens to contain `==BBB` / `==QQQ` /
  `==RRR-N`
- Assuming the user is done annotating and "handling them" unprompted
- Removing an `RRR-N` because the conversation around it feels finished

## Workflow

Copy this checklist and track it:

```
- [ ] Inventory every ==BBB ...==, ==QQQ ...==, and ==RRR-N ...== (file, line, surrounding text, full marker body, and RRR id)
- [ ] Answer every QQQ in chat (not in the document)
- [ ] Answer every RRR-N in chat, identified as RRR-<number>; do NOT delete those markers
- [ ] Classify each BBB: in-document surgical edit vs outside-the-document / ambiguous
- [ ] Apply only the clearly in-document BBB edits; remove those markers
- [ ] For outside-the-document or ambiguous BBB: ask the user; leave those markers in place
- [ ] Strip answered QQQ markers
- [ ] Leave every RRR-N marker in place unless the user named that exact ID for removal
- [ ] If the user named an RRR-N to address: JUST THE REQUESTED edits; keep that marker
- [ ] If the user named an RRR-N to remove: delete only that ID's marker(s); keep all other RRR-* 
- [ ] Confirm leftover markers are held BBB and all remaining RRR-N (ordinary ==highlights== may remain)
```

1. **Inventory.** Read the file(s). Record each marker with enough nearby
   text to know the locus. Do not skip markers inside lists, tables, or
   other Markdown constructs. Ignore a match only when it is clearly a
   *literal example of the syntax itself* (for example inside this skill).
2. **QQQ first in the reply.** Answer in chat before or alongside the edit
   summary. Never write the answer into the document.
3. **RRR-N in the reply.** Answer in chat, labeled with the actual id
   (`RRR-3`, `RRR-12`, …) plus enough of the question to identify it.
   You WILL NOT DELETE the annotation from the source file.
4. **BBB edits (in-document only).** If the annotation is clearly a
   document-text change, follow it. Change only the referred-to text.
   Then delete that marker.
5. **BBB hold (outside or ambiguous).** If a BBB annotation looks as if
   the agent should do any extra work outside the document (such as
   generate a new file, refactor some external code, etc.) DO NOT DO IT.
   Come back with a question to the user about how we should proceed.
   And in this case, the annotation should not be removed from the
   document until what to do next becomes clear (e.g. do the work, do
   not do the work but just edit the text, or whatever the user
   instructs). If the wording of the annotation looks ambiguous to the
   agent/model, it's better to be SAFE and ask, than to be SORRY and
   act in the wrong way. Still process the ones you can.
6. **Strip QQQ markers** after answering. Leave the surrounding document
   text as it was (aside from cleaning whitespace the marker occupied).
7. **RRR follow-up (same conversation or a later explicit request).** We
   will iterate here until I tell you how you should address the RRR-N.
   And if addressing the issue involves editing the file, you will do
   the JUST THE REQUESTED edits, leaving the annotation in the file for
   me to study your changes. When I'm satisfied, I'll tell you to remove
   the RRR-N annotation (and only THAT one) and we'll consider the issue
   resolved. Other RRR-N ocurrences must be kept in the file.
8. **Verify.** Re-scan for `==BBB`, `==QQQ`, and `==RRR-`. Summarize what
   you edited, what you answered, which BBB markers you held, and which
   RRR-N remain.

## What "surgical" means

The annotation sits typically right after the target. Infer the smallest
natural unit that the wording refers to:

| Where the marker sits | Default locus |
| --- | --- |
| End of a sentence / clause | That sentence or clause |
| In a paragraph, "this" / "this sentence" | The immediately preceding sentence |
| "this paragraph" / "this section" | That paragraph, or that heading+body until the next heading |
| In a list item | That item only (not siblings, not the list as a whole) |
| In a table cell | That cell only |
| Right after an image (or similar inline embed) | That image/embed line (alt, title, or adjacent caption if the note is about it) |

**Do not:**

- Restyle, rephrase, or restructure unannotated parts of the document
- "While I'm here" cleanups, heading reshuffles, or consistency passes
- Move sections, split/merge files, or retitle the doc unless the
  annotation explicitly says so
- Expand a cell/item edit into the rest of the table/list
- Answer QQQ or RRR by inserting prose, footnotes, or comments into the file
- Strip or rewrite `==...==` highlights that are not `==BBB` / `==QQQ` /
  `==RRR-N`
- Delete an `RRR-N` marker unless the user named that exact ID for removal
- Delete other `RRR-*` markers while removing the one the user named
- Do any extra work outside the document (new files, refactors, code
  changes, generating assets, etc.) just because a BBB looks like it
  wants that

If a BBB annotation looks as if the agent should do any extra work
outside the document (such as generate a new file, refactor some
external code, etc.) DO NOT DO IT. Come back with a question to the
user about how we should proceed. And in this case, the annotation
should not be removed from the document until what to do next becomes
clear (e.g. do the work, do not do the work but just edit the text, or
whatever the user instructs).

If the wording of the annotation looks ambiguous to the agent/model,
it's better to be SAFE and ask, than to be SORRY and act in the wrong
way. Leave that marker in place. Do not guess.

If an instruction for how to address an `RRR-N` looks like extra work
outside the document or is ambiguous, ask before acting. Do not delete
that marker.

## Marker matching

Treat as annotations **only** when the inside starts with `BBB`, `QQQ`,
or `RRR-<integer>` plus whitespace:

```
==BBB <instruction>==
==QQQ <question>==
==RRR-N <issue to resolve>==
```

- Case-sensitive: `BBB`, `QQQ`, `RRR`, not `bbb` / `Qqq` / `rrr`
- `N` is an integer (`RRR-1`, `RRR-12`, …). IDs need not be consecutive.
  `==RRR` without a `-` and integer is not an annotation.
- Non-greedy up to the next `==`
- Usually one line; if a marker wraps, still take it as one annotation
- Several markers may appear in one paragraph, cell, or item — handle each
- After removal, collapse leftover double spaces and trim dangling
  whitespace at end of line. Do not otherwise reflow the paragraph
- Removing `RRR-N` means that exact id only (e.g. `RRR-3`). Leave
  `RRR-1`, `RRR-2`, `RRR-12`, and every other id. If the same id appears
  more than once and it is unclear which to remove, ask.

## Chat response shape

Use this shape (omit an empty section):

```markdown
## QQQ

**"<first words of question...>"** (`path:line`)
<answer>

**"<first words of next question...>"** (`path:line`)
<answer>

## RRR

**RRR-3** (`path:line`) — "<first words of the issue...>"
<answer>
Marker left in the file. Say how to address RRR-3, or tell me to remove
it when you're satisfied.

**RRR-12** (`path:line`) — "<first words of the issue...>"
<answer>
Marker left in the file.

## BBB

- `path`: <short description of the surgical edit>

## Held — need your call

**"<first words of the BBB...>"** (`path:line`)
This looks like work outside the document / is ambiguous. How should we
proceed? (do the work, only edit the text, or something else)
```

Identify each RRR by the `RRR-N` string with the actual number. Quote as
much of each QQQ (and each held BBB / RRR body) as needed so two similar
items cannot be confused. If several files were processed, group by file.

## Examples

**BBB in prose**

Before:

```
Some regular lorem ipsum text..  ==BBB change this to all uppercase and add links to the relevant material==
```

After (document): the lorem sentence is edited as instructed; the `==BBB ...==` span is gone. Sibling paragraphs are unchanged.

**QQQ in prose**

Before:

```
Some regular lorem ipsum text..  ==QQQ what is the origin of Lorem ipsum, and why did you choose to use that text here instead of some russian poem?==
```

After (document): `Some regular lorem ipsum text..` — marker removed, wording otherwise unchanged.

After (chat): answer identified by `"what is the origin of Lorem ipsum..."` (include more of the question if another QQQ is similar).

**RRR-N in prose** — answer in chat; do not delete the marker:

```
Some regular lorem ipsum text..  ==RRR-2  this reads like marketing; what should it say instead?==
```

Chat: identify as **RRR-2**, answer the issue. Document: marker stays.

Later, user: "RRR-2 rewrite that sentence as a factual one-liner."
→ JUST THE REQUESTED edit to the referred-to text; `==RRR-2 ...==` stays.

Later, user: "remove RRR-2"
→ delete only the `RRR-2` marker. Leave `RRR-1`, `RRR-7`, and any other
`RRR-*` in the file.

**List item (BBB)** — edit that item only:

```
- Deploy to staging first  ==BBB say why staging is required==
- Then production
```

**Table cell (QQQ)** — answer in chat; cell text stays, marker goes:

```
| Latency | 40ms ==QQQ p50 or p99?== |
```

**Image line (BBB)** — touch that line only:

```
![arch](./arch.png) ==BBB alt-text should mention the queue==
```

**Outside-the-document / ambiguous BBB** — do not act; ask; leave the marker:

```
Next: extract auth into its own package.  ==BBB split this into a new crate and update all callers==
```

Chat: quote enough of the BBB to identify it, ask how to proceed (do the
work, only edit the text, or other). Document: marker stays until the
user decides.
