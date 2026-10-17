#!/bin/sh
# Read-only Codex doctor. Starts no model, bills nothing, decides nothing.
#
# A bad result here is NEVER grounds to skip, drop, or substitute Codex.
# Availability is the user's call: report what you saw in one line and let them
# decide. Never edit ~/.codex/auth.json — if auth is broken, ask the user to run
# `codex login`.

set -eu

echo "codex_check=begin"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex_path=missing"
  echo "codex_check=complete"
  exit 0
fi

echo "codex_path=$(command -v codex)"
echo "codex_version=$(codex --version 2>&1 | head -n 1)"

# These config values are what an UNFLAGGED run would inherit — the reason every
# delegated launch passes model and effort explicitly.
if [ -f "$HOME/.codex/config.toml" ]; then
  echo "codex_config_model=$(sed -n 's/^model *= *"\(.*\)"/\1/p' "$HOME/.codex/config.toml" | head -n 1)"
  echo "codex_config_effort=$(sed -n 's/^model_reasoning_effort *= *"\(.*\)"/\1/p' "$HOME/.codex/config.toml" | head -n 1)"
  echo "codex_config_service_tier=$(sed -n 's/^service_tier *= *"\(.*\)"/\1/p' "$HOME/.codex/config.toml" | head -n 1)"
else
  echo "codex_config=missing"
fi

if [ "${1:-}" = "--doctor" ]; then
  echo "codex_login_status=begin"
  codex login status 2>&1 | head -n 10 || echo "codex_login_status=failed"
  echo "codex_login_status=end"
  echo "codex_models=begin"
  codex debug models 2>&1 | head -n 40 || echo "codex_models=failed"
  echo "codex_models=end"
fi

echo "codex_check=complete"
