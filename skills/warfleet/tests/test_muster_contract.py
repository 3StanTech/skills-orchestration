#!/usr/bin/env python3
"""Contract tests for references/muster.md itself.

The muster is prose the dispatcher follows literally, so its invariants are worth
pinning mechanically. Two of these encode rules that have already been broken in a
real run: a "(Recommended)" label reaching a live popup, and an effort tier above
xhigh appearing on a menu.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUSTER = ROOT / "references" / "muster.md"
LATE_PHASES = ROOT / "references" / "late-phases.md"
SKILL = ROOT / "SKILL.md"
GROK_CATALOG = ROOT.parent / "headless" / "data" / "grok-models.json"
GRODEX_RESOLVER = ROOT.parent / "headless" / "scripts" / "resolve-grok-model.sh"


def payloads() -> list[dict]:
    text = MUSTER.read_text(encoding="utf-8")
    return [json.loads(value) for value in re.findall(r'^\{"questions":.*\}$', text, flags=re.M)]


class MusterContractTests(unittest.TestCase):
    def test_three_role_popups(self) -> None:
        found = payloads()
        self.assertEqual(len(found), 3)
        self.assertTrue(all(len(p["questions"]) == 1 for p in found))

    def test_the_popups_are_role_scoped_in_order(self) -> None:
        self.assertEqual(
            [p["questions"][0]["question"] for p in payloads()],
            [
                "Fleet Admiral: model + effort?",
                "General: model + effort?",
                "Infantry: model + effort?",
            ],
        )

    def test_missing_stance_announces_vibin_without_popup(self) -> None:
        text = MUSTER.read_text(encoding="utf-8")
        self.assertIn("No stance was specified, so I’ll use Vibin.", text)
        self.assertIn("Do not show a", text)

    def test_no_option_is_ever_labelled_recommended(self) -> None:
        for payload in payloads():
            for option in payload["questions"][0]["options"]:
                self.assertNotIn("recommend", option["label"].lower())
                self.assertNotIn("recommend", option["description"].lower())

    def test_infantry_offers_luna_max(self) -> None:
        labels = [o["label"] for o in payloads()[2]["questions"][0]["options"]]
        self.assertIn("GPT Luna Max", labels)

    def test_every_popup_is_single_select_within_the_four_option_cap(self) -> None:
        for payload in payloads():
            question = payload["questions"][0]
            self.assertFalse(question.get("multiSelect", False))
            self.assertTrue(2 <= len(question["options"]) <= 4)

    def test_every_grok_option_names_a_version_and_an_accepted_effort(self) -> None:
        catalog = json.loads(GROK_CATALOG.read_text(encoding="utf-8"))["models"]
        found = 0
        for payload in payloads():
            for option in payload["questions"][0]["options"]:
                if not option["label"].lower().startswith("grok"):
                    continue
                match = re.match(r"^Grok (\d+\.\d+) (\w+)$", option["label"])
                self.assertIsNotNone(match, f"unparseable Grok option: {option['label']}")
                model = f"grok-{match.group(1)}"
                effort = match.group(2).lower()
                self.assertIn(model, catalog, f"{model} is not in grok-models.json")
                self.assertIn(effort, catalog[model]["efforts"],
                              f"{model} does not accept {effort}")
                found += 1
        self.assertGreaterEqual(found, 1)

    def test_supersoldiers_is_as_many_as_needed_for_progress(self) -> None:
        body = MUSTER.read_text(encoding="utf-8")
        self.assertIn("supersoldiers", body.lower())
        self.assertIn("As many as the planned work needs", body)
        self.assertIn("Progress and speed outrank cost", body)
        self.assertIn("just in case", body)

    def test_bare_grok_is_documented_as_invalid(self) -> None:
        text = MUSTER.read_text(encoding="utf-8")
        self.assertIn("resolve-grok-model.sh", text)
        self.assertIn("grok_unknown", text)
        self.assertIn("A bare", text)
        self.assertIn("INVALID", text)

    def test_words_as_ask_is_documented_and_bounded(self) -> None:
        text = MUSTER.read_text(encoding="utf-8")
        self.assertIn("Never ask a question the user has already answered", text)
        self.assertIn("extraction, not interpretation", text)

    def test_the_no_defaults_invariant_is_stated_in_the_file(self) -> None:
        text = MUSTER.read_text(encoding="utf-8").lower()
        self.assertIn("no defaults, ever", text)
        self.assertIn("never pre-select", text)

    def test_the_clarification_loop_is_documented(self) -> None:
        text = MUSTER.read_text(encoding="utf-8")
        self.assertIn("CLARIFICATIONS: none", text)

    @staticmethod
    def _flat(text: str) -> str:
        return re.sub(r"\s+", " ", text)

    def test_clarification_ceiling_is_six_per_round(self) -> None:
        muster = self._flat(MUSTER.read_text(encoding="utf-8"))
        skill = self._flat(SKILL.read_text(encoding="utf-8"))
        self.assertIn("up to six individual questions per round", muster)
        self.assertIn("six-question round ceiling", muster)
        self.assertIn("up to six questions per round", skill)
        self.assertNotIn("up to three objects per round", muster)
        self.assertNotIn("three or fewer questions", muster)

    def test_clarification_batches_at_most_three_per_call(self) -> None:
        muster = self._flat(MUSTER.read_text(encoding="utf-8"))
        skill = self._flat(SKILL.read_text(encoding="utf-8"))
        self.assertIn("at most three questions per call", muster)
        self.assertIn("one batch", muster)
        self.assertIn("exactly two batches", muster)
        self.assertIn("one-to-three", muster)
        self.assertIn("four-to-six", muster)
        self.assertIn("one clickable batch", skill)
        self.assertIn("exactly two sequential order-preserving batches", skill)

    def test_clarification_answers_return_to_same_admiral_thread(self) -> None:
        muster = self._flat(MUSTER.read_text(encoding="utf-8"))
        skill = self._flat(SKILL.read_text(encoding="utf-8"))
        self.assertIn("same Admiral thread", muster)
        self.assertIn("together", muster.lower())
        self.assertIn("same Admiral thread", skill)

    def test_clarification_rounds_repeat_until_none_with_no_cap(self) -> None:
        muster = self._flat(MUSTER.read_text(encoding="utf-8"))
        skill = self._flat(SKILL.read_text(encoding="utf-8"))
        self.assertIn("CLARIFICATIONS: none", muster)
        self.assertIn("no total-round cap", muster)
        self.assertIn("no total-round cap", skill)
        self.assertIn("CLARIFICATIONS: none", skill)

    def test_dispatcher_never_rewrites_clarification_questions(self) -> None:
        muster = self._flat(MUSTER.read_text(encoding="utf-8"))
        skill = self._flat(SKILL.read_text(encoding="utf-8"))
        self.assertIn("never rewords, merges, answers, or invents", muster)
        self.assertIn("never rewords, merges, answers, or invents questions", skill)

    def test_primary_admiral_alone_owns_clarifications(self) -> None:
        muster = self._flat(MUSTER.read_text(encoding="utf-8"))
        self.assertIn("primary Admiral alone decides", muster)
        self.assertIn("schema and the six-question round ceiling only", muster)

    def test_general_gate_verifies_clarification_contract(self) -> None:
        late = self._flat(LATE_PHASES.read_text(encoding="utf-8"))
        self.assertIn("Clarification-contract gate", late)
        self.assertIn("CLARIFICATIONS: none", late)
        self.assertIn("at most six questions per round", late)
        self.assertIn("exactly two sequential order-preserving batches", late)
        self.assertIn("same Admiral thread", late)
        self.assertIn("no total-round cap", late)
        self.assertIn("clarification-contract", late)
        self.assertIn("plan finalized only after `CLARIFICATIONS: none`", late)

    def test_the_referenced_scripts_exist(self) -> None:
        self.assertTrue((ROOT / "scripts" / "parse-muster.py").is_file())
        self.assertTrue(GRODEX_RESOLVER.is_file())

    def test_warfleet_is_an_immediate_interrupt_even_in_plan_mode(self) -> None:
        skill = self._flat(SKILL.read_text(encoding="utf-8"))
        self.assertIn("immediate routing interrupt", skill.lower())
        self.assertIn("already-active Plan Mode", skill)
        self.assertIn("Before reading repositories", skill)
        self.assertIn("dispatcher-authored plan", skill)
        self.assertIn("single required transition", skill)

    def test_standing_authorization_prevents_duplicate_prompts(self) -> None:
        skill = self._flat(SKILL.read_text(encoding="utf-8"))
        late = self._flat(LATE_PHASES.read_text(encoding="utf-8"))
        self.assertIn("must not be re-requested for each run, wave, task, private context handoff, or retry", skill)
        self.assertIn("`.agents` and `.claude`", skill)
        self.assertIn("exact same model, effort, session, prompt, task", skill)
        self.assertIn("logged once", skill)
        self.assertIn("do not append a second task row", late)
        self.assertIn("do not show another private-context or Lane C approval prompt", late)

    def test_grok_wrapper_contract_uses_lane_and_injected_flags(self) -> None:
        orchestration = self._flat((ROOT / "references" / "orchestration.md").read_text(encoding="utf-8"))
        self.assertIn("public `--lane`", orchestration)
        self.assertIn("internal `--sandbox`", orchestration)
        self.assertIn("injects `--no-memory` and `--verbatim`", orchestration)
        self.assertIn("must not pass `--sandbox`, `--no-memory`, or `--verbatim`", orchestration)

    def test_general_keeps_the_selected_family(self) -> None:
        orchestration = self._flat((ROOT / "references" / "orchestration.md").read_text(encoding="utf-8"))
        late = self._flat(LATE_PHASES.read_text(encoding="utf-8"))
        self.assertIn("exact family, concrete model, effort, speed, lane, and executor", orchestration)
        self.assertIn("never be routed through an unrelated wrapper", late)


if __name__ == "__main__":
    unittest.main()
