#!/usr/bin/env python3
"""Check a helper context packet before launch (stdlib only, any host).

  packet-check.py <packet.md>

Exit 0 when the packet is launchable; exit 2 with one `packet<TAB><problem>` line per problem.
Fails on: empty goal; unknown task type; working directory not absolute or missing; empty owned
list or an owned path that does not exist (unless marked `(new)` or `(delete)`); an acceptance bullet
without a backticked command or `browser:` capture; a network task without a smoke test; a report
format missing STATUS/FILES/BLOCKERS/NOTES; leftover `<placeholder>` text.

Accepted owned-entry forms:
  - `path`                          the path is the first backtick span; trailing notes are ignored
  - `path` (new) | `path` (delete)  the path may be missing (created, or removed by the task)
  - path (note)                     no backticks: the path is the text before ` (`
  - an unmarked path that an acceptance bullet asserts absent with `test ! -e <path>` counts as (delete)
  - none (read-only…)               review tasks only, as the sole entry: path checks are skipped and
                                    acceptance may be `report: <what the Report format carries>`

Format: ~/.agents/skills/stance/templates/context-packet.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

TABLE = Path(os.environ.get("ROUTE_TABLE", Path.home() / ".agents/skills/stance/data/routing.json"))
FIELD = re.compile(r"^\*\*(?P<name>[^*]+?):\*\*\s*(?P<value>.*)$")
PLACEHOLDER = re.compile(r"<[a-z][^<>`]*>")
MARKER = re.compile(r"\((?:new|delete)\)")
READ_ONLY = re.compile(r"^none \(read-only\b[^)]*\)\s*$")
ABSENT = re.compile(r"test ! -e ([^\s`]+)")


def sections(text: str) -> dict[str, list[str]]:
    """Map each **Field:** to its inline value plus the lines until the next field."""
    out, current = {}, None
    for line in text.splitlines():
        match = FIELD.match(line.strip())
        if match:
            current = match.group("name").strip().lower()
            out[current] = [match.group("value").strip()]
        elif current:
            out[current].append(line.rstrip())
    return out


def bullets(lines: list[str]) -> list[str]:
    return [l.strip()[2:].strip() for l in lines if l.strip().startswith("- ")]


def strip_code(text: str) -> str:
    return re.sub(r"`[^`]*`", "", re.sub(r"```.*?```", "", text, flags=re.S))


def task_types() -> set[str]:
    try:
        rows = json.loads(TABLE.read_text(encoding="utf-8"))["task_types"]
    except (OSError, ValueError, KeyError):
        return {"plan", "mechanical", "standard", "hard", "review", "network"}
    return {name for name, row in rows.items() if not row.get("dispatcher_only")}


def check(text: str) -> list[str]:
    problems = []
    s = sections(text)

    def value(name: str) -> str:
        return " ".join(l for l in s.get(name, []) if l.strip()).strip()

    if not value("goal"):
        problems.append("goal is empty")
    ttype = value("task type")
    if ttype not in task_types():
        problems.append(f"task type {ttype or '(missing)'!r} is not a routing-table task type")
    workdir = Path(value("working directory").strip("`"))
    if not workdir.is_absolute() or not workdir.is_dir():
        problems.append(f"working directory {str(workdir)!r} is not an existing absolute path")
    owned = [k for k in s if k.startswith("you own")]
    entries = bullets(s[owned[0]]) if owned else []
    accept = [k for k in s if k.startswith("acceptance")]
    checks = bullets(s[accept[0]]) if accept else []
    read_only = ttype == "review" and len(entries) == 1 and READ_ONLY.match(entries[0]) is not None
    if not entries:
        problems.append("owned-file list is empty")
    absent = {m.group(1) for item in checks for m in ABSENT.finditer(item)}
    for entry in [] if read_only else entries:
        span = re.search(r"`([^`]+)`", entry)
        path = (span.group(1) if span else entry.split(" (", 1)[0]).strip()
        may_be_missing = MARKER.search(entry) is not None or path in absent
        full = Path(path) if Path(path).is_absolute() else workdir / path
        if not may_be_missing and not full.exists():
            problems.append(f"owned file {path!r} does not exist (mark it `(new)` or `(delete)` if this task creates or removes it)")
    if not checks:
        problems.append("acceptance has no bullets")
    for item in checks:
        runnable = re.search(r"`[^`]+`", item) or item.lower().startswith("browser:")
        if not runnable and not (read_only and item.lower().startswith("report:")):
            problems.append(f"acceptance {item[:60]!r} has no runnable `command` or browser: capture")
    smoke = value("smoke test")
    if ttype == "network" and (not smoke or smoke.lower().strip("`") == "none"):
        problems.append("network task has no smoke test")
    report = "\n".join(s.get("report format", []))
    missing = [k for k in ("STATUS:", "FILES:", "BLOCKERS:", "NOTES:") if k not in report]
    if missing:
        problems.append(f"report format is missing {', '.join(missing)}")
    leftovers = PLACEHOLDER.findall(strip_code(text))
    if leftovers:
        problems.append(f"placeholder text left: {', '.join(sorted(set(leftovers))[:3])}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        text = Path(argv[0]).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"packet\tcannot read {argv[0]}: {exc}")
        return 2
    problems = check(text)
    for p in problems:
        print(f"packet\t{p}")
    print(f"packet_check={'pass' if not problems else 'fail'} count={len(problems)}")
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
