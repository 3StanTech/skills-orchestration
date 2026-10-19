#!/usr/bin/env python3
"""Validate a WarFleet launch manifest without starting any model.

Everything here is a check the dispatcher would otherwise have to make by reading
prose at low effort. Mechanical checks, zero judgment, nothing billed.

With `--auth`, this also cross-checks the manifest against
`~/.claude/warfleet/auth-<session-id>.json` BEFORE anything launches, so a tier
mismatch surfaces at approval time instead of as a wrapper (--auth) rejection
mid-wave.

Shared by every WarFleet host (claude, codex, other); `--host` is required. GPT uses
codex-cli, or (on the codex host only) a native-agent route with recorded current
capabilities. Claude uses claude-cli; Grok uses grok-cli.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

BASELINE_GROK_MODEL = "grok-4.5"
# Catalogs live in the sibling headless skill; resolve from this file so clones and installs agree.
HEADLESS_DATA = Path(__file__).resolve().parents[2] / "headless" / "data"
GROK_CATALOG = HEADLESS_DATA / "grok-models.json"


def load_grok_catalog(path: Path) -> dict[str, set[str]]:
    """Per-model Grok effort sets — the one authority, since `grok --help` declares
    --reasoning-effort as free text and an unsupported tier only fails once billed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {name: set(spec.get("efforts", [])) for name, spec in data.get("models", {}).items()}


FAMILIES = {"gpt", "grok", "claude"}
ALL_EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}
DEFAULT_EFFORTS = {
    "gpt": {"low", "medium", "high", "xhigh", "max", "ultra"},
    "gpt-5.6-luna": {"low", "medium", "high", "xhigh", "max"},
    "gpt-5.5": {"low", "medium", "high", "xhigh"},
    "grok": {"low", "medium", "high", "xhigh"},
    "claude": {"low", "medium", "high", "xhigh", "max"},
}
SPEEDS = {"standard", "fast"}
CLAUDE_FAST_MODELS = {"claude-opus-5", "claude-opus-4-8"}
LANES = {"A", "B", "C"}
DEFAULT_MODELS = {
    "gpt": {"gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"},
    "grok": {BASELINE_GROK_MODEL},
    "claude": {"claude-fable-5", "claude-opus-5", "claude-opus-4-8", "claude-sonnet-5"},
}
EXECUTORS = {"native-agent", "codex-cli", "grok-cli", "claude-cli"}


class ManifestError(ValueError):
    """A manifest violates a mechanical launch rule."""


def fail(message: str) -> None:
    raise ManifestError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read JSON {path}: {exc}")


