#!/usr/bin/env python3
"""Contract tests for the manifest validator.

Every check here replaces something the dispatcher would otherwise have to catch by
eye at low effort. The negative cases matter more than the positive one.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate-manifest.py"
_spec = importlib.util.spec_from_file_location("validate_manifest", SCRIPT)
validate_manifest = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["validate_manifest"] = validate_manifest
_spec.loader.exec_module(validate_manifest)

ManifestError = validate_manifest.ManifestError
GROK_CATALOG = validate_manifest.GROK_CATALOG
GROK = "grok-4.6"

CTX = "/private/tmp/warfleet-test/mission-context.md"


def muster() -> dict:
    return {
        "raw_answers": {
            "fleet_admiral": "Opus 5 High",
            "general": "GPT Sol High",
            "infantry": "Grok 4.6 high, Luna xhigh",
            "infantry_subagents": "Vibin",
        },
        "admirals": [{"family": "claude", "model": "claude-opus-5", "effort": "high", "speed": "standard"}],
        "secondary_admiral": False,
        "general": {"family": "gpt", "model": "gpt-5.6-sol", "effort": "high", "speed": "standard"},
        "infantry": [
            {"family": "grok", "model": GROK, "effort": "high", "speed": "standard"},
            {"family": "gpt", "model": "gpt-5.6-luna", "effort": "xhigh", "speed": "standard"},
        ],
        "infantry_subagents": {"stance": "vibin", "raw": "Vibin"},
        "allocation": {"mode": "task_fit"},
    }


def task(task_id: str, wave: int, family: str = "grok", **overrides) -> dict:
    identity = {
        "grok": {"model": GROK, "effort": "high", "speed": "standard", "executor": "grok-cli"},
        "gpt": {"model": "gpt-5.6-luna", "effort": "xhigh", "speed": "standard", "executor": "native-agent"},
        "claude": {"model": "claude-opus-5", "effort": "high", "speed": "standard", "executor": "claude-cli"},
        "sol": {"family": "gpt", "model": "gpt-5.6-sol", "effort": "high", "speed": "standard", "executor": "native-agent"},
    }[family]
    base = {
        "id": task_id,
        "wave": wave,
        "family": "gpt" if family == "sol" else family,
        "lane": "A",
        "context_file": CTX,
        "task_file": f"/private/tmp/warfleet-test/warfleet-task-{task_id}.md",
        "output_file": f"/private/tmp/warfleet-test/warfleet-out-{task_id}.json",
        "thread_id": f"thread-{task_id}",
        "argv": f"# warfleet-task:{task_id}",
        "dependencies": [],
        "acceptance": ["Reports the requested finding"],
        "subagents": {"max_total": 2, "parallel": True, "rationale": "Independent research improves coverage."},
        **identity,
    }
    base.update(overrides)
    return base


def manifest(*tasks: dict) -> dict:
    data = {"muster": muster(), "mission_context": CTX, "tasks": list(tasks or (task("t1", 1),))}
    # Synthetic capability evidence, not a claim about this test host's runtime.
    data["native_agent_capabilities"] = {
        "evidence": "fixture schema with explicit model/effort/lane/speed controls",
        "models": {"gpt-5.6-luna": ["xhigh"], "gpt-5.6-sol": ["high"]},
        "lanes": ["A", "B"], "speeds": ["standard"],
    }
    # A sol task is outside the default infantry roster unless the caller extends it.
    if any(t.get("model") == "gpt-5.6-sol" for t in data["tasks"]):
        data["muster"] = copy.deepcopy(data["muster"])
        data["muster"]["infantry"].append(
            {"family": "gpt", "model": "gpt-5.6-sol", "effort": "high", "speed": "standard"}
        )
    return data


def args(**overrides) -> argparse.Namespace:
    base = dict(host="codex", roster=None, auth=None, grok_model=GROK, grok_catalog=GROK_CATALOG,
                gpt_model=[], model=[], supported_effort=[])
    base.update(overrides)
    return argparse.Namespace(**base)


class ValidatorHarness(unittest.TestCase):
    def check(self, data: dict, **arg_overrides) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "warfleet-launch.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                validate_manifest.validate(path, args(**arg_overrides))

    def check_fails(self, data: dict, needle: str, **arg_overrides) -> None:
        with self.assertRaises(ManifestError) as ctx:
            self.check(data, **arg_overrides)
        self.assertIn(needle, str(ctx.exception))

    def write_auth(self, tmp: str, entries: list[dict]) -> str:
        path = Path(tmp) / "auth.json"
        path.write_text(json.dumps({"session_id": "abc-123", "approved": entries}), encoding="utf-8")
        return str(path)


class HappyPathTests(ValidatorHarness):
    def test_a_well_formed_manifest_validates(self) -> None:
        self.check(manifest(task("t1", 1), task("t2", 2, dependencies=["t1"])))

    def test_a_luna_task_validates_on_current_native_surface(self) -> None:
        self.check(manifest(task("t1", 1, family="gpt")))

    def test_a_sol_task_validates_on_native_agent(self) -> None:
        self.check(manifest(task("t1", 1, family="sol")))


class ExecutorTests(ValidatorHarness):
    def test_fast_gpt_requires_codex_cli(self) -> None:
        data = manifest(task("t1", 1, family="gpt", speed="fast", executor="codex-cli"))
        data["muster"]["infantry"][1]["speed"] = "fast"
        self.check(data)

    def test_lane_c_gpt_requires_codex_cli(self) -> None:
        self.check(manifest(task("t1", 1, family="gpt", lane="C", executor="codex-cli")))

    def test_sol_can_use_approved_codex_cli(self) -> None:
        self.check(manifest(task("t1", 1, family="sol", executor="codex-cli")))

    def test_cli_works_without_any_native_surface(self) -> None:
        data = manifest(task("t1", 1, family="gpt", executor="codex-cli"))
        del data["native_agent_capabilities"]
        self.check(data)

    def test_native_requires_evidence(self) -> None:
        data = manifest(task("t1", 1, family="gpt"))
        del data["native_agent_capabilities"]
        self.check_fails(data, "requires current capability evidence")

    def test_native_missing_each_requested_control_is_rejected(self) -> None:
        for key in ("models", "lanes", "speeds"):
            with self.subTest(key=key):
                data = manifest(task("t1", 1, family="gpt"))
                del data["native_agent_capabilities"][key]
                self.check_fails(data, "cannot satisfy recorded")

    def test_native_unsupported_effort_is_rejected(self) -> None:
        data = manifest(task("t1", 1, family="gpt"))
        data["native_agent_capabilities"]["models"]["gpt-5.6-luna"] = ["low"]
        self.check_fails(data, "cannot satisfy recorded")

    def test_route_fallback_does_not_change_approved_lane_or_executor(self) -> None:
        for field, value in (("lane", "B"), ("executor", "native-agent")):
            data = manifest(task("t1", 1, family="gpt", executor="codex-cli"))
            data["approved_roster"] = [{"id": "t1", field: value}]
            self.check_fails(data, "silent " + field + " substitution")

    def test_family_and_executor_must_agree(self) -> None:
        self.check_fails(manifest(task("t1", 1, family="grok", executor="claude-cli")),
                         "must use executor grok-cli")

    def test_argv_is_required(self) -> None:
        data = manifest(task("t1", 1))
        data["tasks"][0]["argv"] = ""
        self.check_fails(data, "argv is required")


class ClaudeHostTests(ValidatorHarness):
    """Claude Code has no native GPT agent surface; every GPT task is codex-cli."""

    def test_native_agent_is_rejected_on_claude_host(self) -> None:
        self.check_fails(manifest(task("t1", 1, family="gpt")),
                         "require executor codex-cli", host="claude")

    def test_gpt_on_codex_cli_validates_on_claude_host(self) -> None:
        data = manifest(task("t1", 1, family="gpt", executor="codex-cli"))
        del data["native_agent_capabilities"]
        self.check(data, host="claude")

    def test_other_hosts_follow_wrapper_only_rules(self) -> None:
        self.check_fails(manifest(task("t1", 1, family="gpt")),
                         "require executor codex-cli", host="other")

    def test_non_gpt_families_are_host_independent(self) -> None:
        self.check(manifest(task("t1", 1)), host="claude")


class WaveAndDependencyTests(ValidatorHarness):
    def test_two_tasks_editing_one_file_in_one_wave_are_rejected(self) -> None:
        collide = "/repo/src/app.ts"
        self.check_fails(
            manifest(task("t1", 1, edit_files=[collide]), task("t2", 1, edit_files=[collide])),
            "edit the same file",
        )

    def test_the_same_file_in_different_waves_is_fine(self) -> None:
        collide = "/repo/src/app.ts"
        self.check(manifest(task("t1", 1, edit_files=[collide]), task("t2", 2, edit_files=[collide])))

    def test_a_dependency_in_the_same_wave_is_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1), task("t2", 1, dependencies=["t1"])),
                         "same or a later wave")

    def test_a_dependency_outside_the_roster_is_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1, dependencies=["ghost"])), "outside the roster")

    def test_duplicate_task_ids_are_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1), task("t1", 2)), "duplicate task id")


class IdentityTests(ValidatorHarness):
    def test_a_model_outside_the_muster_is_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1, family="gpt", model="gpt-5.6-terra", effort="high",
                                       executor="native-agent")),
                         "outside the approved Infantry roster")

    def test_an_unknown_model_is_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1, family="gpt", model="gpt-4o", executor="codex-cli")),
                         "not in the approved catalog")

    def test_grok_4_6_accepts_xhigh(self) -> None:
        data = manifest(task("t1", 1, effort="xhigh"))
        data["muster"]["infantry"][0]["effort"] = "xhigh"
        self.check(data)

    def test_grok_4_5_rejects_xhigh(self) -> None:
        data = manifest(task("t1", 1, model="grok-4.5", effort="xhigh"))
        data["muster"]["infantry"][0].update(model="grok-4.5", effort="xhigh")
        self.check_fails(data, "not supported by grok-4.5")

    def test_grok_4_5_is_still_launchable_at_its_own_tiers(self) -> None:
        data = manifest(task("t1", 1, model="grok-4.5", effort="medium"))
        data["muster"]["infantry"][0].update(model="grok-4.5", effort="medium")
        self.check(data)

    def test_grok_has_no_fast_mode(self) -> None:
        self.check_fails(manifest(task("t1", 1, speed="fast")), "no fast-mode control")

    def test_a_newly_resolved_id_is_honored_when_passed_in(self) -> None:
        # Deliberately uncatalogued id: a real release gets a grok-models.json row
        # (as grok-4.7 did), which would replace the family fallback under test.
        data = manifest(task("t1", 1, model="grok-9.9"))
        data["muster"]["infantry"][0]["model"] = "grok-9.9"
        self.check(data, grok_model="grok-9.9")

    def test_claude_fast_mode_is_opus_only(self) -> None:
        data = manifest(task("t1", 1, family="claude", model="claude-sonnet-5", effort="high",
                             speed="fast", executor="claude-cli"))
        data["muster"]["infantry"] = [
            {"family": "claude", "model": "claude-sonnet-5", "effort": "high", "speed": "fast"}
        ]
        self.check_fails(data, "fast mode is supported only by Opus")


class SubagentBudgetTests(ValidatorHarness):
    def test_a_missing_budget_is_rejected(self) -> None:
        data = manifest(task("t1", 1))
        del data["tasks"][0]["subagents"]
        self.check_fails(data, "subagents budget object is required")

    def test_a_negative_ceiling_is_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1, subagents={"max_total": -1, "parallel": False, "rationale": "x"})),
                         "non-negative integer")

    def test_a_missing_rationale_is_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1, subagents={"max_total": 2, "parallel": True, "rationale": "  "})),
                         "rationale is required")

    def test_zero_budget_cannot_be_parallel(self) -> None:
        self.check_fails(manifest(task("t1", 1, subagents={"max_total": 0, "parallel": True, "rationale": "x"})),
                         "must be false when max_total is zero")

    def test_zero_budget_serial_is_allowed(self) -> None:
        self.check(manifest(task("t1", 1, subagents={"max_total": 0, "parallel": False,
                                                     "rationale": "Delegation adds nothing here."})))


class ContextAndBrowserTests(ValidatorHarness):
    def test_context_file_must_match_the_mission_context(self) -> None:
        self.check_fails(manifest(task("t1", 1, context_file="/private/tmp/other.md")),
                         "must match manifest mission_context")

    def test_relative_paths_are_rejected(self) -> None:
        self.check_fails(manifest(task("t1", 1, task_file="warfleet-task-t1.md")), "must be absolute")

    def test_a_browser_task_can_never_be_assigned_to_a_unit(self) -> None:
        self.check_fails(manifest(task("t1", 1, browser=True, lane="C")),
                         "browser work belongs to the dispatcher")


class AuthCrossCheckTests(ValidatorHarness):
    def test_a_matching_auth_file_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth = self.write_auth(tmp, [{"task": "t1", "model": GROK, "effort": "high", "speed": "standard"}])
            self.check(manifest(task("t1", 1)), auth=auth)

    def test_a_missing_auth_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth = self.write_auth(tmp, [{"task": "t9", "model": GROK, "effort": "high"}])
            self.check_fails(manifest(task("t1", 1)), "no auth entry", auth=auth)

    def test_a_shorthand_model_in_the_auth_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth = self.write_auth(tmp, [{"task": "t1", "model": "grok", "effort": "high"}])
            self.check_fails(manifest(task("t1", 1)), "auth model", auth=auth)

    def test_a_tier_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth = self.write_auth(tmp, [{"task": "t1", "model": GROK, "effort": "medium"}])
            self.check_fails(manifest(task("t1", 1)), "auth effort", auth=auth)

    def test_extra_auth_entries_are_allowed_for_pre_approved_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth = self.write_auth(tmp, [
                {"task": "t1", "model": GROK, "effort": "high", "speed": "standard"},
                {"task": "t1-fallback", "model": "gpt-5.6-luna", "effort": "xhigh", "speed": "standard"},
            ])
            self.check(manifest(task("t1", 1)), auth=auth)


class ArgvBindingTests(ValidatorHarness):
    WRAP = str(validate_manifest.WRAPPER_DIR / "run-codex.sh")

    def argv(self, model="gpt-5.6-luna", effort="xhigh", lane="A", extra="") -> str:
        return (f'{self.WRAP} --cwd /w --model {model} --effort {effort} --speed standard '
                f'--lane {lane} --prompt-file /p {extra} > /o 2>&1   # warfleet-task:t1')

    def gpt(self, argv: str) -> dict:
        return manifest(task("t1", 1, "gpt", executor="codex-cli", argv=argv))

    def test_matching_wrapper_argv_validates(self) -> None:
        self.check(self.gpt(self.argv()))

    def test_argv_contradicting_metadata_is_rejected(self) -> None:
        # The A2 fixture: metadata luna/xhigh/lane A, argv sol/high/lane C with approval.
        data = self.gpt(self.argv("gpt-6.1-sol", "high", "C", "--approve-lane-c yes"))
        self.check_fails(data, "argv --model")
        for argv, needle in (
            (self.argv(model="gpt-5.6-sol"), "argv --model"),
            (self.argv(effort="high"), "argv --effort"),
            (self.argv(lane="B"), "argv --lane"),
            (self.argv(extra="--approve-lane-c yes"), "only valid on lane C"),
            (self.argv().replace("--speed standard", "--speed fast"), "argv --speed"),
        ):
            with self.subTest(needle=needle):
                self.check_fails(self.gpt(argv), needle)

    def test_unapproved_executable_is_rejected(self) -> None:
        for exe in ("/Users/x/other/run-codex.sh", "different-wrapper.sh", "run-codex.sh",
                    "/usr/bin/env"):
            with self.subTest(exe=exe):
                self.check_fails(self.gpt(self.argv().replace(self.WRAP, exe)), "not an approved headless wrapper")
        self.check_fails(self.gpt(f"cd /w && {self.argv()}".replace(" > /o", " && ./evil.sh > /o")), "not an approved headless wrapper")

    def test_every_command_across_newlines_is_validated(self) -> None:
        base = self.argv()
        self.check_fails(self.gpt(base + "\n./unapproved-command"), "not an approved headless wrapper")
        self.check_fails(self.gpt(base.replace("   # warfleet", "\n./unapproved-command   # warfleet")),
                         "not an approved headless wrapper")
        self.check_fails(self.gpt(base + "\n" + base), "exactly one wrapper")
        self.check(self.gpt(base + "\n# another comment"))  # a comment line is not a command
        self.check(self.gpt(base.replace("--prompt-file /p", "--prompt-file '/p q\nr'")))  # quoted newline

    def test_unparsed_shell_constructs_are_rejected(self) -> None:
        for extra in ("; ./x", "| tee /o", "|| true", "& ./x", "`./x`", "$(./x)", "< /in", "( ./x )"):
            with self.subTest(extra=extra):
                self.check_fails(self.gpt(self.argv().replace(" > /o", f" {extra} > /o")),
                                 "does not parse")
        # Single-quoted text is literal, not substitution.
        self.check(self.gpt(self.argv().replace("--prompt-file /p", "--prompt-file '/p$(x)'")))

    def test_valid_shell_forms_pass(self) -> None:
        base = self.argv()
        self.check(self.gpt(base.replace("--model gpt", "--model \\\ngpt")))             # backslash-newline continuation
        self.check(self.gpt('FOO="a\nb" ' + base))                                        # assignment value spanning a newline
        self.check(self.gpt(base.replace("--prompt-file /p", "--prompt-file '/p|q;r'")))  # quoted operator characters are literal
        self.check(self.gpt(base.replace("--prompt-file /p", '--prompt-file "/p|q"')))

    def test_unquoted_operator_after_quoted_one_still_rejected(self) -> None:
        argv = self.argv().replace("--prompt-file /p", "--prompt-file '/p|q' | tee /x")
        self.check_fails(self.gpt(argv), "does not parse")

    def test_env_prefix_and_cd_are_allowed(self) -> None:
        self.check(self.gpt(f"cd /w && FOO=1 {self.argv()}"))

    def test_grok_reasoning_effort_alias_matches_effort(self) -> None:
        grok = str(validate_manifest.WRAPPER_DIR / "run-grok.sh")
        base = f"{grok} --cwd /w --lane A --model {GROK} %s high --prompt-file /p"
        self.check(manifest(task("t1", 1, argv=base % "--reasoning-effort")))
        self.check(manifest(task("t1", 1, argv=base % "--effort")))
        self.check_fails(manifest(task("t1", 1, argv=(base % "--reasoning-effort").replace("high --prompt", "low --prompt"))),
                         "argv --effort")

    def test_wrapper_must_match_executor(self) -> None:
        self.check_fails(self.gpt(self.argv().replace("run-codex.sh", "run-grok.sh")), "wrapper does not match")

    def test_auth_arguments_must_match_when_auth_entries_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth = self.write_auth(tmp, [{"task": "t1", "model": "gpt-5.6-luna", "effort": "xhigh", "speed": "standard"}])
            good = self.argv(extra=f"--auth {auth} --task-id t1")
            self.check(self.gpt(good), auth=auth)
            self.check_fails(self.gpt(self.argv()), "argv --task-id", auth=auth)
            self.check_fails(self.gpt(self.argv(extra=f"--auth {auth} --task-id t2")), "argv --task-id", auth=auth)
            self.check_fails(self.gpt(self.argv(extra=f"--auth {tmp}/other.json --task-id t1")), "argv --auth", auth=auth)


class MusterBlockTests(ValidatorHarness):
    def test_a_manifest_without_the_canonical_muster_is_rejected(self) -> None:
        data = manifest(task("t1", 1))
        del data["muster"]
        self.check_fails(data, "canonical muster object")

    def test_raw_answers_must_survive_into_the_manifest(self) -> None:
        data = manifest(task("t1", 1))
        data["muster"]["raw_answers"]["infantry"] = ""
        self.check_fails(data, "four non-empty raw answers")

    def test_the_secondary_admiral_flag_must_match_the_admiral_count(self) -> None:
        data = manifest(task("t1", 1))
        data["muster"]["secondary_admiral"] = True
        self.check_fails(data, "contradicts the Admiral count")

    def test_task_fit_allocation_must_not_carry_shares(self) -> None:
        data = manifest(task("t1", 1))
        data["muster"]["infantry"][0]["share"] = 70
        self.check_fails(data, "must not contain Infantry shares")


class RosterDriftTests(ValidatorHarness):
    def test_a_silent_lane_substitution_is_rejected(self) -> None:
        data = manifest(task("t1", 1, lane="C"))
        data["approved_roster"] = [dict(copy.deepcopy(data["tasks"][0]), lane="A")]
        self.check_fails(data, "silent lane substitution")

    def test_a_task_outside_the_approved_roster_is_rejected(self) -> None:
        data = manifest(task("t1", 1), task("t2", 2))
        data["approved_roster"] = [{"id": "t1"}]
        self.check_fails(data, "outside the approved roster")


if __name__ == "__main__":
    unittest.main()
