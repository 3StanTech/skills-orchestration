#!/bin/sh
set -eu

wrapper=$(CDPATH= cd -- "$(dirname -- "$0")/../scripts" && pwd)/run-codex.sh
tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/headless-codex-test.XXXXXX")
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM

expect_fail() {
  if "$wrapper" --cwd "$tmpdir" "$@" --dry-run >/dev/null 2>&1; then
    echo "FAIL: expected rejection: $*" >&2
    exit 1
  fi
}

expect_fail --model gpt-5.5 --effort max --lane A --prompt test
expect_fail --model gpt-6-astra --lane A --prompt test
expect_fail --model gpt-6-astra --effort ultra --lane A

output=$("$wrapper" --cwd "$tmpdir" --model gpt-6-astra --effort ultra \
  --lane A --speed standard --prompt test --dry-run)
printf '%s' "$output" | grep -q 'service_tier=default'
printf '%s' "$output" | grep -q -- '--sandbox read-only'

output=$("$wrapper" --cwd "$tmpdir" --model gpt-6-astra --effort high \
  --lane B --speed fast --prompt test --dry-run)
printf '%s' "$output" | grep -q 'service_tier=priority'
printf '%s' "$output" | grep -q -- '--sandbox workspace-write'

echo "PASS: run-codex wrapper"
