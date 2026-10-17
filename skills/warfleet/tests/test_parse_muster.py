#!/usr/bin/env python3
"""Contract tests for the muster compiler.

The point of the compiler is that a low-effort dispatcher never has to interpret a
muster answer. These tests pin the two halves of that promise: canonical output for
answers it understands, and a hard failure — never a guess — for anything else.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "parse-muster.py"
_spec = importlib.util.spec_from_file_location("parse_muster", SCRIPT)
parse_muster = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# Register before exec: @dataclass resolves its own module out of sys.modules.
sys.modules["parse_muster"] = parse_muster
_spec.loader.exec_module(parse_muster)

compile_muster = parse_muster.compile_muster
MusterError = parse_muster.MusterError

# Pinned locally so the suite is hermetic — it must not drift when the real
# headless/data/grok-models.json gains a model.
GROK = "grok-4.6"
GROK_EFFORTS = {
    "grok-4.6": frozenset({"low", "medium", "high", "xhigh"}),
    "grok-4.5": frozenset({"low", "medium", "high"}),
}


_CLAUDE = frozenset({"low", "medium", "high", "xhigh", "max"})
_GPT = _CLAUDE | {"ultra"}
# Pinned like GROK_EFFORTS: the real catalogs are headless/data/claude-models.json and
# `codex debug models --bundled`.
EXACT = {
    "claude-opus-5": parse_muster.ModelSpec("claude", "claude-opus-5", _CLAUDE, True),
    "claude-opus-5-5": parse_muster.ModelSpec("claude", "claude-opus-5-5", _CLAUDE, True),
    "claude-sonnet-5": parse_muster.ModelSpec("claude", "claude-sonnet-5", _CLAUDE, False),
    "claude-sonnet-5-5": parse_muster.ModelSpec("claude", "claude-sonnet-5-5", _CLAUDE, False),
    "gpt-5.6-sol": parse_muster.ModelSpec("gpt", "gpt-5.6-sol", _GPT, True),
    "gpt-6.1-sol": parse_muster.ModelSpec("gpt", "gpt-6.1-sol", _GPT, True),
}


def compile_ok(admiral: str, general: str, infantry: str, grok: str = GROK, efforts=None):
    return compile_muster(admiral, general, infantry, grok,
                          GROK_EFFORTS if efforts is None else efforts,
                          exact_catalog=EXACT)


class ExactModelIdTests(unittest.TestCase):
    def test_exact_ids_resolve_to_themselves(self) -> None:
        for model in ("claude-opus-5-5", "gpt-6.1-sol", "claude-sonnet-5-5"):
            with self.subTest(model=model):
                data = compile_ok(f"{model} high", "Opus 5 medium", "Grok 4.6 high")
                self.assertEqual(data["admirals"][0]["model"], model)
                self.assertNotIn("instructions", data["admirals"][0])

    def test_unknown_or_mismatched_id_is_rejected_not_mapped(self) -> None:
        for answer in ("claude-opus-9-9 high", "gpt-6.2-sol high", "claude-opus-5-6 high"):
            with self.subTest(answer=answer), self.assertRaises(MusterError) as ctx:
                compile_ok(answer, "Opus 5 medium", "Grok 4.6 high")
            self.assertIn("not a known model ID", str(ctx.exception))


    def test_repeating_the_same_identity_is_one_selection(self) -> None:
        data = compile_ok("claude-opus-5 Opus 5 high", "Opus 5 medium", "Grok 4.6 Grok 4.6 high")
        self.assertEqual(data["admirals"][0]["model"], "claude-opus-5")
        self.assertNotIn("instructions", data["admirals"][0])
        self.assertEqual(data["infantry"][0]["model"], GROK)

    def test_versioned_friendly_names_never_pick_an_older_model(self) -> None:
        for answer in ("Opus 5.5 high", "GPT 6.1 Sol high"):
            with self.subTest(answer=answer), self.assertRaises(MusterError) as ctx:
                compile_ok(answer, "Opus 5 medium", "Grok 4.6 high")
            self.assertIn("version", str(ctx.exception))

    def test_two_models_in_one_selection_are_rejected(self) -> None:
        for answer in ("claude-opus-5-5 gpt-6.1-sol high", "claude-opus-5-5 Opus 4.8 high",
                       "gpt-6.1-sol Grok 4.6 high", "claude-opus-5-5 Opus 5 high",
                       "Grok 4.6 Grok 4.5 high", "Opus 5 Opus 4.8 high"):
            with self.subTest(answer=answer), self.assertRaises(MusterError):
                compile_ok(answer, "Opus 5 medium", "Grok 4.6 high")


class CanonicalizationTests(unittest.TestCase):
    def test_menu_labels_resolve_to_full_ids(self) -> None:
        data = compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high")
        self.assertEqual(data["admirals"][0]["model"], "claude-opus-5")
        self.assertEqual(data["general"]["model"], "gpt-5.6-sol")
        self.assertEqual(data["infantry"][0]["model"], GROK)

    def test_prose_and_case_are_accepted(self) -> None:
        data = compile_ok("claude-opus-5 xhigh", "opus 4.8 medium", "gpt luna LOW")
        self.assertEqual(data["admirals"][0]["effort"], "xhigh")
        self.assertEqual(data["general"]["model"], "claude-opus-4-8")
        self.assertEqual(data["infantry"][0]["model"], "gpt-5.6-luna")

    def test_raw_answers_are_preserved_as_authorization_evidence(self) -> None:
        data = compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high")
        self.assertEqual(data["raw_answers"]["fleet_admiral"], "Opus 5 High")
        self.assertEqual(data["raw_answers"]["infantry"], "Grok 4.6 high")

    def test_recommended_decoration_is_stripped_defensively(self) -> None:
        # The menus must never carry it, but a stray label can never corrupt a roster.
        data = compile_ok("Opus 5 High (Recommended)", "GPT Sol High", "Grok 4.6 high")
        self.assertEqual(data["admirals"][0]["model"], "claude-opus-5")

    def test_speed_defaults_to_standard_and_honors_explicit_fast(self) -> None:
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high")["general"]["speed"], "standard")
        self.assertEqual(compile_ok("Opus 5 High fast", "GPT Sol High", "Grok 4.6 high")["admirals"][0]["speed"], "fast")
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "Luna max fast")["infantry"][0]["speed"], "fast")

    def test_fast_on_grok_is_rejected(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high fast")

    def test_role_instructions_survive_after_equals(self) -> None:
        data = compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high = focus on the CSS")
        self.assertEqual(data["role_instructions"]["infantry"], "focus on the CSS")


class AdmiralTests(unittest.TestCase):
    def test_single_admiral_sets_no_secondary(self) -> None:
        self.assertFalse(compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high")["secondary_admiral"])

    def test_two_admirals_enable_the_secondary_reviewer(self) -> None:
        data = compile_ok("Opus 5 High + GPT Sol High", "Opus 5 Medium", "Grok 4.6 high")
        self.assertTrue(data["secondary_admiral"])
        self.assertEqual(len(data["admirals"]), 2)

    def test_three_admirals_are_rejected(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High + GPT Sol High + Opus 4.8 High", "Opus 5 High", "Grok 4.6 high")

    def test_exactly_one_general(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "Opus 5 High + GPT Sol High", "Grok")


class GrokTierTests(unittest.TestCase):
    """Grok now asks model + effort like Codex, and each model accepts a different
    effort set — 4.6 adds xhigh, 4.5 does not."""

    def test_effort_is_required_and_never_defaulted(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok")

    def test_a_named_version_selects_that_model(self) -> None:
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.5 high")["infantry"][0]["model"],
                         "grok-4.5")
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high")["infantry"][0]["model"],
                         "grok-4.6")

    def test_hyphenated_ids_resolve_too(self) -> None:
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "grok-4.5 medium")["infantry"][0]["model"],
                         "grok-4.5")

    def test_bare_grok_never_uses_the_resolved_default(self) -> None:
        for selection in ("Grok medium", "Grok high", "Grok"):
            with self.subTest(selection=selection), self.assertRaisesRegex(MusterError, "explicit Grok version"):
                compile_ok("Opus 5 High", "GPT Sol High", selection, grok="grok-4.5")

    def test_xhigh_is_accepted_by_4_6(self) -> None:
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 xhigh")["infantry"][0]["effort"],
                         "xhigh")

    def test_xhigh_is_rejected_by_4_5(self) -> None:
        # The whole reason grok-models.json exists: an unsupported tier would
        # otherwise only fail at launch, after the call is billed.
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.5 xhigh")

    def test_an_uncharacterized_new_model_blocks_rather_than_guessing(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.7 high", grok="grok-4.7")

    def test_grok_never_takes_fast_mode(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high fast")

    def test_two_grok_tiers_can_coexist_with_shares(self) -> None:
        data = compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 xhigh 60, Grok 4.5 medium 40")
        self.assertEqual([(e["model"], e["effort"], e["share"]) for e in data["infantry"]],
                         [("grok-4.6", "xhigh", 60), ("grok-4.5", "medium", 40)])


class AllocationTests(unittest.TestCase):
    def test_absent_shares_mean_task_fit(self) -> None:
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high, Luna low")["allocation"]["mode"], "task_fit")

    def test_fixed_shares_totalling_100_are_accepted(self) -> None:
        data = compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high 70, Luna low 30")
        self.assertEqual(data["allocation"], {"mode": "fixed", "unit": "task_count"})
        self.assertEqual([e["share"] for e in data["infantry"]], [70, 30])

    def test_shares_not_totalling_100_are_rejected(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high 70, Luna low 20")

    def test_a_partial_share_set_is_rejected(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.6 high 70, Luna low")


class FailDoNotGuessTests(unittest.TestCase):
    def test_unknown_model_fails(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("banana supreme", "GPT Sol High", "Grok 4.6 high")

    def test_missing_effort_fails_rather_than_defaulting(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5", "GPT Sol High", "Grok 4.6 high")

    def test_two_efforts_in_one_entry_fail(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 high medium", "GPT Sol High", "Grok 4.6 high")

    def test_fast_and_standard_together_fail(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 high fast standard", "GPT Sol High", "Grok 4.6 high")

    def test_fast_on_a_non_fast_model_fails(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Sonnet 5 high fast", "GPT Sol High", "Grok 4.6 high")

    def test_ultra_is_rejected_for_luna_which_lacks_it(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Luna ultra")

    def test_xhigh_is_not_mistaken_for_high(self) -> None:
        self.assertEqual(compile_ok("Opus 5 xhigh", "GPT Sol High", "Grok 4.6 high")["admirals"][0]["effort"], "xhigh")

    def test_explicitly_named_max_is_honored(self) -> None:
        self.assertEqual(compile_ok("Opus 5 High", "GPT Sol High", "Luna max")["infantry"][0]["effort"], "max")

    def test_infantry_subagent_stances_compile(self) -> None:
        data = compile_muster("Opus 5 High", "GPT Sol High", "Grok 4.5 high", GROK,
                              GROK_EFFORTS, "Vibin")
        self.assertEqual(data["infantry_subagents"]["stance"], "vibin")
        self.assertEqual(data["raw_answers"]["infantry_subagents"], "Vibin")

    def test_missing_stance_defaults_to_vibin_and_records_source(self) -> None:
        data = compile_ok("Opus 5 High", "GPT Sol High", "Grok 4.5 high")
        self.assertEqual(data["infantry_subagents"]["stance"], "vibin")
        self.assertEqual(data["infantry_subagents"]["source"], "defaulted")
        self.assertIsNone(data["raw_answers"]["infantry_subagents"])

    def test_unknown_subagent_stance_fails(self) -> None:
        with self.assertRaises(MusterError):
            compile_muster("Opus 5 High", "GPT Sol High", "Grok 4.5 high", GROK,
                           GROK_EFFORTS, "lots")

    def test_bare_grok_without_effort_fails(self) -> None:
        with self.assertRaises(MusterError):
            compile_ok("Opus 5 High", "GPT Sol High", "Grok")


if __name__ == "__main__":
    unittest.main()
