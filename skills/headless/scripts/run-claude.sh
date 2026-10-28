#!/bin/sh
set -eu

usage() {
  echo "usage: run-claude.sh --cwd DIR --model MODEL --effort low|medium|high|xhigh|max --speed standard|fast --lane A|B|C [--session UUID | --resume UUID] [--prompt-file FILE] [--chrome] [--output-format text|json|stream-json] [--max-budget-usd N] [--add-dir DIR] [--allow-tools RULES] [--settings FILE] [--approve-lane-c yes] [--auth FILE --task-id ID] [--dry-run]"
}

cwd=
model=
effort=
speed=
lane=
session=
resume=
prompt_file=
chrome=no
approve_lane_c=no
dry_run=no
auth=
task_id=
output_format=
max_budget=
add_dir=
allow_tools=
settings_file=
seen=" "

need_value() {
  [ "$#" -ge 2 ] && [ -n "$2" ] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
  case "$2" in --*) echo "ERROR: $1 requires a value, not another flag" >&2; exit 2 ;; esac
}

while [ "$#" -gt 0 ]; do
  key=$1
  [ "$key" != --session-id ] || key=--session
  case "$seen" in *" $key "*) echo "ERROR: duplicate argument: $key" >&2; exit 2 ;; esac
  seen="$seen$key "
  case "$1" in
    --cwd) need_value "$@"; cwd=$2; shift 2 ;;
    --model) need_value "$@"; model=$2; shift 2 ;;
    --effort) need_value "$@"; effort=$2; shift 2 ;;
    --speed) need_value "$@"; speed=$2; shift 2 ;;
    --lane) need_value "$@"; lane=$2; shift 2 ;;
    --session|--session-id) need_value "$@"; session=$2; shift 2 ;;
    --resume) need_value "$@"; resume=$2; shift 2 ;;
    --prompt-file) need_value "$@"; prompt_file=$2; shift 2 ;;
    --dry-run) dry_run=yes; shift ;;
    --auth) need_value "$@"; auth=$2; shift 2 ;;
    --task-id) need_value "$@"; task_id=$2; shift 2 ;;
    --chrome) chrome=yes; shift ;;
    --output-format) need_value "$@"; output_format=$2; shift 2 ;;
    --max-budget-usd) need_value "$@"; max_budget=$2; shift 2 ;;
    --add-dir) need_value "$@"; add_dir=$2; shift 2 ;;
    --allow-tools) need_value "$@"; allow_tools=$2; shift 2 ;;
    --settings) need_value "$@"; settings_file=$2; shift 2 ;;
    --approve-lane-c) need_value "$@"; approve_lane_c=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$cwd" ] || { echo "ERROR: --cwd is required" >&2; exit 2; }
[ -d "$cwd" ] || { echo "ERROR: workspace does not exist: $cwd" >&2; exit 2; }
[ -n "$model" ] || { echo "ERROR: explicit --model is required" >&2; exit 2; }
[ -n "$effort" ] || { echo "ERROR: explicit --effort is required" >&2; exit 2; }
case "$output_format" in ""|text|json|stream-json) ;; *) echo "ERROR: --output-format must be text, json or stream-json" >&2; exit 2 ;; esac
case "$max_budget" in ""|*[!0-9.]*) [ -z "$max_budget" ] || { echo "ERROR: --max-budget-usd must be a number" >&2; exit 2; } ;; esac
[ -z "$add_dir" ] || [ -d "$add_dir" ] || { echo "ERROR: --add-dir does not exist: $add_dir" >&2; exit 2; }
# --allow-tools: the plan's allowed checks as permission rules, e.g. "Bash(npx vitest run:*),Bash(npx tsc --noEmit)".
case "$allow_tools" in *"
"*) echo "ERROR: --allow-tools must be one line" >&2; exit 2 ;; esac
case "$speed" in standard|fast) ;; *) echo "ERROR: explicit --speed standard|fast is required" >&2; exit 2 ;; esac
# The catalog is the only model/effort/fast authority; never list models here.
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
verdict=$(CATALOG="$here/../data/claude-models.json" M="$model" E="$effort" S="$speed" python3 -c '
import json, os
spec = json.load(open(os.environ["CATALOG"]))["models"].get(os.environ["M"])
if spec is None:
    print("unknown")
elif os.environ["E"] not in spec.get("efforts", []):
    print("effort:" + " ".join(spec.get("efforts", [])))
elif os.environ["S"] == "fast" and not spec.get("fast"):
    print("nofast")
else:
    print("ok")
' 2>/dev/null) || verdict=unreadable
case "$verdict" in
  ok) ;;
  unknown) echo "ERROR: $model is not recorded in headless/data/claude-models.json; record its efforts and fast support at plan time first" >&2; exit 2 ;;
  effort:*) echo "ERROR: $model does not accept effort $effort; recorded: ${verdict#effort:}" >&2; exit 2 ;;
  nofast) echo "ERROR: --speed fast is not supported by $model" >&2; exit 2 ;;
  *) echo "ERROR: cannot read headless/data/claude-models.json" >&2; exit 2 ;;
