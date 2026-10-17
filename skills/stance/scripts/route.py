#!/usr/bin/env python3
"""Routing-table resolver, validator and outcome log (any host; stdlib only).

  route.py resolve --task-type T --host H [--project DIR] [--named M:E[:S]] [--roster M:E[:S]]
  route.py validate
  route.py log --plan P --task ID --task-type T --host H --project DIR --model M --effort E
               --route R --source S --first-pass yes|no --repairs N --status S
               [--returned-by acceptance,seam,review,dispatcher-check|none]
               [--repaired-by original|fresh-helper|dispatcher|escalation] [--repairs-of TASK]
               [--escalated-to M] [--model-check ok|mismatch:<id>|n/a] [--note "<evidence>"]
  route.py correct --plan P --task ID [--date D] [--host H] [--first-pass yes|no] [--returned-by ...]
               [--repairs N] [--repaired-by ...] [--repairs-of TASK] --note "<evidence>"
  route.py review [--min-fails N]
  route.py nudge --task-type T --model M --effort E [--min-fails N]
  route.py check-model --transcript FILE --expect ID

Exit codes: 0 ok; 1 findings (validate, nudge); 2 invalid input; 3 needs the owner
(no tier at any level, or an inactive family). Rules: ~/.agents/skills/stance/references/routing.md.
Paths can be overridden for tests with ROUTE_TABLE, ROUTE_OUTCOMES, ROUTE_CLAUDE_CATALOG,
ROUTE_GROK_CATALOG and ROUTE_GPT_CATALOG (a saved `codex debug models --bundled` output).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HOME = Path.home()
TABLE = Path(os.environ.get("ROUTE_TABLE", HOME / ".agents/skills/stance/data/routing.json"))
OUTCOMES = Path(os.environ.get("ROUTE_OUTCOMES", HOME / ".agents/state/outcomes.jsonl"))
CLAUDE_CATALOG = Path(os.environ.get("ROUTE_CLAUDE_CATALOG", HOME / ".agents/skills/headless/data/claude-models.json"))
GROK_CATALOG = Path(os.environ.get("ROUTE_GROK_CATALOG", HOME / ".agents/skills/headless/data/grok-models.json"))
GPT_CATALOG = os.environ.get("ROUTE_GPT_CATALOG")

HOSTS = ("claude", "codex", "grok", "hermes", "pi", "other")
NATIVE_FAMILY = {"claude": "claude", "codex": "gpt", "grok": "grok"}
ENGINE = {"claude": "claude", "gpt": "codex", "grok": "grok"}
TIER_KEYS = ("tier", "escalation", "fallback")
RETURNED_BY = ("acceptance", "seam", "review", "dispatcher-check")
REPAIRED_BY = ("original", "fresh-helper", "dispatcher", "escalation")
CORRECTABLE = ("host", "first_pass", "returned_by", "repairs", "repaired_by", "repairs_of")
NUDGE_WINDOW = 10


class Exit(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def family(model: str) -> str:
    for prefix, fam in (("claude-", "claude"), ("gpt-", "gpt"), ("grok-", "grok")):
        if model.startswith(prefix):
            return fam
    raise Exit(2, f"{model}: unknown model family (expected claude-, gpt- or grok- prefix)")


def parse_tier(raw: str) -> dict:
    parts = raw.split(":")
    if len(parts) not in (2, 3) or not all(parts):
        raise Exit(2, f"{raw!r}: expected MODEL:EFFORT or MODEL:EFFORT:SPEED")
    return {"model": parts[0], "effort": parts[1], "speed": parts[2] if len(parts) == 3 else "standard"}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Exit(2, f"cannot read {path}: {exc}")


def gpt_catalog() -> dict[str, dict]:
    if GPT_CATALOG:
        text = Path(GPT_CATALOG).read_text(encoding="utf-8")
    else:
        try:
            text = subprocess.run(["codex", "debug", "models", "--bundled"], capture_output=True,
                                  text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Exit(2, f"gpt catalog unavailable: {exc}")
    start = text.find("{")
    if start < 0:
        raise Exit(2, "gpt catalog unavailable: no JSON from `codex debug models --bundled`")
    data = json.loads(text[start:])
    return {m["slug"]: {"efforts": [e["effort"] for e in m.get("supported_reasoning_levels", [])],
                        "fast": "fast" in (m.get("additional_speed_tiers") or [])}
            for m in data.get("models", [])}


class Catalogs:
    def __init__(self):
        self._cache: dict[str, dict] = {}

    def claude(self) -> dict:
        if "claude" not in self._cache:
            self._cache["claude"] = load_json(CLAUDE_CATALOG)
        return self._cache["claude"]

    def models(self, fam: str) -> dict[str, dict]:
        if fam not in self._cache:
            if fam == "gpt":
                self._cache[fam] = gpt_catalog()
            elif fam == "grok":
                self._cache[fam] = {k: {"efforts": v["efforts"], "fast": False}
                                    for k, v in load_json(GROK_CATALOG)["models"].items()}
        if fam == "claude":
            return self.claude()["models"]
        return self._cache[fam]

    def aliases(self) -> dict[str, str]:
        return {k: v for k, v in self.claude().get("aliases", {}).items() if k != "confirmed"}


def check_tier(tier: dict, cats: Catalogs, label: str) -> str:
    """Return the tier's family, or raise Exit(2) if the catalog rejects it."""
    fam = family(tier["model"])
    spec = cats.models(fam).get(tier["model"])
    if spec is None:
        raise Exit(2, f"{label}: {tier['model']} is not in the {fam} catalog")
    if tier["effort"] not in spec["efforts"]:
        raise Exit(2, f"{label}: {tier['model']} does not accept effort {tier['effort']} "
                      f"(catalog: {', '.join(spec['efforts'])})")
    speed = tier.get("speed", "standard")
    if speed not in ("standard", "fast") or (speed == "fast" and not spec.get("fast")):
        raise Exit(2, f"{label}: {tier['model']} does not support speed {speed}")
    return fam


