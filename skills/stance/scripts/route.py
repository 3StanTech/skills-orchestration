#!/usr/bin/env python3
"""Tier resolver, menu, validator and outcome log (any host; stdlib only).

  route.py resolve --task-type T --host H [--named M:E[:S]] [--roster M:E[:S]]
  route.py menu [--family claude|gpt|grok]
  route.py validate
  route.py log --plan P --task ID --task-type T --host H --project DIR --model M --effort E
               --route R --source S --first-pass yes|no --repairs N --status S
               [--returned-by acceptance,seam,review,dispatcher-check|none]
               [--repaired-by original|fresh-helper|dispatcher|escalation] [--repairs-of TASK]
               [--escalated-to M] [--model-check ok|mismatch:<id>|n/a] [--note "<evidence>"]
  route.py correct --plan P --task ID [--date D] [--host H] [--first-pass yes|no] [--returned-by ...]
               [--repairs N] [--repaired-by ...] [--repairs-of TASK] --note "<evidence>"
  route.py review
  route.py check-model --transcript FILE --expect ID

There is no tier table: a tier is the one the owner names in the request, else the approved plan
roster's, else `resolve` exits 3 and the agent asks the owner for model + effort.
Availability per family comes from headless/data/families.json (per user, untracked; a missing
file or family means active). A named tier on an inactive family resolves (the owner's call);
a roster tier on one exits 3.

Exit codes: 0 ok; 1 findings (validate); 2 invalid input; 3 needs the owner (no tier named,
or a roster tier on an inactive family). Rules: ~/.agents/skills/stance/references/routes.md.
Paths can be overridden for tests with ROUTE_FAMILIES, ROUTE_OUTCOMES, ROUTE_CLAUDE_CATALOG,
ROUTE_GROK_CATALOG and ROUTE_GPT_CATALOG (a saved `codex debug models --bundled` output).
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HOME = Path.home()
FAMILIES = Path(os.environ.get("ROUTE_FAMILIES", HOME / ".agents/skills/headless/data/families.json"))
OUTCOMES = Path(os.environ.get("ROUTE_OUTCOMES", HOME / ".agents/state/outcomes.jsonl"))
CLAUDE_CATALOG = Path(os.environ.get("ROUTE_CLAUDE_CATALOG", HOME / ".agents/skills/headless/data/claude-models.json"))
GROK_CATALOG = Path(os.environ.get("ROUTE_GROK_CATALOG", HOME / ".agents/skills/headless/data/grok-models.json"))
GPT_CATALOG = os.environ.get("ROUTE_GPT_CATALOG")
# The Codex wrapper owns which GPT identities may launch; menu and resolve read its rule.
CODEX_WRAPPER = Path(__file__).resolve().parents[2] / "headless/scripts/run-codex.sh"

HOSTS = ("claude", "codex", "grok", "hermes", "pi", "other")
NATIVE_FAMILY = {"claude": "claude", "codex": "gpt", "grok": "grok"}
ENGINE = {"claude": "claude", "gpt": "codex", "grok": "grok"}
FAMILY_NAMES = tuple(ENGINE)
TASK_TYPES = ("plan", "mechanical", "standard", "hard", "review", "network", "visual")
RETURNED_BY = ("acceptance", "seam", "review", "dispatcher-check")
REPAIRED_BY = ("original", "fresh-helper", "dispatcher", "escalation")
CORRECTABLE = ("host", "first_pass", "returned_by", "repairs", "repaired_by", "repairs_of")


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


def codex_launchable() -> list[str]:
    """The model globs run-codex.sh accepts (its `case "$model" in` arm that does not exit)."""
    try:
        text = CODEX_WRAPPER.read_text(encoding="utf-8")
    except OSError as exc:
        raise Exit(2, f"gpt launch rule unavailable: {exc}")
    m = re.search(r'case "\$model" in\s*\n\s*([^)\n]+)\)\s*;;', text)
    if not m:
        raise Exit(2, f"gpt launch rule unavailable: no approved-model case in {CODEX_WRAPPER}")
    return [g.strip() for g in m.group(1).split("|")]


def not_installed(fam: str) -> bool:
    """True when a family's catalog source is simply absent on this machine (not broken).

    Only GPT has an external source (the Codex CLI); the Claude and Grok catalogs ship as files
    in the headless skill, so a missing one is a broken install, not an absent CLI."""
    return fam == "gpt" and not GPT_CATALOG and not shutil.which("codex")


def gpt_catalog() -> dict[str, dict]:
    """Launchable GPT identities only: the wrapper's family rule, minus models Codex hides
    (internal or routing aliases are never offered, even when the bundled catalog lists them)."""
    globs = codex_launchable()
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
            for m in data.get("models", [])
            if m.get("visibility", "list") != "hide" and any(fnmatch.fnmatchcase(m["slug"], g) for g in globs)}


class Catalogs:
    def __init__(self):
        self._cache: dict[str, dict] = {}

    def claude(self) -> dict:
        if "claude" not in self._cache:
            self._cache["claude"] = load_json(CLAUDE_CATALOG)
        return self._cache["claude"]

    def models(self, fam: str) -> dict[str, dict]:
        try:
            if fam == "claude":
                return self.claude()["models"]
            if fam not in self._cache:
                if fam == "gpt":
                    self._cache[fam] = gpt_catalog()
                elif fam == "grok":
                    self._cache[fam] = {k: {"efforts": v["efforts"], "fast": False}
                                        for k, v in load_json(GROK_CATALOG)["models"].items()}
            return self._cache[fam]
        except (KeyError, TypeError, AttributeError, ValueError, OSError) as exc:
            raise Exit(2, f"{fam} catalog is malformed or unreadable: {exc!r}")

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


def route_for(fam: str, host: str, tier: dict, cats: Catalogs) -> tuple[str, str | None]:
    if NATIVE_FAMILY.get(host) == fam:
        if host == "claude":
            alias = next((a for a, mid in cats.aliases().items() if mid == tier["model"]), None)
            # Subagents inherit the session's speed and only take aliases: exact-ID or fast -> headless.
            if alias and tier.get("speed", "standard") == "standard":
                return "subagent", alias
            return "headless:claude", None
        return f"native:{host}", None
    return f"headless:{ENGINE[fam]}", None


def families() -> dict[str, dict]:
    """Per-user availability; a missing file or family reads as active."""
    if not FAMILIES.exists():
        return {}
    root = load_json(FAMILIES)
    data = root.get("families", {}) if isinstance(root, dict) else None
    if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
        raise Exit(2, f"{FAMILIES}: expected {{\"families\": {{\"<family>\": {{\"active\": true|false}}}}}}")
    return data


def is_active(fams: dict, fam: str) -> bool:
    return bool(fams.get(fam, {}).get("active", True))


def resolve(args) -> dict:
    if args.host not in HOSTS:
        raise Exit(2, f"unknown host {args.host!r} (expected one of {', '.join(HOSTS)})")
    if args.task_type not in TASK_TYPES:
        raise Exit(2, f"unknown task type {args.task_type!r} (expected one of {', '.join(TASK_TYPES)})")
    if args.task_type == "visual":
        # Browser capture and visual checks are never delegated.
        return {"task_type": args.task_type, "route": "dispatcher", "source": "built-in"}
    if args.named:
        tier, source = parse_tier(args.named), "named"
    elif args.roster:
        tier, source = parse_tier(args.roster), "roster"
    else:
        raise Exit(3, "no tier named: ask the owner for model + effort")
    cats = Catalogs()
    fam = check_tier(tier, cats, source)
    fams = families()
    # A tier the owner names is their availability call; a roster tier is not.
    if source != "named" and not is_active(fams, fam):
        raise Exit(3, f"family {fam} is inactive ({fams[fam].get('reason', 'no reason recorded')}); "
                      "ask the owner before using it")
    route, alias = route_for(fam, args.host, tier, cats)
    return {"task_type": args.task_type, "source": source, "model": tier["model"],
            "effort": tier["effort"], "speed": tier["speed"], "family": fam, "route": route,
            "subagent_alias": alias, "escalation": None, "fallback": None, "notes": ""}


def menu(args) -> list[str]:
    """One line per model of each active family: `<model-id>\t<efforts>[\tfast]`."""
    if args.family and args.family not in FAMILY_NAMES:
        raise Exit(2, f"unknown family {args.family!r} (expected one of {', '.join(FAMILY_NAMES)})")
    fams, cats = families(), Catalogs()
    lines = []
    for fam in FAMILY_NAMES:
        if (args.family and fam != args.family) or not is_active(fams, fam):
            continue
        if not_installed(fam):
            print(f"menu\t{fam}: skipped, codex is not installed (no catalog source)", file=sys.stderr)
            continue
        # A broken catalog would silently hide a family the owner can use: fail instead.
        for model, spec in cats.models(fam).items():
            lines.append("\t".join([model, ",".join(spec["efforts"])] + (["fast"] if spec.get("fast") else [])))
    return lines


def validate(_args) -> list[str]:
    findings = []
    try:
        fams = families()
    except Exit as exc:
        return [str(exc)]
    for name, status in list(fams.items()):
        if name not in FAMILY_NAMES:
            findings.append(f"families.json: unknown family {name!r} (expected one of {', '.join(FAMILY_NAMES)})")
        elif not isinstance(status.get("active", True), bool):
            findings.append(f"families.json: {name} needs {{\"active\": true|false}}")
    cats = Catalogs()
    for fam in FAMILY_NAMES:
        # The GPT catalog is Codex's own output: checked only where Codex (or a saved copy) exists.
        if not is_active(fams, fam) or not_installed(fam):
            continue
        try:
            models = cats.models(fam)
        except Exit as exc:
            findings.append(f"{fam} catalog: {exc}")
            continue
        for model, spec in models.items():
            if not isinstance(spec, dict) or not spec.get("efforts"):
                findings.append(f"{fam} catalog: {model} has no efforts")
    try:
        for alias, mid in cats.aliases().items():
            if mid not in cats.models("claude"):
                findings.append(f"alias {alias} -> {mid}: not a claude catalog row")
    except Exit:
        pass  # already reported as a claude catalog finding
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
    p.add_argument("--named")
    p.add_argument("--roster")
    p = sub.add_parser("menu")
    p.add_argument("--family")
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
    sub.add_parser("review")
    p = sub.add_parser("check-model")
    p.add_argument("--transcript", required=True)
    p.add_argument("--expect", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "resolve":
            print(json.dumps(resolve(args), indent=2))
        elif args.cmd == "menu":
            lines = menu(args)
            if lines:
                print("\n".join(lines))
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
        elif args.cmd == "check-model":
            print(check_model(args))
    except Exit as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
