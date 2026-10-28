#!/bin/sh
# install.sh — link this bundle into the flat layout every host reads.
#
# Usage: install.sh [--check]
#   skills/<name>/ (with SKILL.md) -> $HOME/.agents/skills/<name>   (Codex and Grok read this)
#                                  -> <host>/skills/<name> for each installed host (its config
#                                     folder exists): ~/.claude, ~/.hermes, ~/.pi/agent; the
#                                     skills subfolder is created when missing
#   hooks/<file> (not test_*)      -> $HOME/.agents/hooks/<file>
#   scripts/<file>                 -> $HOME/.agents/scripts/<file>
#   skills/headless/data/families.example.json -> families.json beside it, only if missing
#     (per-user family availability; set a family you cannot use to active:false + reason)
# Never replaces a real file or folder, or a link pointing elsewhere: reported as conflict.
# A host link that already resolves to the same skill counts as installed.
# Idempotent. Re-run after installing a new host.
#   --check  change nothing; print `bundlelink<TAB><bundle><TAB><missing|conflict|broken> <dest>`
#            per finding; exit 1 if any.
# Exit 0 ok, 1 findings/conflicts, 2 bad usage.
set -u

check=0
case "${1:-}" in
  "") ;;
  --check) check=1 ;;
  *) echo "usage: install.sh [--check]" >&2; exit 2 ;;
esac
[ $# -le 1 ] || { echo "usage: install.sh [--check]" >&2; exit 2; }

BUNDLE=$(CDPATH= cd -P -- "$(dirname "$0")" && pwd)
name=$(basename "$BUNDLE")
linked=0 ok=0 bad=0

report() { printf 'bundlelink\t%s\t%s %s\n' "$name" "$1" "$2"; bad=$((bad + 1)); }
fail() { echo "install.sh: $1 failed: $2" >&2; bad=$((bad + 1)); }

# Collapse . and .. textually; print the absolute path.
normalize() {
  NORM_PATH="$1" awk 'BEGIN {
    p = ENVIRON["NORM_PATH"]; n = split(p, a, "/"); m = 0
    for (i = 1; i <= n; i++) {
      if (a[i] == "" || a[i] == ".") continue
      if (a[i] == "..") { if (m > 0) m--; continue }
      s[++m] = a[i]
    }
    out = ""; for (i = 1; i <= m; i++) out = out "/" s[i]
    print out
  }'
}

# A broken link is ours only if its normalized absolute target stays under $BUNDLE.
owned() {
  case "$1" in /*) ;; *) return 1 ;; esac
  case "$(normalize "$1")" in "$BUNDLE"/*) return 0 ;; *) return 1 ;; esac
}

link_one() {
  src=$1 dest=$2
  if [ -L "$dest" ]; then
    cur=$(readlink "$dest")
    if [ "$cur" = "$src" ]; then ok=$((ok + 1)); return; fi
    if [ -e "$dest" ]; then report conflict "$dest"; return; fi
    if ! owned "$cur" || [ "$check" -eq 1 ]; then report broken "$dest"; return; fi
    rm -f "$dest" || { fail rm "$dest"; return; }
  elif [ -e "$dest" ]; then
    report conflict "$dest"; return
  elif [ "$check" -eq 1 ]; then
    report missing "$dest"; return
  fi
  if ln -s "$src" "$dest"; then linked=$((linked + 1)); else fail ln "$dest"; fi
}

if [ "$check" -eq 0 ]; then
  mkdir -p "$HOME/.agents/skills" "$HOME/.agents/hooks" "$HOME/.agents/scripts" \
    || fail mkdir "$HOME/.agents/{skills,hooks,scripts}"
fi

for d in "$BUNDLE"/skills/*/; do
  [ -f "$d/SKILL.md" ] || continue
  n=$(basename "$d")
  link_one "$BUNDLE/skills/$n" "$HOME/.agents/skills/$n"
done
# Host folders: an existing link that resolves to the same skill is fine (e.g. relative links).
link_host() {
  src=$1 dest=$2
  if [ -L "$dest" ] && [ -e "$dest" ]; then
    if [ "$(CDPATH= cd -P -- "$dest" 2>/dev/null && pwd)" = "$(CDPATH= cd -P -- "$src" && pwd)" ]; then
      ok=$((ok + 1)); return
    fi
    report conflict "$dest"; return
  fi
  link_one "$src" "$dest"
}

for conf in "$HOME/.claude" "$HOME/.hermes" "$HOME/.pi/agent"; do
  [ -d "$conf" ] || continue
  host="$conf/skills"
  if [ ! -d "$host" ]; then
    if [ "$check" -eq 1 ]; then report missing "$host"; continue; fi
    mkdir -p "$host" || { fail mkdir "$host"; continue; }
  fi
  for d in "$BUNDLE"/skills/*/; do
    [ -f "$d/SKILL.md" ] || continue
    n=$(basename "$d")
    link_host "$BUNDLE/skills/$n" "$host/$n"
  done
done

for f in "$BUNDLE"/hooks/*; do
  [ -f "$f" ] || continue
  n=$(basename "$f")
  case "$n" in test_*) continue ;; esac
  link_one "$BUNDLE/hooks/$n" "$HOME/.agents/hooks/$n"
done
for f in "$BUNDLE"/scripts/*; do
  [ -f "$f" ] || continue
  n=$(basename "$f")
  link_one "$BUNDLE/scripts/$n" "$HOME/.agents/scripts/$n"
done

example="$BUNDLE/skills/headless/data/families.example.json"
families="$BUNDLE/skills/headless/data/families.json"
if [ -f "$example" ] && [ ! -e "$families" ]; then
  if [ "$check" -eq 1 ]; then
    report missing "$families"
  elif cp "$example" "$families"; then
    echo "created $families (every family on: set active:false + reason for any you cannot use)"
  else
    fail cp "$families"
  fi
fi

[ "$check" -eq 1 ] || echo "linked=$linked ok=$ok conflict=$bad"
[ "$bad" -eq 0 ]
