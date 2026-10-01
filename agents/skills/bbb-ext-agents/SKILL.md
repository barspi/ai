---
name: bbb-ext-agents
description: >-
  Sends work to the user's locally installed subscription CLIs `claude` and
  `codex`. Use only for a clear handoff. Strong signals, in any word order:
  "my" beside the agent ("my claude", "my codex"), "subagent" beside it
  ("claude subagent", "codex subagent", "use my codex subagent"), or a model
  nickname used as that agent ("my astra", "astra in high effort", "my opus",
  "my sonnet", "my fable", "my sol", "my luna", "my terra"). If the handoff
  is doubtful, stop and confirm before running anything. Never use
  Cursor-hosted models, Task subagents, or API keys.
---

# Local subscription agents

The user wants the `claude` and `codex` binaries already logged in on their Mac. Cursor model APIs and Task subagents are a different, per-token bill. Do not use them for this request.

If `claude` or `codex` is not installed, stop. This skill only runs on the machine where those CLIs are logged in.

## When to run

Run only when the user is handing work to that local CLI. Strong signals, in any word order:

- "my" next to the agent: "my claude", "my codex"
- "subagent" next to the agent: "use my claude subagent", "codex subagent"
- a model nickname used as the agent: "my astra", "astra in high effort", "my opus", "my sonnet", "my fable", "my sol", "my luna", "my terra"

"astra", "sol", "luna", or "terra" means Codex. "opus", "sonnet", or "fable" means Claude. Combine that with whatever effort they named.

If the handoff is doubtful, stop and ask before running the script. A factual question is not a handoff. The bare names "Claude Code", "Codex CLI", and "codex astra" are not a handoff.

Verified once against Claude Code 2.1.284 and Codex CLI 0.157.1. The script checks that the flags it needs are still in `--help`. If a flag is missing, stop, read that `--help`, and update the script. Do not redo a web research pass first, and do not invent a replacement flag.

## Command

This file is `SKILL.md`. The script is `scripts/ask-local-agent.sh` in the same directory. Resolve that directory from the `SKILL.md` you actually opened, including when that path is a symlink. Do not hard-code the absolute path from the user's home. Execute the script itself so it can select Bash. Do not launch it with `/bin/bash`.

```bash
SKILL_DIR="<directory containing this SKILL.md>"
SCRIPT="$SKILL_DIR/scripts/ask-local-agent.sh"
"$SCRIPT" \
  --agent codex \
  --mode review \
  --project "$PROJECT" \
  --prompt-file "$PROMPT_FILE"
```

| User words | Arguments |
| --- | --- |
| my codex, default model, review | `--agent codex --mode review` |
| my astra, high effort, review | `--agent codex --model astra --effort high --mode review` |
| sol / luna / terra | `--model sol` / `luna` / `terra` |
| my claude, sonnet, medium effort, review | `--agent claude --model sonnet --effort medium --mode review` |
| opus / fable | `--model opus` / `fable` |
| implement, apply, edit | `--mode implement` only when they asked that agent to change files |

Pass `--model` and `--effort` only when the user names them. Otherwise omit both flags so the signed-in CLI uses its own default. Do not substitute a top model, and do not default effort to `high`.

Effort values, when named: `low`, `medium`, `high`, `xhigh`, `max`. Codex also accepts `ultra`.

`--project` is the repo root the agent may read. Pass `--extra-dir` for each additional root, such as a specs directory outside the repo. Put the plan and the file paths in the prompt file. Do not paste the repository into the prompt.

## Resume

The script remembers the last session for each agent, model, and project in `scripts/sessions.json`. The next call to that same trio resumes it. Do not pass `--resume` yourself unless you are correcting a stored id. Pass `--fresh` only when the user asks for a new conversation.

On a resumed call the prompt is only the new question. Do not paste the earlier session back in. The CLI already has it, and that is what keeps the context cache warm.

Stderr prints `resume=stored id=...`, `resume=explicit`, `resume=fresh`, or `resume=none`. After the call it prints `session_id=`. That id is the one stored for the next call. Tell the user the id. If resume fails because the session is gone, rerun the same command with `--fresh`.

## Canonical openings

Put exactly one opening at the top of the prompt file, before `## Session`. Then the session summary, then the user's own instructions.

Only the Review opening is written. Implement, refactor, and research are reserved. Do not invent their text. If the user asks for one of those, say it is not written yet and ask whether to draft it.

Every opening starts with the shared presentation rules, then the case rules.

### Shared presentation

```text
Present the answer for a human and for a later AI pass.
- Start with a TL;DR paragraph, or two at most.
- Then a high-level view using assertive and concise language; answer the what, why, how, what we found out, etc. (not necessarily with those words).
- Then a more detailed view only where it changes a decision.
- Use well-defined topical sections.
- Use a table when comparing items.
- When you rate an option, use 0-3 stars (0 = reject, 3 = strongest) and say what the stars mean.
```

### Review

Use this when `--mode review`. Copy it verbatim at the top of the prompt file.

```text
This is a non-interactive one-shot review. Read the files you need. Do not edit anything. Do not ask questions. Ignore global workflow rules about plan mode, worktrees, subagents, lessons files, and waiting for approval.

Present the answer for a human and for a later AI pass.
- Start with a TL;DR of one to three sentences.
- Then a high-level view using assertive and concise language; answer the what, why, how, what we found out, what was good, wrong, missing, misguided etc. (not necessarily with those words).
- Then a more detailed view only where it changes a decision.
- Use well-defined topical sections.
- Use a table when comparing items.
- When you rate an option, use 0-3 stars (0 = reject, 3 = strongest) and say what the stars mean.

## Session
<summary, relevant points, and discoveries. Nothing else from the chat.>

## Task
<what the user asked. For a review this may be almost empty.>

## Plan
<full plan>

## Paths
- <absolute paths that matter>

Also return the required JSON object. Put the TL;DR, the high-level view, and any detailed sections in `writeup` as markdown. Use `verdict`, `incorrect`, `missed`, `corrections`, and `reject` for the structured points. Do not add JSON keys.
```

Review mode sends a JSON schema for `verdict`, `writeup`, `incorrect`, `missed`, `corrections`, and `reject`. Pass `--schema-file` to replace it, or `--no-schema` for prose. With `--no-schema`, the Review opening above is the whole format; drop the JSON sentence.

## After it returns

Stdout is the raw CLI payload. Stderr has `bash=`, `model=`, `last_message_file=` (Codex), and `session_id=`.

- Claude: read `structured_output` when present, otherwise `result`. `session_id` is also inside the JSON object.
- Codex: stdout is JSONL. The final answer is the file named by `last_message_file`.

When you show the result to the user, use the shared presentation shape and keep the subagent's points verbatim inside it. Do not replace them with a loose paraphrase.

Judge the corrections. Integrate the ones that are right. Leave a note for any you reject. The next handoff to the same agent and model resumes on its own. Do not open a persistent stream unless the user asks to keep the channel open.

## Do not

- Call Cursor's Claude, GPT, or other hosted models, including via the Task tool.
- Pass `--bare`, an API key, or a custom base URL. The script unsets inherited API key variables for the child process.
- Change the model line in `~/.codex/config.toml`.
- Use Remote Control, `codex exec-server`, or an MCP wrapper. Those do not review a plan better than this script.
- Use `--mode implement` for a review. Their config allows workspace writes; the script forces read-only for reviews.
