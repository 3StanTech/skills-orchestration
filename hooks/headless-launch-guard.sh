#!/bin/bash
# PreToolUse/Bash: block raw codex/grok/claude -p launches that bypass the headless wrappers.
exec python3 "$HOME/.agents/hooks/headless-launch-guard.py"
