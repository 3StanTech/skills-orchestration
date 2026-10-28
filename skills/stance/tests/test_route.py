#!/usr/bin/env python3
"""Tier rules: named > roster > ask, family availability, host mapping, catalog checks, menu,
outcome aggregation.

Runs route.py as a subprocess against fixture catalogs and a temporary families file, so the real
families.json, catalogs and outcome log are never read or written.
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

FAMILIES = {"families": {"claude": {"active": True}, "gpt": {"active": True},
                         "grok": {"active": False, "reason": "no subscription"}}}


class RouteHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.families = json.loads(json.dumps(FAMILIES))
        self.write_families()
        self.env = dict(os.environ, ROUTE_FAMILIES=str(self.dir / "families.json"),
                        ROUTE_OUTCOMES=str(self.dir / "outcomes.jsonl"),
                        ROUTE_CLAUDE_CATALOG=str(FIX / "claude-models.json"),
                        ROUTE_GROK_CATALOG=str(FIX / "grok-models.json"),
                        ROUTE_GPT_CATALOG=str(FIX / "gpt-models.txt"))

    def tearDown(self):
        self.tmp.cleanup()

    def write_families(self):
        (self.dir / "families.json").write_text(json.dumps(self.families))

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


class TierSource(RouteHarness):
    def test_no_tier_named_asks_the_owner(self):
        for task_type in ("plan", "standard", "review", "network"):
            with self.subTest(task_type=task_type):
                self.assertIn("ask the owner for model + effort", self.resolve_fails(3, task_type))

    def test_named_beats_roster(self):
        out = self.resolve("standard", "claude", "--roster", "gpt-6.1-sol:low", "--named", "claude-opus-5-5:low")
        self.assertEqual((out["source"], out["model"], out["effort"]), ("named", "claude-opus-5-5", "low"))

    def test_roster_when_nothing_named(self):
        out = self.resolve("standard", "claude", "--roster", "gpt-6.1-sol:low")
        self.assertEqual((out["source"], out["model"], out["route"]), ("roster", "gpt-6.1-sol", "headless:codex"))

    def test_named_gives_route_and_alias_with_no_preset_ladder(self):
        out = self.resolve("hard", "claude", "--named", "claude-sonnet-5-5:medium")
        self.assertEqual((out["route"], out["subagent_alias"], out["speed"]), ("subagent", "sonnet", "standard"))
        self.assertIsNone(out["escalation"])
        self.assertIsNone(out["fallback"])

    def test_project_flag_is_gone(self):
        self.resolve_fails(2, "standard", "claude", "--project", str(self.dir), "--named", "claude-sonnet-5-5:high")

    def test_visual_is_dispatcher_only_without_a_tier(self):
        self.assertEqual(self.resolve("visual", "codex")["route"], "dispatcher")


class Families(RouteHarness):
    def test_roster_tier_on_inactive_family_needs_owner(self):
        self.assertIn("inactive (no subscription)", self.resolve_fails(3, "network", "claude", "--roster", "grok-4.6:high"))

    def test_named_inactive_family_is_the_owners_call(self):
        out = self.resolve("standard", "claude", "--named", "grok-4.6:high")
        self.assertEqual(out["route"], "headless:grok")

    def test_missing_file_or_family_means_active(self):
        del self.families["families"]["grok"]
        self.write_families()
        self.assertEqual(self.resolve("standard", "claude", "--roster", "grok-4.6:high")["family"], "grok")
        (self.dir / "families.json").unlink()
        self.assertEqual(self.resolve("standard", "claude", "--roster", "grok-4.6:high")["family"], "grok")

    def test_unknown_effort_and_model_are_invalid(self):
        self.resolve_fails(2, "standard", "claude", "--named", "claude-sonnet-5-5:max")
        self.resolve_fails(2, "standard", "claude", "--named", "claude-nope-1:high")
        self.resolve_fails(2, "standard", "claude", "--named", "mistral-7b:high")
        self.resolve_fails(2, "standard", "claude", "--named", "claude-sonnet-5-5")

    def test_fast_only_where_catalog_allows(self):
        self.resolve_fails(2, "standard", "claude", "--named", "claude-sonnet-5-5:high:fast")
        self.assertEqual(self.resolve("standard", "claude", "--named", "gpt-6.1-sol:high:fast")["speed"], "fast")

    def test_unknown_task_type_and_host(self):
        self.resolve_fails(2, "nonsense", "claude", "--named", "claude-sonnet-5-5:high")
        self.resolve_fails(2, "standard", "vscode", "--named", "claude-sonnet-5-5:high")


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


class Menu(RouteHarness):
    def models(self, *extra):
        r = self.run_route("menu", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {line.split("\t")[0]: line.split("\t")[1:] for line in r.stdout.splitlines()}

    def test_lists_active_families_with_efforts(self):
        out = self.models()
        self.assertIn("claude-sonnet-5-5", out)
        self.assertIn("gpt-6.1-sol", out)
        self.assertFalse([m for m in out if m.startswith("grok-")])  # grok is inactive
        self.assertNotIn("max", out["claude-sonnet-5-5"][0].split(","))

    def test_inactive_gpt_disappears_and_family_filter(self):
        self.families["families"]["gpt"] = {"active": False, "reason": "no paid plan"}
        self.write_families()
        out = self.models()
        self.assertFalse([m for m in out if m.startswith("gpt-")])
        self.assertTrue(out)
        self.assertTrue(all(m.startswith("claude-") for m in self.models("--family", "claude")))
        self.assertEqual(self.models("--family", "gpt"), {})
        self.assertEqual(self.run_route("menu", "--family", "mistral").returncode, 2)


class Validate(RouteHarness):
    def test_clean(self):
        r = self.run_route("validate")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("routing_validate=clean count=0", r.stdout)

    def test_rejects_unknown_family_and_bad_active(self):
        self.families["families"]["mistral"] = {"active": True}
        self.families["families"]["gpt"] = {"active": "no"}
        self.write_families()
        r = self.run_route("validate")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("unknown family 'mistral'", r.stdout)
        self.assertIn("gpt needs", r.stdout)

    def test_unreadable_catalog_is_a_finding(self):
        self.env["ROUTE_GROK_CATALOG"] = str(self.dir / "missing.json")
        self.assertEqual(self.run_route("validate").returncode, 0)  # grok inactive: not read
        self.families["families"]["grok"] = {"active": True}
        self.write_families()
        r = self.run_route("validate")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("grok catalog", r.stdout)


class OutcomeLog(RouteHarness):
    def log_args(self, first_pass, task="t1", escalated=None, status="complete", check="ok", host="claude"):
        args = ["log", "--plan", "p.md", "--task", task, "--task-type", "standard", "--host", host,
                "--project", "/x", "--model", "claude-sonnet-5-5", "--effort", "high", "--route", "subagent",
                "--source", "named", "--first-pass", first_pass, "--repairs", "0" if first_pass == "yes" else "1",
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
    def test_review_aggregates_per_task_type_and_tier(self):
        self.log("yes")
        self.log("no", "t2", escalated="gpt-6.1-sol", status="blocked")
        self.log("no", "t3", check="mismatch:claude-sonnet-6")
        out = self.run_route("review").stdout
        self.assertIn("runs=3 first_pass=1/3 escalated=1 blocked=1 model_mismatch=1", out)
        self.assertIn("alias for claude-sonnet-5-5 moved", out)

    def test_review_with_no_log(self):
        self.assertIn("no outcomes recorded yet", self.run_route("review").stdout)


class OutcomeRules(OutcomeLog):
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
