#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
  echo "usage: run-grok.sh --cwd DIR --lane A|B|C --model ID --effort LEVEL [--session UUID | --resume UUID] (--prompt-file FILE | --prompt-json JSON | --prompt TEXT) [--json-schema JSON] [--max-turns N] [--approve-lane-c yes] [--auth FILE --task-id ID] [--log FILE] [--dry-run]"
}

model=
effort=
cwd=
lane=
session=
resume=
prompt_file=
prompt_json=
prompt=
json_schema=
max_turns=
approve_lane_c=no
log_file=
dry_run=no
auth=
task_id=
prompt_sources=0
seen=" "

need_value() {
  [ "$#" -ge 2 ] && [ -n "$2" ] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
}

while [ "$#" -gt 0 ]; do
  key=$1
  case "$key" in --session-id) key=--session ;; --reasoning-effort) key=--effort ;; esac
  case "$seen" in *" $key "*) echo "ERROR: duplicate argument: $key" >&2; exit 2 ;; esac
  seen="$seen$key "
  case "$1" in
    --cwd) need_value "$@"; cwd=$2; shift 2 ;;
    --effort|--reasoning-effort) need_value "$@"; effort=$2; shift 2 ;;
    --lane) need_value "$@"; lane=$2; shift 2 ;;
    --sandbox)
      echo "ERROR: --sandbox is an internal Grok flag; use the public --lane A|B|C interface" >&2
      exit 2
      ;;
    --no-memory|--verbatim)
      echo "ERROR: $1 is injected by run-grok.sh; callers must not pass it" >&2
      exit 2
      ;;
    --session|--session-id) need_value "$@"; session=$2; shift 2 ;;
    --resume) need_value "$@"; resume=$2; shift 2 ;;
    --prompt-file) need_value "$@"; prompt_sources=$((prompt_sources + 1)); prompt_file=$2; shift 2 ;;
    --prompt-json) need_value "$@"; prompt_sources=$((prompt_sources + 1)); prompt_json=$2; shift 2 ;;
    --prompt) need_value "$@"; prompt_sources=$((prompt_sources + 1)); prompt=$2; shift 2 ;;
    --json-schema) need_value "$@"; json_schema=$2; shift 2 ;;
    --max-turns) need_value "$@"; max_turns=$2; shift 2 ;;
    --model) need_value "$@"; model=$2; shift 2 ;;
    --approve-lane-c) need_value "$@"; approve_lane_c=$2; shift 2 ;;
    --log) need_value "$@"; log_file=$2; shift 2 ;;
    --dry-run) dry_run=yes; shift ;;
    --auth) need_value "$@"; auth=$2; shift 2 ;;
    --task-id) need_value "$@"; task_id=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$cwd" ] || { echo "ERROR: --cwd is required" >&2; exit 2; }
[ -d "$cwd" ] || { echo "ERROR: workspace does not exist: $cwd" >&2; exit 2; }
case "$lane" in
  A) sandbox=read-only ;;
  B) sandbox=workspace ;;
  C) sandbox=off ;;
  "") echo "ERROR: explicit --lane A|B|C is required" >&2; exit 2 ;;
  *) echo "ERROR: --lane must be A, B, or C" >&2; exit 2 ;;
esac
case "$lane" in
  C)
    [ "$approve_lane_c" = yes ] || { echo "ERROR: lane C requires --approve-lane-c yes" >&2; exit 2; }
    ;;
esac
[ -z "$session" ] || [ -z "$resume" ] || { echo "ERROR: choose --session or --resume, not both" >&2; exit 2; }
[ "$prompt_sources" -eq 1 ] || { echo "ERROR: choose exactly one prompt source" >&2; exit 2; }

# Discovery may populate a menu, but may never choose a launch tier for the user.
[ -n "$model" ] || { echo "ERROR: explicit --model is required" >&2; exit 2; }

# Effort is required and validated against THIS model's set: grok-4.6 accepts xhigh,
# grok-4.5 does not, and the CLI enumerates neither — a bad tier fails only once billed.
[ -n "$effort" ] || { echo "ERROR: explicit --effort is required" >&2; exit 2; }
allowed=$(CATALOG="$here/../data/grok-models.json" M="$model" python3 -c '
import json, os, sys
try:
    data = json.load(open(os.environ["CATALOG"], encoding="utf-8"))
except Exception:
    sys.exit(0)
spec = data.get("models", {}).get(os.environ["M"])
if spec is not None:
    print(",".join(spec.get("efforts", [])))
' 2>/dev/null || true)
[ -n "$allowed" ] || { echo "ERROR: $model has no recorded effort set; add it to headless/data/grok-models.json" >&2; exit 2; }
case ",$allowed," in
  *",$effort,"*) ;;
  *) echo "ERROR: $model does not accept effort '$effort'; supported: $allowed" >&2; exit 2 ;;