def merged_row(table: dict, task_type: str, project: str | None) -> tuple[dict, bool]:
    rows = table.get("task_types", {})
    if task_type not in rows:
        raise Exit(2, f"unknown task type {task_type!r} (table has: {', '.join(rows)})")
    row = dict(rows[task_type])
    override = {}
    if project:
        override = (table.get("projects", {}).get(str(Path(project).expanduser().resolve()), {})
                    .get("task_types", {}).get(task_type, {}))
        row.update(override)
    return row, bool(override.get("tier"))


def route_for(fam: str, preference: str, host: str, tier: dict, cats: Catalogs) -> tuple[str, str | None]:
    if preference == "native" and NATIVE_FAMILY.get(host) == fam:
        if host == "claude":
            alias = next((a for a, mid in cats.aliases().items() if mid == tier["model"]), None)
            # Subagents inherit the session's speed and only take aliases: exact-ID or fast -> headless.
            if alias and tier.get("speed", "standard") == "standard":
                return "subagent", alias
            return "headless:claude", None
        return f"native:{host}", None
    return f"headless:{ENGINE[fam]}", None


DEFAULT_TASK_TYPES = ("plan", "mechanical", "standard", "hard", "review", "network", "visual")
NO_TABLE = ("no routing table at {}: run install.sh or copy routing.example.json; until then name "
            "a tier (implement using <model-id> <effort> <stance>) or the agent asks")


def load_table() -> dict:
    """The routing table is optional: missing reads as empty, so named tiers still resolve."""
    return load_json(TABLE) if TABLE.exists() else {}


def resolve(args) -> dict:
    if args.host not in HOSTS:
        raise Exit(2, f"unknown host {args.host!r} (expected one of {', '.join(HOSTS)})")
    table, cats = load_table(), Catalogs()
    if table:
        row, project_tier = merged_row(table, args.task_type, args.project)
    elif args.task_type in DEFAULT_TASK_TYPES:
        # No table: the built-in task types still apply, and visual is never delegated.
        row, project_tier = {"dispatcher_only": args.task_type == "visual"}, False
    else:
        raise Exit(2, f"unknown task type {args.task_type!r} (expected one of {', '.join(DEFAULT_TASK_TYPES)})")
    if row.get("dispatcher_only"):
        return {"task_type": args.task_type, "route": "dispatcher", "source": "table" if table else "built-in"}
    if args.named:
        tier, source = parse_tier(args.named), "named"
    elif args.roster:
        tier, source = parse_tier(args.roster), "roster"
    elif row.get("tier"):
        tier, source = dict(row["tier"]), "project" if project_tier else "global"
    elif not table:
        raise Exit(3, NO_TABLE.format(TABLE))
    else:
        raise Exit(3, f"no tier for task type {args.task_type!r}: ask the owner for model + effort")
    tier.setdefault("speed", "standard")
    fam = check_tier(tier, cats, source)
    status = table.get("families", {}).get(fam, {"active": True})
    # A tier the owner names is their availability call; table and roster tiers are not.
    if source != "named" and not status.get("active", True):
        raise Exit(3, f"family {fam} is inactive ({status.get('reason', 'no reason recorded')}); "
                      "ask the owner before using it")
    route, alias = route_for(fam, row.get("route", "native"), args.host, tier, cats)
    return {"task_type": args.task_type, "source": source, "model": tier["model"],
            "effort": tier["effort"], "speed": tier["speed"], "family": fam, "route": route,
            "subagent_alias": alias, "escalation": row.get("escalation"),
            "fallback": row.get("fallback"), "notes": row.get("notes", "")}


