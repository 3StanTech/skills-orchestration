#!/bin/sh
set -eu

claude_path="$(command -v claude || true)"
if [ -z "$claude_path" ]; then
  echo "ERROR: claude is not on PATH" >&2
  exit 1
fi

echo "claude_path=$claude_path"
claude --version

if [ "$#" -gt 0 ] && [ "$1" = "--auth" ]; then
  exec claude auth status
fi

echo "Authentication status: run this script with --auth; this does not modify credentials."