esac


# WarFleet roster check: a tagged launch must match its user-approved entry.
if [ -n "$auth" ] || [ -n "$task_id" ]; then
  [ -n "$auth" ] && [ -n "$task_id" ] || { echo "ERROR: --auth and --task-id go together" >&2; exit 2; }
  python3 "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/check-auth.py" --auth "$auth" --task-id "$task_id" \
    --model "$model" --effort "$effort" --speed "standard" || exit 2
fi

[ -n "$prompt_file" ] || [ -n "$prompt_json" ] || [ -n "$prompt" ] || {
  echo "ERROR: one of --prompt-file, --prompt-json, or --prompt is required" >&2
  usage >&2
  exit 2
}

if [ -n "$prompt_file" ]; then
  [ -f "$prompt_file" ] && [ -r "$prompt_file" ] || { echo "ERROR: prompt file is not readable" >&2; exit 2; }
  LC_ALL=C grep -q '[^[:space:]]' "$prompt_file" || { echo "ERROR: prompt file is empty" >&2; exit 2; }
fi
if [ -n "$prompt" ]; then
  printf '%s' "$prompt" | LC_ALL=C grep -q '[^[:space:]]' || { echo "ERROR: prompt is empty" >&2; exit 2; }
fi
if [ -n "$prompt_json" ]; then
  printf '%s' "$prompt_json" | python3 -c 'import json,sys; v=json.load(sys.stdin); sys.exit(0 if isinstance(v,list) and v else 2)' || {
    echo "ERROR: prompt JSON must be a nonempty content-block list" >&2; exit 2;
  }
fi
if [ -n "$max_turns" ]; then
  case "$max_turns" in *[!0-9]*|0) echo "ERROR: max-turns must be a positive integer" >&2; exit 2 ;; esac
fi

# Output text cannot establish that a provider has not started task work. Keep
# one attempt and its original status/log; recovery belongs to the dispatcher
# after independent pre-work evidence. Never infer permission escalation from prose.
if [ -n "$log_file" ]; then
  attempt_file=$log_file
else
  attempt_file=$(mktemp "${TMPDIR:-/tmp}/headless-grok-attempt.XXXXXX")
fi
echo "headless_log=$attempt_file" >&2

if [ "$dry_run" = yes ]; then
  printf 'grok --cwd %s -m %s --effort %s --sandbox %s --permission-mode bypassPermissions --no-memory --verbatim' "$cwd" "$model" "$effort" "$sandbox"
  [ -z "$session" ] || printf ' --session-id %s' "$session"
  [ -z "$resume" ] || printf ' --resume %s' "$resume"
  [ -z "$prompt_file" ] || printf ' --prompt-file %s' "$prompt_file"
  [ -z "$prompt_json" ] || printf ' --prompt-json %s' "$prompt_json"
  [ -z "$prompt" ] || printf ' --single %s' "$prompt"
  printf '\n'
  exit 0
fi

command -v grok >/dev/null 2>&1 || { echo "ERROR: grok is not on PATH" >&2; exit 1; }

run_attempt() {
  attempt_sandbox=$1
  shift
  set -- -m "$model" --effort "$effort" --sandbox "$attempt_sandbox" \
    --permission-mode bypassPermissions --no-memory --verbatim
  if [ -n "$session" ]; then set -- "$@" --session-id "$session"; fi
  if [ -n "$resume" ]; then set -- "$@" --resume "$resume"; fi
  if [ -n "$max_turns" ]; then set -- "$@" --max-turns "$max_turns"; fi
  if [ -n "$json_schema" ]; then set -- "$@" --json-schema "$json_schema"; fi
  if [ -n "$prompt_file" ]; then set -- "$@" --prompt-file "$prompt_file"; fi
  if [ -n "$prompt_json" ]; then set -- "$@" --prompt-json "$prompt_json"; fi
  if [ -n "$prompt" ]; then set -- "$@" --single "$prompt"; fi
  grok --cwd "$cwd" "$@" >"$attempt_file" 2>&1
}

if run_attempt "$sandbox"; then
  status=0
else
  status=$?
fi
cat "$attempt_file"

exit "$status"
