#!/usr/bin/env bash
# One-shot review or implement call against the locally installed
# Claude Code or Codex CLI, using the subscription login on this machine.
# Stdout is the CLI's JSON (Claude) or JSONL (Codex). Metadata goes to stderr.
#
# macOS /bin/bash is 3.2. This block is safe on 3.2 and re-execs the newest
# bash found (Homebrew bash on this Mac is 5.3) before any bash-4 syntax.
if [[ -z "${ASK_LOCAL_AGENT_BASH:-}" ]]; then
  current_key="$(printf '%03d%03d%03d' "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}" "${BASH_VERSINFO[2]}")"
  best=""
  best_key="$current_key"
  for candidate in /opt/homebrew/bin/bash /usr/local/bin/bash /bin/bash; do
    [[ -x "$candidate" ]] || continue
    key="$("$candidate" -c 'printf "%03d%03d%03d" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}" "${BASH_VERSINFO[2]}"' 2>/dev/null || true)"
    [[ -n "$key" ]] || continue
    if [[ "$key" > "$best_key" ]]; then
      best="$candidate"
      best_key="$key"
    fi
  done
  if [[ -n "$best" ]]; then
    export ASK_LOCAL_AGENT_BASH=1
    exec "$best" "$0" "$@"
  fi
fi

set -euo pipefail
echo "bash=$BASH version=$BASH_VERSION" >&2

usage() {
  cat <<'EOF' >&2
Usage: ask-local-agent.sh --agent claude|codex --project DIR --prompt-file FILE \
  [--model NAME] [--effort LEVEL] [--mode review|implement] \
  [--schema-file FILE | --no-schema] [--resume ID | --fresh] [--extra-dir DIR]... \
  [--dry-run]

A later call to the same agent, model, and project resumes the last
session automatically, so the CLI can reuse that conversation. Pass
--fresh to start a new one. An explicit --resume ID overrides the stored one.

Omit --model to use the CLI account default. Do not pass a model the
account cannot use.
Omit --effort to use the CLI account default.

Models, when set: codex accepts astra, sol, luna, terra or a full id
(gpt-6-astra). Claude accepts opus, sonnet, fable or a full model id.
Effort, when set: low, medium, high, xhigh, max. Codex also accepts ultra.
Default mode is review (read-only). implement is only for an explicit edit request.
EOF
  exit 2
}

agent=""
model=""
effort=""
project=""
prompt_file=""
mode="review"
schema_file=""
no_schema=0
resume_id=""
fresh=0
dry_run=0
created_schema=0
extra_dirs=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) agent="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    --effort) effort="${2:-}"; shift 2 ;;
    --project) project="${2:-}"; shift 2 ;;
    --prompt-file) prompt_file="${2:-}"; shift 2 ;;
    --mode) mode="${2:-}"; shift 2 ;;
    --schema-file) schema_file="${2:-}"; shift 2 ;;
    --no-schema) no_schema=1; shift ;;
    --resume) resume_id="${2:-}"; shift 2 ;;
    --fresh) fresh=1; shift ;;
    --extra-dir) extra_dirs+=("${2:-}"); shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ -n "$agent" && -n "$project" && -n "$prompt_file" ]] || usage
[[ "$agent" == "claude" || "$agent" == "codex" ]] || usage
[[ "$mode" == "review" || "$mode" == "implement" ]] || usage
[[ -d "$project" ]] || { echo "Project directory not found: $project" >&2; exit 2; }
[[ -f "$prompt_file" ]] || { echo "Prompt file not found: $prompt_file" >&2; exit 2; }
[[ "$no_schema" -eq 0 || -z "$schema_file" ]] || { echo "Pass either --schema-file or --no-schema" >&2; exit 2; }
[[ "$fresh" -eq 0 || -z "$resume_id" ]] || { echo "Pass either --resume or --fresh" >&2; exit 2; }

state_file="$(cd "$(dirname "$0")" && pwd)/sessions.json"
project_key="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$project")"
session_slot="${agent}|${model:-default}|${project_key}"

lookup_session() {
  python3 - "$state_file" "$session_slot" <<'PY'
import json, sys
path, slot = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path, encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    data = {}
row = data.get(slot) or {}
sid = row.get("session_id") if isinstance(row, dict) else None
if isinstance(sid, str) and len(sid) > 8:
    print(sid)
PY
}

