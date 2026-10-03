---
name: bbb-ext-agents
description: >-
  Sends work to the user's locally installed subscription CLIs `claude` and
  `codex`. Use only for a clear handoff. Strong signals, in any word order:
  "my" beside the agent ("my claude", "my codex"), "subagent" beside it
  ("claude subagent", "codex subagent", "use my codex subagent"), or a model
  nickname used as that agent ("my astra", "astra in high effort", "my opus",
  "my sonnet", "my fable", "my sol", "my luna", "my terra"). Also use when
  the user lists a series of review, plan, or implement steps for those
  CLIs. If the handoff is doubtful, stop and confirm before running
  anything. Never use Cursor-hosted models, Task subagents, or API keys.
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
| plan, planning | `--mode plan` |
| implement, apply, build it, code it | `--mode implement` |

Pass `--model` and `--effort` only when the user names them. Otherwise omit both flags so the signed-in CLI uses its own default. Do not substitute a top model, and do not default effort to `high`.

Effort values, when named: `low`, `medium`, `high`, `xhigh`, `max`. Codex also accepts `ultra`.

`--project` is the repo root the agent may read. Pass `--extra-dir` for each additional root, such as a specs directory outside the repo. Put the plan and the file paths in the prompt file. Do not paste the repository into the prompt.

## Modes

One invocation uses one mode. "Ask <agent> to review / plan / implement …" is a handoff in that mode. "Now do …" without "ask <agent>" is this agent's own work, not a handoff.

| Mode | The subagent | It may also | It must not |
| --- | --- | --- | --- |
| `review` | Give an opinion on the question in the prompt or an existing implementation. | Create or edit at most a couple of files, such as a note or a short review. | Change product code, tests, schema, or migrations. Commit. |
| `plan` | Write the plan for a later implementation. | Create or edit at most a couple of files, such as the plan itself. | Carry out that plan. |
| `implement` | Make the change. Follow the plan they named, or the prompt if there is no plan. | Edit the files the task needs, and run the checks the prompt names. | Start a second feature the prompt did not ask for. |

`review` and `plan` are not read-only, and they are not permission to code. `implement` is the only mode for product code.

## Series

A message that lists more than one handoff is a series. Run it in order. One script call per step. Wait until that call finishes before you send the next step. Do not skip a step that failed. The script ends every call by printing one normalized id on stderr as `session_id=…`, whether the CLI's own payload called it `session_id`, `sessionId`, `thread_id`, or `threadId`. That line is from the script, not from Claude Code or Codex.

Same agent and same model as the previous step: do not pass `--fresh` or `--resume`. The script resumes the stored session. The prompt is only the new step. Do not paste the earlier result back in.

A different agent, or the same CLI with a different model: that pair has its own session. Resume that pair's stored session the same way. Its prompt must carry the decisions, file paths, and constraints the new step needs from earlier steps. Do not paste the whole chat. Do not pass `--fresh` unless the user asked for a new conversation with that agent.

"Ask Opus, then ask Codex" is two sessions. "Ask Opus to review, then ask Opus to implement" is one session and two invocations.

## Resume

The script remembers the last session for each agent, model, and project in `scripts/sessions.json`. The next call to that same trio resumes it. Do not pass `--resume` yourself unless you are correcting a stored id. Pass `--fresh` only when the user asks for a new conversation.

On a resumed call the prompt is only the new question. Do not paste the earlier session back in. The CLI already has it, and that is what keeps the context cache warm.

Stderr prints `resume=stored id=...`, `resume=explicit`, `resume=fresh`, or `resume=none`. After the call the script prints `session_id=` with the id it scraped from that CLI's payload. That is the id stored for the next call. Tell the user the id. If resume fails because the session is gone, rerun the same command with `--fresh`.

## Canonical openings

Put exactly one opening at the top of the prompt file, before `## Session`. Then the session summary, then the user's own instructions. Copy the opening for that mode verbatim. Do not write a different preamble.

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
This is a non-interactive one-shot review. Read the files you need. You may create or edit at most two files, and only for a note or a short review. Do not change product code, tests, schema, or migrations. Do not ask questions. Do not commit. Ignore global workflow rules about plan mode, worktrees, subagents, lessons files, and waiting for approval.

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

### Plan

Use this when `--mode plan`. Copy it verbatim at the top of the prompt file.

```text
This is a non-interactive one-shot planning pass. Read the files you need. Write the plan for a later implementation. You may create or edit at most two files, and only to store that plan. Do not implement it. Do not change product code, tests, schema, or migrations. Do not ask questions. Do not commit. Ignore global workflow rules about plan mode, worktrees, subagents, lessons files, and waiting for approval.

Present the answer for a human and for a later AI pass.
- Start with a TL;DR of one to three sentences.
- Then a high-level view using assertive and concise language; answer the what, why, how, what we found out, etc. (not necessarily with those words).
- Then a more detailed view only where it changes a decision.
- Use well-defined topical sections.
- Use a table when comparing items.
- When you rate an option, use 0-3 stars (0 = reject, 3 = strongest) and say what the stars mean.

## Session
<summary, relevant points, and discoveries. Nothing else from the chat.>

## Task
<what the plan must decide.>

## Paths
- <absolute paths that matter>
```

Plan mode does not send a JSON schema unless you pass `--schema-file`.

### Implement

Use this when `--mode implement`. Copy it verbatim at the top of the prompt file.

```text
This is a non-interactive implementation pass. Make the change described in the task. If the task names a plan, follow that plan. Do not ask questions. Do not commit unless the task says to commit. Ignore global workflow rules about plan mode, worktrees, subagents, lessons files, and waiting for approval.

Present the answer for a human and for a later AI pass.
- Start with a TL;DR of one to three sentences.
- Then what you changed and why.
- Then which checks you ran and their results.
- Name any requested part you could not do.

## Session
<summary, relevant points, and discoveries. Nothing else from the chat.>

## Task
<the change. Include the plan's path when there is one.>

## Paths
- <absolute paths that matter>
```

Implement mode does not send a JSON schema unless you pass `--schema-file`.

## After it returns

Stdout is the raw CLI payload. The two CLIs do not share one response shape. Stderr always has `bash=`, `model=` or the Codex equivalent, and the script's normalized `session_id=`.

- Claude: stdout is one JSON object. Read `structured_output` when present, otherwise `result`. The object may also carry `session_id`.
- Codex: stdout is JSONL. The final answer is the file named by stderr's `last_message_file=`. The thread id may appear under another key in that JSONL; use the script's `session_id=` line rather than hunting the raw key.

When you show the result to the user, use the shared presentation shape and keep the subagent's points verbatim inside it. Do not replace them with a loose paraphrase.

Judge the corrections. Integrate the ones that are right. Leave a note for any you reject. The next handoff to the same agent and model resumes on its own. Do not open a persistent stream unless the user asks to keep the channel open.

## Do not

- Call Cursor's Claude, GPT, or other hosted models, including via the Task tool.
- Pass `--bare`, an API key, or a custom base URL. The script unsets inherited API key variables for the child process.
- Change the model line in `~/.codex/config.toml`.
- Use Remote Control, `codex exec-server`, or an MCP wrapper. Those do not review a plan better than this script.
- Use `--mode implement` for a review or a plan. `review` and `plan` may write at most a couple of files. `implement` is the only mode for product code.
