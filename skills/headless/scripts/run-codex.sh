#!/bin/sh
# Launch one Codex (GPT) unit with model, effort, speed, lane, and prompt transport
# all explicit and auditable.
#
# Direct CLI is used for every lane to pin both sandbox and service tier.
# The companion cannot pin standard/fast, so it is not a compatible launch path.
# Disable the configured app-owned node_repl server for headless execution.
#
# The headless launch guard allows this wrapper by name and blocks raw `codex exec`.
# Tier and WarFleet roster checks live here. Do not rename it without updating
# ~/.agents/hooks/headless-launch-guard.py.

set -eu

usage() {
  cat <<'EOF'
usage: run-codex.sh --cwd DIR --model ID --effort LEVEL --lane A|B|C
                    [--speed standard|fast] [--out FILE]
                    [--prompt-file FILE | --prompt TEXT]
                    [--resume ID] [--output-schema FILE] [--add-dir DIR]
                    [--image FILE] [--profile NAME] [--ephemeral]
                    [--review] [--review-base BRANCH | --review-commit SHA | --review-uncommitted]
                    [--approve-lane-c yes] [--auth FILE --task-id ID]
                    [--force-direct] [--dry-run]

  Models and efforts are validated against `codex debug models --bundled` for
  the installed CLI. User menus remain policy-owned and must not expose internal
  or routing aliases merely because they appear in that catalog. Models below
  the GPT-5.5 family remain disallowed by local policy.

  There is no --session: `codex exec` has no such flag. A new thread's id is
  discovered from the run log afterwards; continue an existing one with --resume.

  Lanes:  A = read-only        (investigate)
          B = workspace-write  (edit inside the working directory)
          C = danger-full-access (network, dev servers, /tmp, installs)

  Select lanes from verified task/host needs. Runtime containment and network
  access require route-specific verification. Lane C requires --approve-lane-c yes.
EOF
}

cwd=
model=
effort=
lane=
speed=standard
out=
prompt_file=
prompt=
resume=
add_dir=
output_schema=
image=
profile=
ephemeral=no
review=no
review_scope=
review_value=
review_selectors=0
approve_lane_c=no
force_direct=no
dry_run=no
auth=
task_id=

seen=" "
need_value() {
  [ "$#" -ge 2 ] && [ -n "$2" ] || { echo "ERROR: $1 requires a value" >&2; exit 2; }
  case "$2" in --*) echo "ERROR: $1 requires a value, not another flag" >&2; exit 2 ;; esac
}

while [ "$#" -gt 0 ]; do
  case "$seen" in *" $1 "*) echo "ERROR: duplicate argument: $1" >&2; exit 2 ;; esac
  seen="$seen$1 "
  case "$1" in
    --cwd) need_value "$@"; cwd=$2; shift 2 ;;
    --model) need_value "$@"; model=$2; shift 2 ;;
    --effort) need_value "$@"; effort=$2; shift 2 ;;
    --lane) need_value "$@"; lane=$2; shift 2 ;;
    --speed) need_value "$@"; speed=$2; shift 2 ;;
    --out) need_value "$@"; out=$2; shift 2 ;;
    --prompt-file) need_value "$@"; prompt_file=$2; shift 2 ;;
    --prompt) need_value "$@"; prompt=$2; shift 2 ;;
    --resume) need_value "$@"; resume=$2; shift 2 ;;
    --add-dir) need_value "$@"; add_dir=$2; shift 2 ;;
    --output-schema) need_value "$@"; output_schema=$2; shift 2 ;;
    --image) need_value "$@"; image=$2; shift 2 ;;
    --profile) need_value "$@"; profile=$2; shift 2 ;;
    --ephemeral) ephemeral=yes; shift ;;
    --review) review=yes; shift ;;
    --review-base) review_selectors=$((review_selectors + 1)); need_value "$@"; review=yes; review_scope=--base; review_value=$2; shift 2 ;;
    --review-commit) review_selectors=$((review_selectors + 1)); need_value "$@"; review=yes; review_scope=--commit; review_value=$2; shift 2 ;;
    --review-uncommitted) review_selectors=$((review_selectors + 1)); review=yes; review_scope="--uncommitted"; shift ;;
    --approve-lane-c) need_value "$@"; approve_lane_c=$2; shift 2 ;;
    --force-direct) force_direct=yes; shift ;;
    --dry-run) dry_run=yes; shift ;;
    --auth) need_value "$@"; auth=$2; shift 2 ;;
    --task-id) need_value "$@"; task_id=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ "$review_selectors" -le 1 ] || { echo "ERROR: choose one review scope" >&2; exit 2; }
