#!/usr/bin/env python3
"""Routing rules: precedence, host mapping, catalog checks, outcome aggregation.

Runs route.py as a subprocess against fixture catalogs and a temporary table, so the real
routing.json, catalogs and outcome log are never read or written.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
ROUTE = HERE.parent / "scripts" / "route.py"
FIX = HERE / "fixtures"

TABLE = {
    "version": 1,
    "families": {"claude": {"active": True}, "gpt": {"active": True},
                 "grok": {"active": False, "reason": "no subscription"}},
    "task_types": {
        "mechanical": {"tier": {"model": "gpt-6-luna", "effort": "low"}, "route": "native",
                       "escalation": {"model": "claude-sonnet-5-5", "effort": "high"}, "fallback": None},
        "standard": {"tier": {"model": "claude-sonnet-5-5", "effort": "high"}, "route": "native",
                     "escalation": {"model": "gpt-6.1-sol", "effort": "high"}, "fallback": None},
        "hard": {"tier": {"model": "claude-opus-5-5", "effort": "max", "speed": "fast"}, "route": "native"},
        "review": {"tier": {"model": "gpt-6.1-sol", "effort": "high"}, "route": "headless"},
        "network": {"tier": {"model": "grok-4.6", "effort": "high"}, "route": "native"},
        "plan": {"tier": None, "route": "native"},
        "visual": {"dispatcher_only": True},
    },
    "projects": {},
}


class RouteHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.project = self.dir / "client-site"
        self.project.mkdir()
        self.table = json.loads(json.dumps(TABLE))
        self.table["projects"] = {str(self.project.resolve()): {"task_types": {
            "standard": {"tier": {"model": "claude-opus-5-5", "effort": "high"}}}}}
        self.write_table()
        self.env = dict(os.environ, ROUTE_TABLE=str(self.dir / "routing.json"),
                        ROUTE_OUTCOMES=str(self.dir / "outcomes.jsonl"),
                        ROUTE_CLAUDE_CATALOG=str(FIX / "claude-models.json"),
                        ROUTE_GROK_CATALOG=str(FIX / "grok-models.json"),
                        ROUTE_GPT_CATALOG=str(FIX / "gpt-models.txt"))

    def tearDown(self):
        self.tmp.cleanup()

    def write_table(self):
        (self.dir / "routing.json").write_text(json.dumps(self.table))

    def run_route(self, *args):
        return subprocess.run(["python3", str(ROUTE), *args], env=self.env, text=True, capture_output=True)

    def resolve(self, task_type, host="claude", *extra):
        r = self.run_route("resolve", "--task-type", task_type, "--host", host, *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def resolve_fails(self, code, task_type, host="claude", *extra):
        r = self.run_route("resolve", "--task-type", task_type, "--host", host, *extra)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r.stderr


class Precedence(RouteHarness):
    def test_named_beats_roster_project_and_global(self):
        out = self.resolve("standard", "claude", "--project", str(self.project),
                           "--roster", "gpt-6.1-sol:low", "--named", "claude-opus-5-5:low")
        self.assertEqual((out["source"], out["model"], out["effort"]), ("named", "claude-opus-5-5", "low"))

    def test_roster_beats_project_and_global(self):
        out = self.resolve("standard", "claude", "--project", str(self.project), "--roster", "gpt-6.1-sol:low")
        self.assertEqual((out["source"], out["model"]), ("roster", "gpt-6.1-sol"))

    def test_project_override_beats_global_and_keeps_global_escalation(self):
        out = self.resolve("standard", "claude", "--project", str(self.project))
        self.assertEqual((out["source"], out["model"]), ("project", "claude-opus-5-5"))
        self.assertEqual(out["escalation"]["model"], "gpt-6.1-sol")

    def test_global_when_project_has_no_override(self):
        out = self.resolve("mechanical", "claude", "--project", str(self.project))
        self.assertEqual((out["source"], out["model"]), ("global", "gpt-6-luna"))

    def test_unfilled_row_needs_owner(self):
        self.assertIn("ask the owner", self.resolve_fails(3, "plan"))

    def test_named_fills_an_unfilled_row(self):
        self.assertEqual(self.resolve("plan", "claude", "--named", "claude-sonnet-5-5:medium")["source"], "named")


class Families(RouteHarness):
    def test_inactive_family_from_table_needs_owner(self):
        self.assertIn("inactive", self.resolve_fails(3, "network"))

    def test_named_inactive_family_is_the_owners_call(self):
        out = self.resolve("standard", "claude", "--named", "grok-4.6:high")
        self.assertEqual(out["route"], "headless:grok")

    def test_unknown_effort_and_model_are_invalid(self):
        self.resolve_fails(2, "standard", "claude", "--named", "claude-sonnet-5-5:max")
        self.resolve_fails(2, "standard", "claude", "--named", "claude-nope-1:high")
        self.resolve_fails(2, "standard", "claude", "--named", "mistral-7b:high")
        self.resolve_fails(2, "standard", "claude", "--named", "claude-sonnet-5-5")

    def test_fast_only_where_catalog_allows(self):
        self.resolve_fails(2, "standard", "claude", "--named", "claude-sonnet-5-5:high:fast")
        self.assertEqual(self.resolve("standard", "claude", "--named", "gpt-6.1-sol:high:fast")["speed"], "fast")

    def test_unknown_task_type_and_host(self):
        self.resolve_fails(2, "nonsense")
        self.resolve_fails(2, "standard", "vscode")


class HostMapping(RouteHarness):
    CASES = [
        # (host, named tier, expected route, expected alias)
        ("claude", "claude-sonnet-5-5:high", "subagent", "sonnet"),
        ("claude", "claude-opus-4-8:high", "headless:claude", None),       # no alias -> exact ID
        ("claude", "claude-opus-5-5:max:fast", "headless:claude", None),    # fast -> headless
        ("claude", "gpt-6.1-sol:high", "headless:codex", None),
        ("codex", "gpt-6.1-sol:high", "native:codex", None),
        ("codex", "claude-sonnet-5-5:high", "headless:claude", None),
        ("grok", "grok-4.6:high", "native:grok", None),
        ("grok", "gpt-6.1-sol:high", "headless:codex", None),
        ("hermes", "claude-sonnet-5-5:high", "headless:claude", None),
        ("pi", "gpt-6.1-sol:high", "headless:codex", None),
        ("other", "grok-4.6:high", "headless:grok", None),
    ]

    def test_route_per_host_and_family(self):
        for host, tier, route, alias in self.CASES:
            with self.subTest(host=host, tier=tier):
                out = self.resolve("standard", host, "--named", tier)
                self.assertEqual((out["route"], out["subagent_alias"]), (route, alias))

    def test_headless_preference_overrides_native(self):
        self.assertEqual(self.resolve("review", "codex")["route"], "headless:codex")

    def test_visual_is_dispatcher_only(self):
        self.assertEqual(self.resolve("visual", "codex")["route"], "dispatcher")


class Validate(RouteHarness):
    def test_reports_bad_tiers_and_missing_projects_not_unfilled_rows(self):
        self.table["task_types"]["mechanical"]["escalation"] = {"model": "claude-sonnet-5-5", "effort": "max"}
        self.table["projects"]["/no/such/folder"] = {"task_types": {}}
        self.write_table()
        r = self.run_route("validate")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("no tier", r.stdout)  # an unfilled row just means "ask"
        self.assertIn("does not accept effort max", r.stdout)
        self.assertIn("/no/such/folder: folder does not exist", r.stdout)
        self.assertNotIn("network", r.stdout)  # inactive family rows are skipped

    def test_escalation_only_row_is_filled(self):
        self.table["task_types"]["plan"]["escalation"] = {"model": "claude-opus-5-5", "effort": "xhigh"}
        self.write_table()
        self.assertNotIn("plan:", self.run_route("validate").stdout)

    def test_clean_table(self):
        self.table["task_types"]["plan"]["tier"] = {"model": "claude-opus-5-5", "effort": "high"}
        self.write_table()
        r = self.run_route("validate")
        self.assertEqual(r.returncode, 0, r.stdout)


class OutcomeLog(RouteHarness):
    def log_args(self, first_pass, task="t1", escalated=None, status="complete", check="ok", host="claude"):
        args = ["log", "--plan", "p.md", "--task", task, "--task-type", "standard", "--host", host,
                "--project", "/x", "--model", "claude-sonnet-5-5", "--effort", "high", "--route", "subagent",
                "--source", "global", "--first-pass", first_pass, "--repairs", "0" if first_pass == "yes" else "1",
                "--status", status, "--model-check", check]
        if first_pass == "no":
            args += ["--returned-by", "acceptance"]
        if escalated:
            args += ["--escalated-to", escalated]
        return args

    def log(self, first_pass, task="t1", escalated=None, status="complete", check="ok", *extra):
        r = self.run_route(*self.log_args(first_pass, task, escalated, status, check), *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class Outcomes(OutcomeLog):
    def test_review_and_nudge_threshold(self):
        self.log("yes")
        self.log("no", "t2", escalated="gpt-6.1-sol", status="blocked")
        self.log("no", "t3", check="mismatch:claude-sonnet-6")
        nudge = ["nudge", "--task-type", "standard", "--model", "claude-sonnet-5-5", "--effort", "high"]
        self.assertEqual(self.run_route(*nudge).returncode, 0)
        out = self.run_route("review").stdout
        self.assertIn("runs=3 first_pass=1/3 escalated=1 blocked=1 model_mismatch=1", out)
        self.assertIn("alias for claude-sonnet-5-5 moved", out)
        self.assertNotIn("failed first pass", out)
        self.log("no", "t4")
        self.assertEqual(self.run_route(*nudge).returncode, 1)
        self.assertIn("failed first pass 3x", self.run_route("review").stdout)

    def test_review_with_no_log(self):
        self.assertIn("no outcomes recorded yet", self.run_route("review").stdout)


class OutcomeRules(OutcomeLog):
    NUDGE = ["nudge", "--task-type", "standard", "--model", "claude-sonnet-5-5", "--effort", "high"]

    def raw_rows(self):
        return [json.loads(l) for l in (self.dir / "outcomes.jsonl").read_text().splitlines()]

    def write_legacy(self, *rows):
        with (self.dir / "outcomes.jsonl").open("a") as fh:
            for r in rows:
                fh.write(json.dumps(dict({"date": "2026-10-01", "host": "claude", "plan": "p.md",
                                          "task_type": "standard", "model": "claude-sonnet-5-5",
                                          "effort": "high", "repairs": 0, "status": "complete"}, **r)) + "\n")

    def test_first_pass_and_returned_by_consistency(self):
        base = self.log_args("yes")
        cases = [
            # (first_pass, returned_by or None, expected exit)
            ("yes", None, 0), ("yes", "none", 0), ("yes", "seam,review", 0), ("yes", "dispatcher-check", 0),
            ("yes", "acceptance", 2), ("yes", "review,acceptance", 2),
            ("no", None, 2), ("no", "review", 2), ("no", "seam,dispatcher-check", 2),
            ("no", "acceptance", 0), ("no", "acceptance,review", 0),
            ("no", "acceptance,none", 2), ("yes", "bogus", 2), ("yes", "", 2),
        ]
        for first_pass, returned, code in cases:
            with self.subTest(first_pass=first_pass, returned=returned):
                args = [a for a in base]
                args[args.index("--first-pass") + 1] = first_pass
                if returned is not None:
                    args += ["--returned-by", returned]
                r = self.run_route(*args)
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)

    def test_stored_fields_and_defaults(self):
        row = self.log("yes")
        self.assertEqual((row["returned_by"], row["repaired_by"], row["repairs_of"]), ([], "original", None))
        row = self.log("no", "t2", None, "complete", "ok", "--returned-by", "review,acceptance,review",
                       "--repaired-by", "fresh-helper", "--repairs-of", "t1")
        self.assertEqual((row["returned_by"], row["repaired_by"], row["repairs_of"]),
                         (["acceptance", "review"], "fresh-helper", "t1"))
        self.assertNotIn("note", row)
        self.assertEqual(self.log("yes", "t3", None, "complete", "ok", "--note", "ev")["note"], "ev")
        r = self.run_route(*self.log_args("yes"), "--repaired-by", "someone")
        self.assertEqual(r.returncode, 2)

    def test_done_alias_is_stored_as_complete(self):
        self.assertEqual(self.log("yes", "t1", None, "done")["status"], "complete")

    def test_host_validation(self):
        for host, code in (("claude", 0), ("pi", 0), ("other", 0), ("claude-code", 2), ("Claude", 2), ("", 2)):
            with self.subTest(host=host):
                self.assertEqual(self.run_route(*self.log_args("yes", host=host)).returncode, code)
        self.log("yes")
        r = self.run_route("correct", "--plan", "p.md", "--task", "t1", "--host", "claude-code", "--note", "x")
        self.assertEqual(r.returncode, 2)

    def test_correction_merge_latest_wins_and_is_not_counted(self):
        self.write_legacy({"task": "a", "first_pass": False, "host": "claude-code"},
                          {"task": "b", "first_pass": True})
        out = self.run_route("review").stdout
        self.assertIn("runs=2 first_pass=1/1", out)
        self.assertIn("unclassified:1", out)
        self.assertIn("p.md a 2026-10-01", out)
        self.assertIn("host=claude-code", out)
        r = self.run_route("correct", "--plan", "p.md", "--task", "a", "--host", "claude", "--note", "host fix")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_route("correct", "--plan", "p.md", "--task", "a", "--first-pass", "yes",
                           "--returned-by", "review", "--note", "evidence: review only")
        self.assertEqual(r.returncode, 0, r.stderr)
        latest = self.raw_rows()[-1]
        self.assertEqual(latest["correction_of"], {"plan": "p.md", "task": "a", "date": "2026-10-01"})
        self.assertEqual((latest["host"], latest["first_pass"], latest["returned_by"]), ("claude", True, ["review"]))
        out = self.run_route("review").stdout
        self.assertIn("runs=2 first_pass=2/2", out)
        self.assertIn("review:1", out)
        self.assertNotIn("legacy rows", out)
        self.assertNotIn("host=", out)
        r = self.run_route("correct", "--plan", "p.md", "--task", "a", "--first-pass", "no",
                           "--returned-by", "acceptance", "--note", "re-read: acceptance failed")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("runs=2 first_pass=1/2", self.run_route("review").stdout)
        self.assertEqual(len(self.raw_rows()), 5)  # append-only: originals untouched

    def test_correct_rejects_bad_input(self):
        self.write_legacy({"task": "a", "first_pass": False}, {"task": "a", "first_pass": True, "date": "2026-10-02"})
        def fails(*args):
            r = self.run_route("correct", "--plan", "p.md", *args, "--note", "n")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        fails("--task", "missing", "--first-pass", "yes")
        fails("--task", "a", "--first-pass", "yes")  # two dates, no --date
        fails("--task", "a", "--date", "2026-10-01")  # nothing to correct
        fails("--task", "a", "--date", "2026-10-01", "--returned-by", "review")  # still first_pass no
        fails("--task", "a", "--date", "2026-10-01", "--first-pass", "no")  # no acceptance
        fails("--task", "a", "--date", "2026-10-02", "--returned-by", "acceptance")  # first_pass yes

    def test_repair_rows_excluded_from_first_pass_stats(self):
        self.log("yes", "t1")
        self.log("no", "r1", None, "complete", "ok", "--repairs-of", "t1", "--repaired-by", "fresh-helper")
        self.assertIn("runs=1 first_pass=1/1", self.run_route("review").stdout)
        self.assertIn("repair_rows=1", self.run_route("review").stdout)

    def run_window(self, passes, fails, legacy_fails=0, repairs=0):
        for i in range(passes):
            self.log("yes", f"p{i}")
        for i in range(fails):
            self.log("no", f"f{i}")
        for i in range(repairs):
            self.log("no", f"r{i}", None, "complete", "ok", "--repairs-of", "f0")
        self.write_legacy(*({"task": f"l{i}", "first_pass": False} for i in range(legacy_fails)))
        return self.run_route(*self.NUDGE).returncode

    def test_nudge_needs_three_acceptance_failures(self):
        self.assertEqual(self.run_window(0, 2), 0)
        self.tearDown(); self.setUp()
        self.assertEqual(self.run_window(0, 3), 1)

    def test_nudge_rate_boundary(self):
        self.assertEqual(self.run_window(3, 3), 0)  # 50%: no nudge
        self.tearDown(); self.setUp()
        self.assertEqual(self.run_window(4, 5), 1)  # 44%: nudge
        self.tearDown(); self.setUp()
        self.assertEqual(self.run_window(5, 5), 0)  # 50% of a full window

    def test_nudge_uses_last_ten_classified_rows(self):
        for i in range(5):
            self.log("no", f"old{i}")
        for i in range(8):
            self.log("yes", f"new{i}")
        # window = 2 fails + 8 passes: 80%, no nudge despite 5 lifetime failures
        self.assertEqual(self.run_route(*self.NUDGE).returncode, 0)
        self.assertNotIn("failed first pass", self.run_route("review").stdout)

    def test_legacy_unclassified_and_repair_rows_do_not_trip_nudge(self):
        self.assertEqual(self.run_window(0, 2, legacy_fails=5, repairs=4), 0)


class CheckModel(RouteHarness):
    def test_ok_mismatch_and_missing(self):
        def check(name):
            return self.run_route("check-model", "--transcript", str(FIX / name),
                                  "--expect", "claude-sonnet-5-5").stdout.strip()
        self.assertEqual(check("transcript-ok.jsonl"), "ok")
        self.assertEqual(check("transcript-moved.jsonl"), "mismatch:claude-sonnet-6")
        self.assertEqual(check("missing.jsonl"), "n/a")


if __name__ == "__main__":
    unittest.main()
