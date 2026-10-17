#!/bin/sh
# WarFleet non-billing preflight. Reports what is on this machine. Decides nothing.
#
# ============================ HARD RULE ============================
# A PREFLIGHT RESULT NEVER REMOVES A FAMILY FROM THE MUSTER OR ROSTER.
# You do not get to decide a family is unavailable. If a check looks bad,
# put the full menu up anyway and tell the user what you saw in ONE line.
# A unit that later fails at launch is a casualty for the General, not a
# silent substitution. Dropping a family the user asked for is a
# dispatcher violation, and it has already happened once in a real run.
# ===================================================================
#
# Nothing here starts a model or bills anything.

set -eu

# -P resolves the physical path, so this also works through the ~/.claude symlinked scripts dir.
SKILL_ROOT=$(CDPATH= cd -P -- "$(dirname "$0")/.." && pwd)

echo "warfleet_preflight=begin"

if command -v claude >/dev/null 2>&1; then
  echo "claude_path=$(command -v claude)"
  echo "claude_version=$(claude --version 2>&1 | head -n 1)"
else
  echo "claude_path=missing"
fi

if command -v codex >/dev/null 2>&1; then
  echo "codex_path=$(command -v codex)"
  echo "codex_version=$(codex --version 2>&1 | head -n 1)"
else
  echo "codex_path=missing"
fi

if [ -x "$SKILL_ROOT/../headless/scripts/run-codex.sh" ]; then
  echo "headless_codex_wrapper=present"
else
  echo "headless_codex_wrapper=missing at $SKILL_ROOT/../headless/scripts/run-codex.sh"
fi

if [ -x "$SKILL_ROOT/../headless/scripts/run-claude.sh" ]; then
  echo "headless_claude_wrapper=present"
else
  echo "headless_claude_wrapper=missing at $SKILL_ROOT/../headless/scripts/run-claude.sh"
fi

if [ -x "$SKILL_ROOT/../headless/scripts/run-grok.sh" ]; then
  echo "headless_grok_wrapper=present"
else
  echo "headless_grok_wrapper=missing at $SKILL_ROOT/../headless/scripts/run-grok.sh"
fi

if command -v grok >/dev/null 2>&1; then
  echo "grok_path=$(command -v grok)"
  echo "grok_version=$(grok --version 2>&1 | head -n 1)"
  resolver="$SKILL_ROOT/../headless/scripts/resolve-grok-model.sh"
  if [ -x "$resolver" ]; then
    "$resolver" 2>/dev/null || echo "grok_model=unresolved"
  else
    echo "grok_model=unresolved; resolver missing at $resolver"
  fi
else
  echo "grok_path=missing"
fi

if [ -d "$HOME/.claude/warfleet" ]; then
  echo "warfleet_auth_dir=present"
else
  echo "warfleet_auth_dir=missing; create it before writing the auth file"
fi

echo "dispatcher_recommendation=run the dispatcher itself at low effort; it holds zero judgment"
echo "warfleet_preflight=complete"