def validate(_args) -> list[str]:
    if not TABLE.exists():
        return [NO_TABLE.format(TABLE)]
    table, cats = load_json(TABLE), Catalogs()
    findings = []
    families = table.get("families", {})

    def check_rows(rows: dict, where: str):
        for name, row in rows.items():
            if name not in table.get("task_types", {}):
                findings.append(f"{where}{name}: unknown task type")
                continue
            if row.get("dispatcher_only"):
                continue
            for key in TIER_KEYS:
                tier = row.get(key)
                if not tier:
                    continue
                try:
                    fam = family(tier["model"])
                    if not families.get(fam, {}).get("active", True):
                        continue
                    check_tier(dict(tier, speed=tier.get("speed", "standard")), cats, f"{where}{name}.{key}")
                except (Exit, KeyError) as exc:
                    findings.append(str(exc) if isinstance(exc, Exit) else f"{where}{name}.{key}: missing {exc}")
            if row.get("route", "native") not in ("native", "headless"):
                findings.append(f"{where}{name}: route must be native or headless")

    check_rows(table.get("task_types", {}), "")
    for path, override in table.get("projects", {}).items():
        if not Path(path).is_dir():
            findings.append(f"project {path}: folder does not exist")
        check_rows(override.get("task_types", {}), f"project {path}: ")
    for alias, mid in cats.aliases().items():
        if mid not in cats.models("claude"):
            findings.append(f"alias {alias} -> {mid}: not a claude catalog row")
    return findings


def read_raw() -> list[dict]:
    if not OUTCOMES.exists():
        return []
    rows = []
    for line in OUTCOMES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def key_of(row: dict) -> tuple:
    return (row.get("plan"), row.get("task"), row.get("date"))


def read_outcomes() -> list[dict]:
    """Effective rows: the latest correction per (plan, task, date) merged over the original.

    Correction rows are never counted as runs themselves."""
    raw = read_raw()
    latest = {}
    for r in raw:
        if "correction_of" in r:
            c = r["correction_of"]
            latest[(c.get("plan"), c.get("task"), c.get("date"))] = r
    rows = []
    for r in raw:
        if "correction_of" in r:
            continue
        fix = latest.get(key_of(r))
        if fix:
            r = dict(r, **{k: fix[k] for k in CORRECTABLE if k in fix})
        rows.append(r)
    return rows


def parse_returned_by(raw: str) -> list[str]:
    values = [v.strip() for v in raw.split(",") if v.strip()]
    if values == ["none"]:
        return []
    bad = [v for v in values if v not in RETURNED_BY]
    if not values or bad:
        raise Exit(2, f"--returned-by {raw!r}: expected a comma list from {', '.join(RETURNED_BY)}, or none")
    return sorted(set(values), key=RETURNED_BY.index)


def check_consistency(first_pass: bool, returned_by: list[str]) -> None:
    if first_pass and "acceptance" in returned_by:
        raise Exit(2, "--first-pass yes cannot include acceptance in --returned-by "
                      "(first_pass means the packet's Acceptance passed on the first report)")
    if not first_pass and "acceptance" not in returned_by:
        raise Exit(2, "--first-pass no needs acceptance in --returned-by "
                      "(seam, review and dispatcher-check returns alone keep first_pass yes)")


def returned_for(first_pass: bool, raw: str | None) -> list[str]:
    if raw is None:
        if not first_pass:
            raise Exit(2, "--first-pass no requires --returned-by (at least acceptance)")
        returned = []
    else:
        returned = parse_returned_by(raw)
    check_consistency(first_pass, returned)
    return returned


def check_host(host: str) -> None:
    if host not in HOSTS:
        raise Exit(2, f"unknown host {host!r} (expected one of {', '.join(HOSTS)})")


def log(args) -> dict:
    check_host(args.host)
    first_pass = args.first_pass == "yes"
    entry = {"date": dt.date.today().isoformat(), "host": args.host, "project": args.project,
             "plan": args.plan, "task": args.task, "task_type": args.task_type, "model": args.model,
             "effort": args.effort, "route": args.route, "source": args.source,
             "first_pass": first_pass, "returned_by": returned_for(first_pass, args.returned_by),
             "repairs": args.repairs, "repaired_by": args.repaired_by, "repairs_of": args.repairs_of,
             "escalated_to": args.escalated_to,
             "status": "complete" if args.status == "done" else args.status,
             "model_check": args.model_check}
    if args.note:
        entry["note"] = args.note
    append(entry)
    return entry