esac
if [ "$speed" = fast ]; then fast_mode=true; else fast_mode=false; fi
# --settings FILE: a settings JSON object (e.g. hooks) merged into the one --settings value Claude
# receives; the wrapper's fastMode always wins so the tier's speed cannot be overridden.
settings="{\"fastMode\":$fast_mode}"
if [ -n "$settings_file" ]; then
  [ -f "$settings_file" ] && [ -r "$settings_file" ] || { echo "ERROR: --settings file is not readable: $settings_file" >&2; exit 2; }
  settings=$(F="$settings_file" FAST="$fast_mode" python3 -c '
import json, os, sys
data = json.load(open(os.environ["F"]))
if not isinstance(data, dict):
    sys.exit(1)
data["fastMode"] = os.environ["FAST"] == "true"
print(json.dumps(data, separators=(",", ":")))
' 2>/dev/null) || { echo "ERROR: --settings file must hold a JSON object: $settings_file" >&2; exit 2; }
fi
case "$lane" in
  A) permission_mode=plan; disallowed=yes ;;
  B) permission_mode=acceptEdits; disallowed=no ;;
  C) permission_mode=bypassPermissions; disallowed=no ;;
  *) echo "ERROR: explicit --lane A|B|C is required" >&2; exit 2 ;;
esac
if [ "$lane" = C ] && [ "$approve_lane_c" != yes ]; then
  echo "ERROR: lane C requires --approve-lane-c yes" >&2
  exit 2
fi
[ -z "$session" ] || [ -z "$resume" ] || { echo "ERROR: choose --session or --resume, not both" >&2; exit 2; }


# WarFleet roster check: a tagged launch must match its user-approved entry.
if [ -n "$auth" ] || [ -n "$task_id" ]; then
  [ -n "$auth" ] && [ -n "$task_id" ] || { echo "ERROR: --auth and --task-id go together" >&2; exit 2; }
  python3 "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/check-auth.py" --auth "$auth" --task-id "$task_id" \
    --model "$model" --effort "$effort" --speed "$speed" || exit 2
fi

# Buffer once outside the workspace to validate before launch without changing
# prompt bytes or putting private prompt text in argv. With --prompt-file, stdin is
# never read: a caller's stdin may be a pipe that never closes, which would block
# here before Claude starts (2026-10-05: a 40-minute silent stall).
prompt_buffer=$(mktemp "${TMPDIR:-/tmp}/headless-claude-prompt.XXXXXX")
trap 'rm -f "$prompt_buffer"' EXIT HUP INT TERM
if [ -n "$prompt_file" ]; then
  [ -f "$prompt_file" ] && [ -r "$prompt_file" ] || { echo "ERROR: prompt file is not readable" >&2; exit 2; }
  cat "$prompt_file" > "$prompt_buffer"
elif [ ! -t 0 ]; then
  cat > "$prompt_buffer"
fi
LC_ALL=C grep -q '[^[:space:]]' "$prompt_buffer" || { echo "ERROR: nonempty prompt file or stdin is required" >&2; exit 2; }

set -- --model "$model" --effort "$effort" --settings "$settings" --permission-mode "$permission_mode" --exclude-dynamic-system-prompt-sections
if [ "$disallowed" = yes ]; then set -- "$@" --disallowed-tools "Edit,Write,NotebookEdit"; fi
if [ "$lane" = C ]; then set -- "$@" --dangerously-skip-permissions; fi
if [ "$chrome" = yes ]; then set -- "$@" --chrome; fi
if [ -n "$output_format" ]; then set -- "$@" --output-format "$output_format"; fi
# claude -p rejects stream-json without --verbose.
if [ "$output_format" = stream-json ]; then set -- "$@" --verbose; fi
if [ -n "$max_budget" ]; then set -- "$@" --max-budget-usd "$max_budget"; fi
if [ -n "$add_dir" ]; then set -- "$@" --add-dir "$add_dir"; fi
if [ -n "$allow_tools" ] && [ "$lane" != C ]; then set -- "$@" --allowedTools "$allow_tools"; fi
if [ -n "$session" ]; then set -- "$@" --session-id "$session"; fi
if [ -n "$resume" ]; then set -- "$@" --resume "$resume"; fi
set -- "$@" -p

if [ "$dry_run" = yes ]; then
  printf 'cwd=%s\n' "$cwd"
  printf '%s\n' claude "$@"
  echo 'prompt_transport=stdin (validated; content omitted)'
  exit 0
fi
command -v claude >/dev/null 2>&1 || { echo "ERROR: claude is not on PATH" >&2; exit 1; }
cd "$cwd"
# Keep input literal; do not interpolate it into shell code or expose it in argv.
claude "$@" < "$prompt_buffer"
