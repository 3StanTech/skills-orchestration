#!/bin/sh
# Resolve the live Grok catalog and the efforts each model accepts.
#
# Two different authorities are merged here, because neither is complete alone:
#   * `grok models` — authoritative on WHICH models exist. Read-only, bills nothing,
#     hook-exempt. Its AUTH line has produced a false negative before; its CATALOG
#     has not. Never treat a bad auth line as grounds to drop Grok.
#   * ../data/grok-models.json — authoritative on WHAT EFFORTS each model accepts. This
#     cannot be probed: `grok --help` declares --reasoning-effort as free text and
#     enumerates nothing, so a bad tier only fails after the call is billed.
#
# A live model missing from the JSON is reported as `grok_unknown=<id>`. That is the
# future-proofing that matters: when a new Grok ships, the caller asks the user
# instead of guessing an effort menu for a model nobody has characterized.
#
# Output (stdout, parseable):
#   grok_default=<id>                  the CLI's current default
#   grok_available=<id,id,...>         every launchable id, default first
#   grok_efforts_<id>=<low,medium,...> per-model effort menu, one line per known id
#   grok_unknown=<id,id,...>           live ids with no effort record (omitted if none)
#   grok_baseline=<id>                 the previously-known-good id
#   grok_resolution=live|fallback      whether the catalog probe succeeded
#   grok_model=<id>                    DEPRECATED alias for grok_default; kept so
#                                      older callers keep working
#
# Never pass an alias like `grok-build-latest` — it is not launchable, and an
# unresolved alias also defeats the hook's verbatim auth-file comparison. Resolve,
# then pass the concrete id.

set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
catalog="$here/../data/grok-models.json"

usage() {
  echo "usage: resolve-grok-model.sh [--catalog FILE] [--quiet]"
}

quiet=no
while [ "$#" -gt 0 ]; do
  case "$1" in
    --catalog) catalog=$2; shift 2 ;;
    --quiet) quiet=yes; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

raw=""
if command -v grok >/dev/null 2>&1; then
  # Tolerate a non-zero exit and the spurious auth line; we only want the catalog.
  raw=$(grok models 2>/dev/null || true)
fi

CATALOG_FILE="$catalog" GROK_RAW="$raw" QUIET="$quiet" python3 <<'PY'
import json, os, re, sys

raw = os.environ.get("GROK_RAW", "")
catalog_path = os.environ.get("CATALOG_FILE", "")

known, baseline = {}, "grok-4.5"
try:
    with open(catalog_path, encoding="utf-8") as fh:
        data = json.load(fh)
    baseline = data.get("baseline", baseline)
    known = {k: v.get("efforts", []) for k, v in data.get("models", {}).items()}
except Exception as exc:
    print(f"grok_note=effort catalog unreadable ({exc}); menus must be confirmed with the user",
          file=sys.stderr)

default = ""
match = re.search(r"^\s*Default model:\s*(\S+)", raw, re.M)
if match:
    default = match.group(1).strip()

# Lines look like "  * grok-4.6 (default)" or "  - grok-4.5".
available = []
for line in raw.splitlines():
    hit = re.match(r"^\s*[-*]\s+(\S+)", line)
    if hit:
        model = hit.group(1).strip()
        if model not in available:
            available.append(model)

resolution = "live" if default or available else "fallback"
if resolution == "fallback":
    # Never drop Grok over a failed probe. Fall back to what we already know.
    default = baseline
    available = list(known.keys()) or [baseline]
    if os.environ.get("QUIET") != "yes":
        print("grok_note=could not resolve the live catalog; using the known set. "
              "Never drop Grok on this.", file=sys.stderr)

if default and default not in available:
    available.insert(0, default)
if default and available and available[0] != default:
    available.remove(default)
    available.insert(0, default)

unknown = [m for m in available if m not in known]

print(f"grok_default={default}")
print(f"grok_available={','.join(available)}")
for model in available:
    if model in known:
        print(f"grok_efforts_{model}={','.join(known[model])}")
if unknown:
    print(f"grok_unknown={','.join(unknown)}")
print(f"grok_baseline={baseline}")
print(f"grok_resolution={resolution}")
print(f"grok_model={default}")
PY