def append(entry: dict) -> None:
    OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
    with OUTCOMES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def correct(args) -> dict:
    originals = [r for r in read_raw() if "correction_of" not in r
                 and r.get("plan") == args.plan and r.get("task") == args.task
                 and (args.date is None or r.get("date") == args.date)]
    if not originals:
        raise Exit(2, f"no logged row for plan {args.plan!r} task {args.task!r}"
                      + (f" date {args.date}" if args.date else ""))
    dates = sorted({r.get("date") for r in originals})
    if len(dates) > 1:
        raise Exit(2, f"task {args.task!r} has rows on {', '.join(dates)}; pass --date")
    key = (args.plan, args.task, dates[0])
    current = next(r for r in read_outcomes() if key_of(r) == key)
    previous = {}
    for r in read_raw():
        c = r.get("correction_of")
        if c and (c.get("plan"), c.get("task"), c.get("date")) == key:
            previous = {k: r[k] for k in CORRECTABLE if k in r}
    fields = dict(previous)
    if args.host is not None:
        check_host(args.host)
        fields["host"] = args.host
    if args.first_pass is not None:
        fields["first_pass"] = args.first_pass == "yes"
    if args.returned_by is not None:
        fields["returned_by"] = parse_returned_by(args.returned_by)
    if args.repairs is not None:
        fields["repairs"] = args.repairs
    if args.repaired_by is not None:
        fields["repaired_by"] = args.repaired_by
    if args.repairs_of is not None:
        fields["repairs_of"] = args.repairs_of
    if fields == previous:
        raise Exit(2, "nothing to correct: pass at least one changed field")
    if args.first_pass is not None or args.returned_by is not None:
        first_pass = fields.get("first_pass", bool(current.get("first_pass")))
        if "returned_by" not in fields:
            fields["returned_by"] = returned_for(first_pass, None)
        check_consistency(first_pass, fields["returned_by"])
    entry = {"correction_of": {"plan": key[0], "task": key[1], "date": key[2]}, **fields,
             "note": args.note, "corrected_on": dt.date.today().isoformat()}
    append(entry)
    return entry


def classified_returns(row: dict) -> list[str] | None:
    """The row's returned_by list, or None for a legacy row whose return cause was never recorded."""
    if "returned_by" in row:
        return row["returned_by"]
    return [] if row.get("first_pass") else None


def nudge_window(rows: list[dict], task_type: str, model: str, effort: str, min_fails: int) -> dict:
    window = [r for r in rows if r.get("task_type") == task_type and r.get("model") == model
              and r.get("effort") == effort and not r.get("repairs_of")
              and classified_returns(r) is not None][-NUDGE_WINDOW:]
    fails = sum(1 for r in window if not r.get("first_pass"))
    rate = (len(window) - fails) / len(window) if window else 1.0
    return {"runs": len(window), "fails": fails, "rate": rate,
            "fire": fails >= min_fails and rate < 0.5}


def nudge_text(w: dict) -> str:
    return (f"failed first pass {w['fails']}x in the last {w['runs']} classified runs "
            f"(first-pass rate {round(w['rate'] * 100)}%)")


