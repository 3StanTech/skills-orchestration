#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT

cat > "$temp_dir/grok" <<'EOF'
#!/bin/sh
printf '%s\n' "$@"
EOF
chmod +x "$temp_dir/grok"
PATH="$temp_dir:$PATH"
export PATH

output=$(PATH="$temp_dir:$PATH" "$root/scripts/run-grok.sh" --cwd "$temp_dir" --lane A --model grok-4.6 --effort high --prompt test)
printf '%s\n' "$output" | grep -Fx -- '-m' >/dev/null
# A CONCRETE id, never the `grok-build-latest` alias: that alias is not launchable
# (`grok models` lists only concrete ids), so passing it failed at launch.
printf '%s\n' "$output" | grep -Fx -- 'grok-build-latest' >/dev/null && {
  echo "run-grok.sh must resolve a concrete model id, not pass the alias" >&2
  exit 1
}
printf '%s\n' "$output" | grep -Eqx -- 'grok-[0-9][A-Za-z0-9.\-]*'
printf '%s\n' "$output" | grep -Fx -- '--effort' >/dev/null
printf '%s\n' "$output" | grep -Fx -- 'high' >/dev/null
printf '%s\n' "$output" | grep -Fx -- '--sandbox' >/dev/null
printf '%s\n' "$output" | grep -Fx -- 'read-only' >/dev/null
printf '%s\n' "$output" | grep -Fx -- '--no-memory' >/dev/null
printf '%s\n' "$output" | grep -Fx -- '--verbatim' >/dev/null

# The internal sandbox flag and wrapper-owned flags are not caller interfaces.
if "$root/scripts/run-grok.sh" --cwd "$temp_dir" --sandbox read-only --effort high --prompt test \
  >"$temp_dir/out" 2>"$temp_dir/err"; then
  echo "expected --sandbox to fail" >&2
  exit 1
fi
grep -F 'use the public --lane A|B|C interface' "$temp_dir/err" >/dev/null

for owned in --no-memory --verbatim; do
  if "$root/scripts/run-grok.sh" --cwd "$temp_dir" --lane A --effort high --prompt test "$owned" \
    >"$temp_dir/out" 2>"$temp_dir/err"; then
    echo "expected caller-owned flag to fail: $owned" >&2
    exit 1
  fi
  grep -F 'injected by run-grok.sh' "$temp_dir/err" >/dev/null
done

if "$root/scripts/run-grok.sh" --cwd "$temp_dir" --lane >"$temp_dir/out" 2>"$temp_dir/err"; then
  echo "expected a missing lane value to fail" >&2
  exit 1
fi
grep -F -- '--lane requires a value' "$temp_dir/err" >/dev/null

# A/B/C always expose the same canonical lane interface, while Grok receives the
# corresponding internal sandbox value.
for lane_and_sandbox in 'B workspace' 'C off'; do
  lane=${lane_and_sandbox%% *}
  sandbox=${lane_and_sandbox#* }
  extra=
  [ "$lane" = C ] && extra='--approve-lane-c yes'
  mapped=$(PATH="$temp_dir:$PATH" "$root/scripts/run-grok.sh" --cwd "$temp_dir" --lane "$lane" \
    --model grok-4.6 --effort high --prompt test $extra)
  printf '%s\n' "$mapped" | grep -Fx -- '--sandbox' >/dev/null
  printf '%s\n' "$mapped" | grep -Fx -- "$sandbox" >/dev/null
done

# An omitted model fails before even probing the model executable.
if PATH="$temp_dir:$PATH" "$root/scripts/run-grok.sh" --cwd "$temp_dir" --lane A --effort high --prompt test >"$temp_dir/out" 2>"$temp_dir/err"; then
  echo "expected a missing model to fail" >&2
  exit 1
fi
grep -F 'explicit --model is required' "$temp_dir/err" >/dev/null

# grok-4.5 has no xhigh tier; the wrapper must refuse rather than let it fail once billed.
if "$root/scripts/run-grok.sh" --cwd "$temp_dir" --model grok-4.5 --effort xhigh --lane A --prompt test >"$temp_dir/out" 2>"$temp_dir/err"; then
  echo "expected an unsupported tier to fail" >&2
  exit 1
fi
grep -F 'does not accept effort' "$temp_dir/err" >/dev/null

# Effort is required, never defaulted.
if "$root/scripts/run-grok.sh" --cwd "$temp_dir" --lane A --model grok-4.6 --prompt test >"$temp_dir/out" 2>"$temp_dir/err"; then
  echo "expected a missing effort to fail" >&2
  exit 1
fi
grep -F 'explicit --effort is required' "$temp_dir/err" >/dev/null

# Error prose is not a pre-work signal. Even an exact historical initialization
# error must preserve the original failure and execute only once.
cat > "$temp_dir/grok" <<'EOF'
#!/bin/sh
echo attempt >> "$GROK_RETRY_LOG"
echo "could not apply the 'workspace' sandbox profile: Operation not permitted" >&2
exit 43
EOF
chmod +x "$temp_dir/grok"
status=0
GROK_RETRY_LOG="$temp_dir/retry-log" "$root/scripts/run-grok.sh" \
  --cwd "$temp_dir" --lane B --model grok-4.6 --effort high --prompt test \
  >"$temp_dir/out" 2>"$temp_dir/err" || status=$?
[ "$status" -eq 43 ]
[ "$(wc -l < "$temp_dir/retry-log" | tr -d ' ')" -eq 1 ]
if grep -q 'RETRY:' "$temp_dir/err"; then exit 1; fi

echo "PASS: run-grok wrapper"