save_session() {
  local sid="$1"
  [[ -n "$sid" && "$sid" != "unknown" ]] || return 0
  python3 - "$state_file" "$session_slot" "$sid" <<'PY'
import json, sys
from datetime import datetime, timezone
path, slot, sid = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.load(open(path, encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    data = {}
if not isinstance(data, dict):
    data = {}
data[slot] = {"session_id": sid, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
}

if [[ -n "$effort" ]]; then
  case "$effort" in
    low|medium|high|xhigh|max) ;;
    ultra)
      [[ "$agent" == "codex" ]] || { echo "ultra effort is Codex-only" >&2; exit 2; }
      ;;
    *) echo "Unsupported effort: $effort" >&2; exit 2 ;;
  esac
fi

resolve_model() {
  local raw="$1"
  local key
  key="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  if [[ "$agent" == "codex" ]]; then
    case "$key" in
      astra) printf '%s' "gpt-6-astra" ;;
      sol) printf '%s' "gpt-6-sol" ;;
      luna) printf '%s' "gpt-6-luna" ;;
      terra) printf '%s' "gpt-5.6-terra" ;;
      gpt-*|codex-*) printf '%s' "$key" ;;
      *) echo "Unknown Codex model shortcut: $raw" >&2; exit 2 ;;
    esac
  else
    case "$key" in
      opus|sonnet|fable) printf '%s' "$key" ;;
      claude-*) printf '%s' "$key" ;;
      *) echo "Unknown Claude model shortcut: $raw" >&2; exit 2 ;;
    esac
  fi
}

if [[ -n "$model" ]]; then
  model="$(resolve_model "$model")"
fi
session_slot="${agent}|${model:-default}|${project_key}"

if [[ "$no_schema" -eq 0 && -z "$schema_file" ]]; then
  schema_tmp="$(mktemp "${TMPDIR:-/tmp}/local-agent-schema.XXXXXX")"
  schema_file="${schema_tmp}.json"
  mv "$schema_tmp" "$schema_file"
  created_schema=1
  cleanup_schema() {
    if [[ "${created_schema:-0}" -eq 1 ]]; then
      rm -f "$schema_file"
    fi
  }
  trap cleanup_schema EXIT
  cat >"$schema_file" <<'EOF'
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "verdict": {"type": "string", "enum": ["sound", "needs_changes", "blocked"]},
    "writeup": {"type": "string"},
    "incorrect": {"type": "array", "items": {"type": "string"}},
    "missed": {"type": "array", "items": {"type": "string"}},
    "corrections": {"type": "array", "items": {"type": "string"}},
    "reject": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["verdict", "writeup", "incorrect", "missed", "corrections", "reject"]
}
EOF
fi

require_flags() {
  local bin="$1"
  shift
  local help flag
  help="$("$bin" --help 2>&1 || true)"
  for flag in "$@"; do
    if ! grep -q -F -- "$flag" <<<"$help"; then
      echo "Installed $("$bin" --version 2>&1 | head -1) has no $flag. Read its --help and update this script. Do not guess a replacement." >&2
      exit 3
    fi
  done
}

# Child process must use the subscription login, not an API key inherited from the shell.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL OPENAI_API_KEY OPENAI_BASE_URL CODEX_API_KEY || true

run_cmd() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'DRY-RUN' >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
    return 0
  fi
  "$@"
}

note_session() {
  local file="$1"
  python3 - "$file" <<'PY' >&2 || true
import json, sys
path = sys.argv[1]
found = []
def take(obj):
    if not isinstance(obj, dict):
        return
    for key in ("session_id", "sessionId", "thread_id", "threadId"):
        val = obj.get(key)
        if isinstance(val, str) and len(val) > 8:
            found.append(val)
    for key in ("thread", "session"):
        take(obj.get(key))
with open(path, "r", encoding="utf-8", errors="replace") as fh:
    text = fh.read()
for line in text.splitlines() or [text]:
    line = line.strip()
    if not line:
        continue
    try:
        take(json.loads(line))
    except json.JSONDecodeError:
        continue
sid = found[0] if found else "unknown"
print("session_id=" + sid)
if sid != "unknown":
    open(path + ".session", "w", encoding="utf-8").write(sid)
PY
  if [[ -f "${file}.session" ]]; then
    save_session "$(cat "${file}.session")"
    rm -f "${file}.session"
  fi
}