[ -n "$cwd" ] || { echo "ERROR: --cwd is required" >&2; exit 2; }
[ -d "$cwd" ] || { echo "ERROR: workspace does not exist: $cwd" >&2; exit 2; }

# Full ids only. Validate the exact model/effort pair against the installed CLI's
# bundled catalog rather than a frozen global effort list.
[ -n "$model" ] || { echo "ERROR: explicit --model is required" >&2; exit 2; }
[ -n "$effort" ] || { echo "ERROR: explicit --effort is required" >&2; exit 2; }
case "$model" in
  gpt-6-*|gpt-6.*-*|gpt-5.6-*|gpt-5.5) ;;
  *) echo "ERROR: model is outside the approved GPT-5.5-or-newer families: $model" >&2; exit 2 ;;
esac
command -v codex >/dev/null 2>&1 || { echo "ERROR: codex is not on PATH" >&2; exit 1; }
if ! codex debug models --bundled 2>/dev/null | MODEL="$model" EFFORT="$effort" python3 -c '
import json, os, sys
try:
    data = json.load(sys.stdin)
    model = next((m for m in data.get("models", []) if m.get("slug") == os.environ["MODEL"]), None)
    levels = [v.get("effort") for v in model.get("supported_reasoning_levels", [])] if model else []
except (ValueError, TypeError, AttributeError):
    levels = []
if os.environ["EFFORT"] not in levels:
    print("ERROR: unsupported model/effort pair or unavailable installed catalog: " +
          os.environ["MODEL"] + "/" + os.environ["EFFORT"], file=sys.stderr)
    sys.exit(2)
'; then
  exit 2
fi

case "$lane" in
  A) sandbox=read-only ;;
  B) sandbox=workspace-write ;;
  C)
    sandbox=danger-full-access
    [ "$approve_lane_c" = yes ] || { echo "ERROR: lane C requires --approve-lane-c yes" >&2; exit 2; }
    ;;
  *) echo "ERROR: explicit --lane A|B|C is required" >&2; exit 2 ;;
esac

case "$speed" in
  standard|fast) ;;
  *) echo "ERROR: --speed must be standard or fast" >&2; exit 2 ;;
esac


# WarFleet roster check: a tagged launch must match its user-approved entry.
if [ -n "$auth" ] || [ -n "$task_id" ]; then
  [ -n "$auth" ] && [ -n "$task_id" ] || { echo "ERROR: --auth and --task-id go together" >&2; exit 2; }
  python3 "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/check-auth.py" --auth "$auth" --task-id "$task_id" \
    --model "$model" --effort "$effort" --speed "$speed" || exit 2
fi

[ -z "$prompt_file" ] || [ -z "$prompt" ] || { echo "ERROR: choose --prompt-file or --prompt, not both" >&2; exit 2; }
[ -z "$prompt_file" ] || { [ -f "$prompt_file" ] && [ -r "$prompt_file" ]; } || { echo "ERROR: prompt file not found: $prompt_file" >&2; exit 2; }
if [ "$review" = no ] && [ -z "$prompt_file" ] && [ -z "$prompt" ]; then
  echo "ERROR: one of --prompt-file or --prompt is required" >&2; usage >&2; exit 2
fi

if [ -n "$prompt_file" ]; then
  LC_ALL=C grep -q '[^[:space:]]' "$prompt_file" || { echo "ERROR: prompt file is empty" >&2; exit 2; }
fi
if [ -n "$prompt" ]; then
  printf '%s' "$prompt" | LC_ALL=C grep -q '[^[:space:]]' || { echo "ERROR: prompt is empty" >&2; exit 2; }
fi
[ "$review" = no ] || [ -z "$resume" ] || { echo "ERROR: choose review or resume" >&2; exit 2; }
if [ "$review" = yes ] || [ -n "$resume" ]; then
  [ -z "$add_dir" ] && [ -z "$profile" ] || { echo "ERROR: add-dir/profile are not supported for resume or review" >&2; exit 2; }
fi
[ "$review" = no ] || [ -z "$image" ] || { echo "ERROR: image is not supported for review" >&2; exit 2; }

# Direct CLI pins both sandbox and service tier. --force-direct is retained as
# a compatibility no-op for existing callers.
direct=yes
reason="explicit sandbox and service tier"

