#!/usr/bin/env python3
"""Verify one headless launch against a WarFleet session auth file.

Called by every run-*.sh wrapper when --auth/--task-id are passed. The auth file
(~/.claude/warfleet/auth-<session-id>.json) lists the tasks the user approved at
plan time with their exact tier. A launch whose model, effort or speed differs
from its approved entry is refused; it never edits the auth file.

Usage: check-auth.py --auth FILE --task-id ID --model ID --effort LEVEL [--speed S]
Exit 0 = approved, 2 = refused (reason on stderr).
"""
from __future__ import annotations

import argparse
import json
import sys


def refuse(message: str) -> None:
    sys.stderr.write(
        f"BLOCKED by WarFleet roster: {message}\n"
        "Fix the launch to match the approved roster, or ask the user for a new tier "
        "and add it through plan approval. Never edit the auth file to match a launch.\n")
    sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--speed", default="standard")
    args = parser.parse_args()
    try:
        with open(args.auth, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        refuse(f"auth file unreadable: {exc}")
    approved = data.get("approved") if isinstance(data, dict) else None
    if not isinstance(approved, list):
        refuse("auth file has no approved list")
    entry = next((item for item in approved
                  if isinstance(item, dict) and str(item.get("task")) == args.task_id), None)
    if entry is None:
        refuse(f"task '{args.task_id}' is not in the approved roster")
    for field, value in (("model", args.model), ("effort", args.effort)):
        if entry.get(field) != value:
            refuse(f"{field} mismatch for '{args.task_id}': launch {value!r}, approved {entry.get(field)!r}")
    if "speed" in entry and entry["speed"] != args.speed:
        refuse(f"speed mismatch for '{args.task_id}': launch {args.speed!r}, approved {entry['speed']!r}")


if __name__ == "__main__":
    main()