if [[ "$fresh" -eq 1 ]]; then
  echo "resume=fresh slot=$session_slot" >&2
elif [[ -n "$resume_id" ]]; then
  echo "resume=explicit id=$resume_id" >&2
else
  resume_id="$(lookup_session || true)"
  if [[ -n "$resume_id" ]]; then
    echo "resume=stored id=$resume_id" >&2
  else
    echo "resume=none slot=$session_slot" >&2
  fi
fi

if [[ "$agent" == "claude" ]]; then
  bin="$(command -v claude || true)"
  [[ -n "$bin" ]] || { echo "claude is not on PATH" >&2; exit 127; }
  require_flags "$bin" --print --output-format --json-schema --effort --permission-mode --permission-prompts --tools --add-dir --resume
  args=("$bin" -p --output-format json --add-dir "$project")
  [[ -n "$model" ]] && args+=(--model "$model")
  [[ -n "$effort" ]] && args+=(--effort "$effort")
  for dir in "${extra_dirs[@]}"; do
    args+=(--add-dir "$dir")
  done
  if [[ "$mode" == "review" ]]; then
    args+=(--permission-mode plan --permission-prompts none --tools Read,Grep,Glob)
  else
    args+=(--permission-mode acceptEdits --permission-prompts none --allowedTools "Read,Edit,Grep,Glob,Bash")
  fi
  if [[ -n "$schema_file" ]]; then
    args+=(--json-schema "$(cat "$schema_file")")
  fi
  if [[ -n "$resume_id" ]]; then
    args+=(--resume "$resume_id")
  fi
  echo "agent=claude model=${model:-default} effort=${effort:-default} mode=$mode bin=$bin" >&2
  capture="$(mktemp "${TMPDIR:-/tmp}/local-agent-out.XXXXXX")"
  if [[ "$dry_run" -eq 1 ]]; then
    run_cmd "${args[@]}" <"$prompt_file"
    rm -f "$capture"
    exit 0
  fi
  set +e
  (cd "$project" && "${args[@]}" <"$prompt_file") | tee "$capture"
  status="${PIPESTATUS[0]}"
  set -e
  note_session "$capture"
  rm -f "$capture"
  exit "$status"
fi

bin="$(command -v codex || true)"
[[ -n "$bin" ]] || { echo "codex is not on PATH" >&2; exit 127; }
require_flags "$bin" exec
# exec's own help lists the flags that must not be placed after a subcommand.
exec_help="$("$bin" exec --help 2>&1 || true)"
for flag in --sandbox --json --output-schema --cd --model; do
  if ! grep -q -F -- "$flag" <<<"$exec_help"; then
    echo "codex exec is missing $flag. Read 'codex exec --help' and update this script." >&2
    exit 3
  fi
done

last_message="$(mktemp "${TMPDIR:-/tmp}/local-agent-last.XXXXXX")"
echo "agent=codex model=${model:-default} effort=${effort:-default} mode=$mode bin=$bin last_message_file=$last_message" >&2

base=("$bin" exec --cd "$project" --sandbox "$([[ "$mode" == "review" ]] && printf '%s' read-only || printf '%s' workspace-write)" -c "approval_policy=\"never\"")
[[ -n "$effort" ]] && base+=(-c "model_reasoning_effort=\"${effort}\"")
if [[ "$mode" == "implement" ]]; then
  base+=(--approve-for-me)
fi
for dir in "${extra_dirs[@]}"; do
  base+=(--add-dir "$dir")
done

if [[ -n "$resume_id" ]]; then
  args=("${base[@]}" resume "$resume_id" --json -o "$last_message")
else
  args=("${base[@]}" --json -o "$last_message")
fi
[[ -n "$model" ]] && args+=(--model "$model")
if [[ -n "$schema_file" ]]; then
  args+=(--output-schema "$schema_file")
fi

capture="$(mktemp "${TMPDIR:-/tmp}/local-agent-out.XXXXXX")"
if [[ "$dry_run" -eq 1 ]]; then
  run_cmd "${args[@]}" - <"$prompt_file"
  rm -f "$capture" "$last_message"
  exit 0
fi
set +e
(cd "$project" && "${args[@]}" - <"$prompt_file") | tee "$capture"
status="${PIPESTATUS[0]}"
set -e
note_session "$capture"
rm -f "$capture"
exit "$status"