def review(args) -> list[str]:
    rows = read_outcomes()
    stats = defaultdict(lambda: {"runs": 0, "classified": 0, "first": 0, "repair_rows": 0, "escalated": 0,
                                 "blocked": 0, "mismatch": 0, "unclassified": 0,
                                 **{k: 0 for k in RETURNED_BY}})
    unclassified, bad_hosts = [], []
    for r in rows:
        s = stats[(r.get("task_type"), r.get("model"), r.get("effort"))]
        s["escalated"] += bool(r.get("escalated_to"))
        s["blocked"] += r.get("status") == "blocked"
        s["mismatch"] += str(r.get("model_check", "")).startswith("mismatch")
        if r.get("host") not in HOSTS:
            bad_hosts.append(r)
        if r.get("repairs_of"):
            s["repair_rows"] += 1
            continue
        s["runs"] += 1
        returned = classified_returns(r)
        if returned is None:
            s["unclassified"] += 1
            unclassified.append(r)
            continue
        s["classified"] += 1
        s["first"] += bool(r.get("first_pass"))
        for k in returned:
            s[k] += 1
    lines = []
    for (task_type, model, effort), s in sorted(stats.items(), key=lambda kv: tuple(map(str, kv[0]))):
        returned = ",".join(f"{k}:{s[k]}" for k in (*RETURNED_BY, "unclassified"))
        lines.append(f"{task_type}\t{model}:{effort}\truns={s['runs']} first_pass={s['first']}/{s['classified']} "
                     f"escalated={s['escalated']} blocked={s['blocked']} model_mismatch={s['mismatch']} "
                     f"returned_by={returned} repair_rows={s['repair_rows']}")
        w = nudge_window(rows, task_type, model, effort, args.min_fails)
        if w["fire"]:
            lines.append(f"suggest:\t{task_type}\t{model}:{effort} {nudge_text(w)}; "
                         "consider a different tier or family for this row")
        if s["mismatch"]:
            lines.append(f"suggest:\talias for {model} moved; update aliases in claude-models.json")
    if unclassified:
        lines.append(f"suggest:\t{len(unclassified)} legacy rows have first_pass=false with no returned_by; "
                     "classify with `route.py correct`: "
                     + "; ".join(f"{Path(str(r.get('plan'))).name} {r.get('task')} {r.get('date')}"
                                 for r in unclassified))
    if bad_hosts:
        lines.append(f"suggest:\t{len(bad_hosts)} rows have a host outside {', '.join(HOSTS)}; fix with "
                     "`route.py correct --host`: "
                     + "; ".join(f"{Path(str(r.get('plan'))).name} {r.get('task')} host={r.get('host')}"
                                 for r in bad_hosts))
    return lines or ["no outcomes recorded yet"]


def check_model(args) -> str:
    seen = set()
    try:
        for line in Path(args.transcript).read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            msg = entry.get("message")
            if entry.get("type") == "assistant" and isinstance(msg, dict) and msg.get("model"):
                if not str(msg["model"]).startswith("<"):  # skip synthetic placeholders
                    seen.add(msg["model"])
    except OSError:
        return "n/a"
    if not seen:
        return "n/a"
    other = sorted(m for m in seen if m != args.expect)
    return f"mismatch:{','.join(other)}" if other else "ok"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("resolve")
    p.add_argument("--task-type", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--project")
    p.add_argument("--named")
    p.add_argument("--roster")
    sub.add_parser("validate")
    p = sub.add_parser("log")
    for flag in ("--plan", "--task", "--task-type", "--host", "--project", "--model", "--effort",
                 "--route", "--source"):
        p.add_argument(flag, required=True)
    p.add_argument("--first-pass", required=True, choices=("yes", "no"))
    p.add_argument("--returned-by")
    p.add_argument("--repairs", required=True, type=int)
    p.add_argument("--repaired-by", default="original", choices=REPAIRED_BY)
    p.add_argument("--repairs-of")
    p.add_argument("--status", required=True, choices=("complete", "done", "partial", "blocked"))
    p.add_argument("--escalated-to")
    p.add_argument("--model-check", default="n/a")
    p.add_argument("--note")
    p = sub.add_parser("correct")
    p.add_argument("--plan", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--date")
    p.add_argument("--host")
    p.add_argument("--first-pass", choices=("yes", "no"))
    p.add_argument("--returned-by")
    p.add_argument("--repairs", type=int)
    p.add_argument("--repaired-by", choices=REPAIRED_BY)
    p.add_argument("--repairs-of")
    p.add_argument("--note", required=True)
    p = sub.add_parser("review")
    p.add_argument("--min-fails", type=int, default=3)
    p = sub.add_parser("nudge")
    p.add_argument("--task-type", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--effort", required=True)
    p.add_argument("--min-fails", type=int, default=3)
    p = sub.add_parser("check-model")
    p.add_argument("--transcript", required=True)
    p.add_argument("--expect", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "resolve":
            print(json.dumps(resolve(args), indent=2))
        elif args.cmd == "validate":
            findings = validate(args)
            for f in findings:
                print(f"routing\t{f}")
            print(f"routing_validate={'clean' if not findings else 'findings'} count={len(findings)}")
            return 1 if findings else 0
        elif args.cmd == "log":
            print(json.dumps(log(args)))
        elif args.cmd == "correct":
            print(json.dumps(correct(args)))
        elif args.cmd == "review":
            print("\n".join(review(args)))
        elif args.cmd == "nudge":
            w = nudge_window(read_outcomes(), args.task_type, args.model, args.effort, args.min_fails)
            if w["fire"]:
                print(f"nudge: {args.task_type} on {args.model}:{args.effort} {nudge_text(w)}; "
                      "run `route.py review` and consider changing that row")
                return 1
        elif args.cmd == "check-model":
            print(check_model(args))
    except Exit as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