if [ -z "$out" ]; then
  if [ "$dry_run" = yes ]; then
    out="${TMPDIR:-/tmp}/headless-codex-output.<unique>/last.md"
  else
    out_dir=$(mktemp -d "${TMPDIR:-/tmp}/headless-codex-output.XXXXXX")
    out="$out_dir/last.md"
  fi
fi
echo "codex_output=$out" >&2

emit() {
  if [ "$dry_run" = yes ]; then
    printf '%s\n' "$*"
    exit 0
  fi
}

if [ "$direct" = yes ]; then
  [ -z "$reason" ] || echo "codex_path=direct ($reason)" >&2
  command -v codex >/dev/null 2>&1 || { echo "ERROR: codex is not on PATH" >&2; exit 1; }

  if [ "$review" = yes ]; then
    # `codex exec review` accepts a NARROWER flag set than `codex exec`: no -C, no
    # --sandbox, no -p, no -i. Every flag therefore goes after the subcommand, and
    # the working directory is set with cd instead of -C.
    set -- exec review
    [ -z "$review_scope" ] || set -- "$@" "$review_scope"
    [ -z "$review_value" ] || set -- "$@" "$review_value"
    set -- "$@" -m "$model" -c model_reasoning_effort="$effort" \
           -c sandbox_mode="$sandbox" \
           -c mcp_servers.node_repl.enabled=false --skip-git-repo-check
    if [ "$speed" = fast ]; then set -- "$@" -c service_tier="priority"; else set -- "$@" -c service_tier="default"; fi
    [ "$ephemeral" = no ] || set -- "$@" --ephemeral
    [ -z "$output_schema" ] || set -- "$@" --output-schema "$output_schema"
    set -- "$@" -o "$out"

    cd "$cwd"
    if [ -n "$prompt_file" ]; then
      emit "cd $cwd && codex $* - < $prompt_file"
      exec codex "$@" - < "$prompt_file"
    elif [ -n "$prompt" ]; then
      emit "cd $cwd && codex $* $prompt"
      exec codex "$@" "$prompt"
    else
      emit "cd $cwd && codex $*"
      exec codex "$@"
    fi
  fi

  if [ -n "$resume" ]; then
    # `codex exec resume` also takes a narrower flag set: no -C, no --sandbox, no -p.
    # The lane is therefore pinned through the config key instead of the flag, which
    # matters here more than anywhere — this user's ~/.codex/config.toml sets
    # sandbox_mode = "danger-full-access", so an unpinned resume would inherit FULL
    # ACCESS regardless of the lane the roster approved.
    set -- exec resume "$resume" \
           -m "$model" -c model_reasoning_effort="$effort" \
           -c sandbox_mode="$sandbox" \
           -c mcp_servers.node_repl.enabled=false --skip-git-repo-check
    if [ "$speed" = fast ]; then set -- "$@" -c service_tier="priority"; else set -- "$@" -c service_tier="default"; fi
    [ "$ephemeral" = no ] || set -- "$@" --ephemeral
    [ -z "$output_schema" ] || set -- "$@" --output-schema "$output_schema"
    [ -z "$image" ] || set -- "$@" -i "$image"
    set -- "$@" -o "$out"
    cd "$cwd"
  else
    set -- exec -C "$cwd" --sandbox "$sandbox" --skip-git-repo-check \
           -m "$model" -c model_reasoning_effort="$effort" \
           -c mcp_servers.node_repl.enabled=false
    # --add-dir exists on `codex exec` only; resume and review reject it.
    [ -z "$add_dir" ] || set -- "$@" --add-dir "$add_dir"
    if [ "$speed" = fast ]; then set -- "$@" -c service_tier="priority"; else set -- "$@" -c service_tier="default"; fi
    [ -z "$profile" ] || set -- "$@" -p "$profile"
    [ "$ephemeral" = no ] || set -- "$@" --ephemeral
    [ -z "$output_schema" ] || set -- "$@" --output-schema "$output_schema"
    [ -z "$image" ] || set -- "$@" -i "$image"
    set -- "$@" -o "$out"
  fi

  if [ -n "$prompt_file" ]; then
    emit "codex $* - < $prompt_file"
    exec codex "$@" - < "$prompt_file"
  elif [ -n "$prompt" ]; then
    emit "codex $* $prompt"
    exec codex "$@" "$prompt"
  else
    emit "codex $*"
    exec codex "$@"
  fi
fi

