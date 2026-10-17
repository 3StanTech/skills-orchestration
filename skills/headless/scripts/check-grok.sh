#!/bin/sh
set -eu

grok_path="$(command -v grok || true)"
if [ -z "$grok_path" ]; then
  echo "ERROR: grok is not on PATH" >&2
  exit 1
fi

echo "grok_path=$grok_path"
grok --version

if [ "$#" -gt 0 ] && [ "$1" = "--doctor" ]; then
  exec grok mcp doctor
fi

echo "Auth and MCP status: run this script with --doctor or perform an approved read-only launch."