def manifest_root(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        fail("manifest root must be an object")
    return data


def task_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        fail("manifest must contain a non-empty tasks list")
    if any(not isinstance(task, dict) for task in tasks):
        fail("every task entry must be an object")
    return tasks


def approved_records(data: dict[str, Any], roster_path: str | None) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    raw = data.get("approved_roster", data.get("approved_tasks", []))
    if isinstance(raw, dict):
        raw = [{"id": key, **value} for key, value in raw.items() if isinstance(value, dict)]
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                records[item] = {"id": item}
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                records[item["id"]] = item
    if roster_path:
        roster_data = read_json(Path(roster_path))
        if isinstance(roster_data, dict):
            roster_data = roster_data.get("tasks", roster_data.get("roster", roster_data.get("approved_roster", [])))
        if not isinstance(roster_data, list):
            fail("--roster must contain a JSON list or manifest-like object")
        for item in roster_data:
            if isinstance(item, str):
                records[item] = {"id": item}
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                records[item["id"]] = item
    return records


def auth_records(auth_path: str | None) -> dict[str, dict[str, Any]] | None:
    """Read the session auth file the headless wrappers enforce at launch time."""
    if not auth_path:
        return None
    data = read_json(Path(auth_path))
    if not isinstance(data, dict):
        fail("auth file root must be an object")
    if not isinstance(data.get("session_id"), str) or not data["session_id"]:
        fail("auth file must contain a non-empty session_id")
    approved = data.get("approved")
    if not isinstance(approved, list) or not approved:
        fail("auth file must contain a non-empty approved list")
    records: dict[str, dict[str, Any]] = {}
    for item in approved:
        if not isinstance(item, dict) or not isinstance(item.get("task"), str) or not item["task"]:
            fail("every auth entry needs a task id")
        if item["task"] in records:
            fail(f"duplicate auth entry for task: {item['task']}")
        records[item["task"]] = item
    return records


def model_catalog(args: argparse.Namespace) -> dict[str, set[str]]:
    catalog = {family: set(models) for family, models in DEFAULT_MODELS.items()}
    grok = set(load_grok_catalog(args.grok_catalog))
    grok.add(args.grok_model)
    catalog["grok"] = grok
    if args.gpt_model:
        catalog["gpt"] = set(args.gpt_model)
    for item in args.model:
        try:
            family, model = item.split("=", 1)
        except ValueError:
            fail(f"--model must be FAMILY=MODEL: {item}")
        if family not in FAMILIES or not model:
            fail(f"invalid --model entry: {item}")
        catalog[family].add(model)
    return catalog


def effort_catalog(args: argparse.Namespace) -> dict[str, set[str]]:
    catalog = {target: set(efforts) for target, efforts in DEFAULT_EFFORTS.items()}
    catalog.update(load_grok_catalog(args.grok_catalog))
    overrides: dict[str, set[str]] = {}
    for item in args.supported_effort:
        try:
            target, effort = item.split("=", 1)
        except ValueError:
            fail(f"--supported-effort must be FAMILY_OR_MODEL=LEVEL: {item}")
        if not target or effort not in ALL_EFFORTS:
            fail(f"invalid --supported-effort entry: {item}")
        overrides.setdefault(target, set()).add(effort)
    catalog.update(overrides)
    return catalog


def supported_efforts(catalog: dict[str, set[str]], family: str, model: str) -> set[str]:
    return catalog.get(model, catalog[family])


WRAPPER_DIR = Path.home() / ".agents/skills/headless/scripts"
WRAPPERS = {"run-codex.sh": "codex-cli", "run-grok.sh": "grok-cli", "run-claude.sh": "claude-cli"}
APPROVED_WRAPPERS = {os.path.realpath(WRAPPER_DIR / name): executor for name, executor in WRAPPERS.items()}
# Options a wrapper accepts under two spellings (run-grok.sh folds --reasoning-effort into --effort).
FLAG_ALIASES = {"grok-cli": {"--reasoning-effort": "--effort"}}


OPERATOR_CHARS = "();<>|&"
MASK = str.maketrans(OPERATOR_CHARS, "".join(chr(0xE000 + i) for i in range(len(OPERATOR_CHARS))))
UNMASK = {ord(m): c for c, m in zip(OPERATOR_CHARS, (chr(0xE000 + i) for i in range(len(OPERATOR_CHARS))))}
ALLOWED_OPERATORS = {"&&", ">", ">>", ">&"}  # chaining after `cd`, and output redirection


def command_lines(argv: str, label: str) -> list[str]:
    """Split argv at unquoted newlines (each is a command boundary). Rejects command and
    process substitution, which this validator does not parse."""
    lines, current, quote, i = [], [], None, 0
    word_start = True
    while i < len(argv):
        ch = argv[i]
        if quote is None and ch == "#" and word_start:
            while i < len(argv) and argv[i] != "\n":  # comment: runs to the end of the line
                current.append(argv[i])
                i += 1
            continue
        if quote != "'" and (ch == "`" or argv.startswith("$(", i)):
            fail(f"{label}: argv uses command substitution, which the validator does not parse")
        if ch == "\\" and quote != "'" and argv.startswith("\\\n", i):
            i += 2  # line continuation: removed, as the shell does
            continue
        if ch == "\\" and quote != "'" and i + 1 < len(argv):
            current.append(argv[i:i + 2].translate(MASK)); i += 2; word_start = False; continue
        if quote is None and ch in "'\"":
            quote = ch
        elif quote == ch:
            quote = None
        elif quote is None and ch == "\n":
            lines.append("".join(current)); current = []; i += 1; word_start = True; continue
        word_start = quote is None and ch in " \t"
        current.append(ch.translate(MASK) if quote is not None else ch)
        i += 1
    if quote is not None:
        fail(f"{label}: argv has an unterminated quote")
    lines.append("".join(current))
    return lines


def command_segments(argv: str, label: str) -> list[list[str]]:
    """The simple commands in argv: executable first, leading VAR=value words dropped,
    `cd` segments ignored. A bare tag or comment has none. Any other shell operator
    (`;`, `|`, `||`, `&`, parentheses, `<`) is rejected."""
    segments = []
    for line in command_lines(argv, label):
        try:
            # Quoted operator characters were masked by command_lines; comments
            # (`# warfleet-task:t1`) are stripped by the lexer.
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError as exc:
            fail(f"{label}: argv is not parseable: {exc}")
        current = []
        for token in tokens + ["&&"]:
            if token == "&&":
                while current and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", current[0], re.S):
                    current.pop(0)
                if current and current[0] != "cd":
                    segments.append(current)
                current = []
            elif set(token) <= set("();<>|&") and token not in ALLOWED_OPERATORS:
                fail(f"{label}: argv uses shell operator {token!r}, which the validator does not parse")
            else:
                current.append(token.translate(UNMASK))
    return segments


def validate_argv(task: dict[str, Any], argv: str, auth_path: str | None) -> None:
    """Executable argv must run an approved wrapper and say what the task metadata says.
    The launch hook only checks the auth entry, so a contradicting argv would run an
    unapproved identity."""
    label = task["id"]
    segments = command_segments(argv, label)
    if not segments:
        return  # native-agent launches and bare tags carry no executable
    for segment in segments:
        exe = segment[0]
        approved = APPROVED_WRAPPERS.get(os.path.realpath(os.path.expanduser(exe))) if os.path.isabs(os.path.expanduser(exe)) else None
        if approved is None:
            fail(f"{label}: argv runs {exe!r}, which is not an approved headless wrapper "
                 f"({', '.join(sorted(APPROVED_WRAPPERS))})")
    if len(segments) != 1:
        fail(f"{label}: argv must run exactly one wrapper command")
    tokens = segments[0]
    wrapper = APPROVED_WRAPPERS[os.path.realpath(os.path.expanduser(tokens[0]))]
    if wrapper != task["executor"]:
        fail(f"{label}: argv wrapper does not match executor {task['executor']}")
    aliases = FLAG_ALIASES.get(wrapper, {})
    flags: dict[str, list[str]] = {}
    for i, token in enumerate(tokens[:-1]):
        if token.startswith("--"):
            flags.setdefault(aliases.get(token, token), []).append(tokens[i + 1])

    def expect(flag: str, want: Any, default: Any = None) -> None:
        values = flags.get(flag, [] if default is None else [default])
        if not values or any(v != want for v in values):
            fail(f"{label}: argv {flag} {values or 'missing'} contradicts task {want!r}")

    expect("--model", task["model"])
    expect("--effort", task["effort"])
    expect("--lane", task["lane"])
    expect("--speed", task["speed"], default="standard")
    approve = flags.get("--approve-lane-c", [])
    if task["lane"] == "C":
        expect("--approve-lane-c", "yes")
    elif approve:
        fail(f"{label}: argv --approve-lane-c is only valid on lane C")
    if auth_path is not None:
        expect("--task-id", task["id"])
        values = flags.get("--auth", [])
        if not values or any(
            os.path.realpath(os.path.expanduser(v)) != os.path.realpath(os.path.expanduser(auth_path))
            for v in values
        ):
            fail(f"{label}: argv --auth {values or 'missing'} contradicts the validated auth file")


def validate_executor(data: dict[str, Any], task: dict[str, Any], host: str) -> None:
    family, executor = task["family"], task["executor"]
    label = task["id"]
    if family != "gpt":
        required = {"grok": "grok-cli", "claude": "claude-cli"}[family]
        if executor != required:
            fail(f"{label}: {task['model']} must use executor {required}")
        return
    if executor == "codex-cli":
        return  # Compatible with A/B/C and explicit standard/fast in the wrapper.
    if host != "codex":
        # Claude Code has no native GPT agent surface — every GPT task is a codex-cli launch.
        fail(f"{label}: GPT tasks on host {host} require executor codex-cli")
    if executor != "native-agent":
        fail(f"{label}: GPT requires codex-cli or native-agent")
    caps = data.get("native_agent_capabilities", {})
    if not isinstance(caps, dict):
        fail(f"{label}: native_agent_capabilities must be an object")
    evidence = caps.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        fail(f"{label}: native-agent requires current capability evidence; use codex-cli if unavailable")
    models = caps.get("models", {})
    levels = models.get(task["model"], []) if isinstance(models, dict) else []
    lanes, speeds = caps.get("lanes", []), caps.get("speeds", [])
    if (not isinstance(levels, list) or task["effort"] not in levels
            or not isinstance(lanes, list) or task["lane"] not in lanes
            or not isinstance(speeds, list) or task["speed"] not in speeds):
        fail(f"{label}: native-agent cannot satisfy recorded model/effort/lane/speed; use codex-cli")


def validate_identity(
    record: dict[str, Any],
    label: str,
    models: dict[str, set[str]],
    efforts: dict[str, set[str]],
) -> tuple[str, str, str, str]:
    family = record.get("family")
    model = record.get("model")
    effort = record.get("effort")
    speed = record.get("speed")
    if family not in FAMILIES:
        fail(f"{label}: unknown family: {family}")
    if model not in models[family]:
        fail(f"{label}: model is not in the approved catalog for {family}: {model}")
    allowed = supported_efforts(efforts, family, model)
    if effort not in allowed:
        fail(f"{label}: effort {effort!r} is not supported by {model}; supported: {', '.join(sorted(allowed))}")
    if speed not in SPEEDS:
        fail(f"{label}: explicit speed must be standard or fast")
    if family == "grok" and speed != "standard":
        fail(f"{label}: Grok has no fast-mode control; speed must be standard")
    if speed == "fast" and family == "claude" and model not in CLAUDE_FAST_MODELS:
        fail(f"{label}: Claude fast mode is supported only by Opus models")
    if speed == "fast" and family == "grok":
        fail(f"{label}: Grok has no WarFleet fast-mode control")
    return family, model, effort, speed


def validate_muster(
    data: dict[str, Any], models: dict[str, set[str]], efforts: dict[str, set[str]]
) -> list[tuple[str, str, str, str]]:
    muster = data.get("muster")
    if not isinstance(muster, dict):
        fail("manifest must contain the canonical muster object")
    raw = muster.get("raw_answers")
    if not isinstance(raw, dict) or any(
        not isinstance(raw.get(key), str) or not raw[key]
        for key in ("fleet_admiral", "general", "infantry", "infantry_subagents")
    ):
        fail("muster must preserve all four non-empty raw answers")

    admirals = muster.get("admirals")
    if not isinstance(admirals, list) or not 1 <= len(admirals) <= 2 or any(not isinstance(i, dict) for i in admirals):
        fail("muster must contain one or two Admirals")
    for index, admiral in enumerate(admirals, start=1):
        validate_identity(admiral, f"admiral[{index}]", models, efforts)
    if muster.get("secondary_admiral", len(admirals) == 2) != (len(admirals) == 2):
        fail("muster secondary_admiral flag contradicts the Admiral count")

    general = muster.get("general")
    if not isinstance(general, dict):
        fail("muster must contain exactly one General object")
    validate_identity(general, "general", models, efforts)

    infantry = muster.get("infantry")
    if not isinstance(infantry, list) or not infantry or any(not isinstance(i, dict) for i in infantry):
        fail("muster must contain at least one Infantry tier")
    identities = [
        validate_identity(item, f"infantry[{index}]", models, efforts)
        for index, item in enumerate(infantry, start=1)
    ]

    subagents = muster.get("infantry_subagents")
    if not isinstance(subagents, dict) or subagents.get("stance") not in {
        "supersoldiers", "vibin", "chillin",
    }:
        fail("muster infantry_subagents.stance must be supersoldiers, vibin, or chillin")

    allocation = muster.get("allocation")
    if not isinstance(allocation, dict) or allocation.get("mode") not in {"task_fit", "fixed"}:
        fail("muster allocation mode must be task_fit or fixed")
    shares = [item.get("share") for item in infantry]
    if allocation["mode"] == "fixed":
        if allocation.get("unit") != "task_count":
            fail("fixed allocation unit must be task_count")
        if any(not isinstance(s, int) or isinstance(s, bool) for s in shares) or sum(shares) != 100:
            fail("fixed Infantry shares must be integers totaling 100")
    elif any(share is not None for share in shares):
        fail("task_fit allocation must not contain Infantry shares")
    return identities


def absolute_field(record: dict[str, Any], name: str, label: str) -> str:
    value = record.get(name)
    if not isinstance(value, str) or not value:
        fail(f"{label}: {name} is required")
    if not os.path.isabs(value):
        fail(f"{label}: {name} must be absolute")
    return value


def edit_files(task: dict[str, Any]) -> list[str]:
    raw = task.get("edit_files", task.get("files", []))
    if raw is None:
        return []
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        fail(f"{task.get('id', '<unknown>')}: edit_files must be a list of strings")
    return raw


def validate_subagents(task: dict[str, Any], task_id: str) -> None:
    """A ceiling on the whole descendant tree, sized by the Admiral. Not a target."""
    budget = task.get("subagents")
    if not isinstance(budget, dict):
        fail(f"{task_id}: subagents budget object is required")
    max_total = budget.get("max_total")
    parallel = budget.get("parallel")
    rationale = budget.get("rationale")
    if not isinstance(max_total, int) or isinstance(max_total, bool) or max_total < 0:
        fail(f"{task_id}: subagents.max_total must be a non-negative integer")
    if not isinstance(parallel, bool):
        fail(f"{task_id}: subagents.parallel must be boolean")
    if not isinstance(rationale, str) or not rationale.strip():
        fail(f"{task_id}: subagents.rationale is required")
    if max_total == 0 and parallel:
        fail(f"{task_id}: subagents.parallel must be false when max_total is zero")


def validate(path: Path, args: argparse.Namespace) -> None:
    data = manifest_root(read_json(path))
    tasks = task_list(data)
    models = model_catalog(args)
    efforts = effort_catalog(args)
    infantry_identities = set(validate_muster(data, models, efforts))
    mission_context = absolute_field(data, "mission_context", "manifest")
    approved = approved_records(data, args.roster)
    auth = auth_records(args.auth)
    seen_ids: set[str] = set()
    wave_by_id: dict[str, int] = {}
    files_by_wave: dict[int, dict[str, str]] = {}

    for task in tasks:
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            fail("task id is required")
        if task_id in seen_ids:
            fail(f"duplicate task id: {task_id}")
        seen_ids.add(task_id)

        wave = task.get("wave")
        if not isinstance(wave, int) or isinstance(wave, bool) or wave < 1:
            fail(f"{task_id}: wave must be a positive integer")
        wave_by_id[task_id] = wave

        identity = validate_identity(task, task_id, models, efforts)
        family, model, effort, speed = identity
        if identity not in infantry_identities:
            fail(f"{task_id}: model/effort/speed identity is outside the approved Infantry roster")
        lane = task.get("lane")
        if lane not in LANES:
            fail(f"{task_id}: unknown lane: {lane}")
        executor = task.get("executor")
        if executor not in EXECUTORS:
            fail(f"{task_id}: explicit executor is required, one of {', '.join(sorted(EXECUTORS))}")
        validate_executor(data, task, args.host)

        absolute_field(task, "task_file", task_id)
        absolute_field(task, "output_file", task_id)
        if absolute_field(task, "context_file", task_id) != mission_context:
            fail(f"{task_id}: context_file must match manifest mission_context")
        thread_id = task.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            fail(f"{task_id}: thread_id is required")
        argv = task.get("argv")
        if not isinstance(argv, str) or not argv.strip():
            fail(f"{task_id}: argv is required")
        validate_argv(task, argv, args.auth)

        deps = task.get("dependencies")
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            fail(f"{task_id}: dependencies must be a list of task ids")
        acceptance = task.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance or any(
            not isinstance(item, str) or not item.strip() for item in acceptance
        ):
            fail(f"{task_id}: acceptance must contain at least one non-empty criterion")
        validate_subagents(task, task_id)

        # Browser work belongs to the dispatcher's own pane. An Infantry unit given a
        # browser in a sandboxed lane loses it on spawn — a real Grok unit at
        # read-only lost 46 checks to SIGSEGV before this rule existed.
        if task.get("browser", False) is True:
            fail(f"{task_id}: browser work belongs to the dispatcher, never an Infantry unit")

        for file_path in edit_files(task):
            if not os.path.isabs(file_path):
                fail(f"{task_id}: edit_files paths must be absolute")
            prior = files_by_wave.setdefault(wave, {}).get(file_path)
            if prior:
                fail(f"wave {wave}: {prior} and {task_id} edit the same file: {file_path}")
            files_by_wave[wave][file_path] = task_id

        if approved:
            record = approved.get(task_id)
            if record is None:
                fail(f"{task_id}: task is outside the approved roster")
            for field in ("family", "model", "effort", "speed", "lane", "executor", "subagents"):
                if field in record and record[field] != task[field]:
                    fail(f"{task_id}: silent {field} substitution: approved {record[field]!r}, got {task[field]!r}")

        if auth is not None:
            entry = auth.get(task_id)
            if entry is None:
                fail(f"{task_id}: no auth entry — the hook will block this launch")
            # Verbatim, because the hook compares verbatim. `opus` here and
            # `claude-opus-5` on the command line blocks the launch it authorizes.
            if entry.get("model") != model:
                fail(f"{task_id}: auth model {entry.get('model')!r} != manifest {model!r}")
            if entry.get("effort") != effort:
                fail(f"{task_id}: auth effort {entry.get('effort')!r} != manifest {effort!r}")
            if "speed" in entry and entry["speed"] != speed:
                fail(f"{task_id}: auth speed {entry['speed']!r} != manifest {speed!r}")

    for task in tasks:
        for dep in task["dependencies"]:
            if dep not in wave_by_id:
                fail(f"{task['id']}: dependency is outside the roster: {dep}")
            if wave_by_id[dep] >= task["wave"]:
                fail(f"{task['id']}: dependency {dep} is in the same or a later wave")

    extra = "" if auth is None else f", {len(auth)} auth entries"
    print(f"VALID: {path} ({len(tasks)} tasks{extra})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--host", required=True, choices=("claude", "codex", "other"),
                        help="dispatcher host; native-agent GPT executors exist only on codex")
    parser.add_argument("--roster", help="JSON file containing approved task ids or records")
    parser.add_argument("--auth", help="~/.claude/warfleet/auth-<session-id>.json to cross-check")
    parser.add_argument("--grok-model", default=BASELINE_GROK_MODEL,
                        help="live Grok default from ~/.agents/skills/headless/scripts/resolve-grok-model.sh")
    parser.add_argument("--grok-catalog", type=Path, default=GROK_CATALOG,
                        help="per-model Grok effort table (headless data/grok-models.json)")
    parser.add_argument("--gpt-model", action="append", default=[], help="currently exposed GPT model id; repeat for each")
    parser.add_argument("--model", action="append", default=[], help="additional exact model in FAMILY=MODEL form")
    parser.add_argument("--supported-effort", action="append", default=[], help="live supported effort in FAMILY_OR_MODEL=LEVEL form")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(args.manifest, args)
    except ManifestError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
