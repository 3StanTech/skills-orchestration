#!/usr/bin/env python3
"""Compile three free-form WarFleet muster answers into a canonical roster.

The dispatcher runs at low effort and holds zero judgment, so it must not be the
thing that decides what "Opus 5 high, Grok = focus on the CSS" means. This script
is that decision, made mechanically: it accepts friendly prose from the popup's
free-form `Other` box, canonicalizes it, and *fails* rather than guessing.

Menu policy lives in references/muster.md, not here. The compiler accepts every
supported effort recorded for each model, including `max` and `ultra` when a menu
or Other names them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASELINE_GROK_MODEL = "grok-4.5"
GROK_CATALOG = Path.home() / ".agents/skills/headless/data/grok-models.json"
CLAUDE_CATALOG = Path.home() / ".agents/skills/headless/data/claude-models.json"


class MusterError(ValueError):
    """A muster answer cannot be normalized without guessing."""


@dataclass(frozen=True)
class ModelSpec:
    family: str
    model: str
    efforts: frozenset[str]
    fast: bool


# Longest-first so `xhigh` is never mistaken for `high`. (Word boundaries already
# prevent that specific pair, but the ordering keeps the invariant obvious.)
EFFORTS = ("ultra", "xhigh", "medium", "high", "low", "max")

GPT_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})
LUNA_EFFORTS = GPT_EFFORTS - {"ultra"}
CLAUDE_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


# Grok is matched separately from the alias table because its id carries a version
# the user may name ("Grok 4.5" vs "Grok 4.6"), and each version accepts a DIFFERENT
# effort set — 4.6 adds xhigh, 4.5 does not. Getting that wrong only fails at launch,
# after the call is billed, so the compiler gates it here instead.
GROK_PATTERN = re.compile(r"\bgrok(?:[\s-]*(\d+(?:\.\d+)?))?\b", re.I)


def load_grok_efforts(catalog: Path) -> dict[str, frozenset[str]]:
    """Per-model Grok effort sets. This cannot be probed — `grok --help` declares
    --reasoning-effort as free text — so the catalog file is the only authority."""
    try:
        data = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        name: frozenset(spec.get("efforts", []))
        for name, spec in data.get("models", {}).items()
    }


# A full model ID spelled out in an answer: claude-* or gpt-* with a version digit.
FULL_ID = re.compile(r"\b(?:claude|gpt)-[a-z0-9]+(?:[.-][a-z0-9]+)*", re.I)
ID_SUFFIX = re.compile(r"-(?:" + "|".join(EFFORTS) + r"|fast|standard)$", re.I)


def load_exact_catalog(claude_catalog: Path = CLAUDE_CATALOG) -> dict[str, ModelSpec]:
    """Exact Claude and GPT IDs from the authorities headless already uses:
    headless/data/claude-models.json and `codex debug models --bundled`."""
    specs: dict[str, ModelSpec] = {}
    try:
        models = json.loads(claude_catalog.read_text(encoding="utf-8")).get("models", {})
        for name, spec in models.items():
            specs[name] = ModelSpec("claude", name, frozenset(spec.get("efforts", [])),
                                    bool(spec.get("fast")))
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    try:
        out = subprocess.run(["codex", "debug", "models", "--bundled"], capture_output=True,
                             text=True, timeout=30).stdout
        for model in json.loads(out).get("models", []):
            levels = frozenset(v.get("effort") for v in model.get("supported_reasoning_levels", []))
            specs[model["slug"]] = ModelSpec("gpt", model["slug"], levels,
                                             "fast" in model.get("additional_speed_tiers", []))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        pass
    return specs


VERSION_BEFORE = re.compile(r"\d+(?:\.\d+)*[\s-]*$")
VERSION_AFTER = re.compile(r"[.\-]\d")


def check_version_fragments(text: str, role: str, match: re.Match[str], spans=()) -> None:
    """A version the alias did not consume (`Opus 5.5`, `GPT 6.1 Sol`) names a model the
    alias table cannot map; reject it rather than pick an older model."""
    before, after = text[:match.start()], text[match.end():]
    trimmed = before.rstrip(" -")
    # A number that ends another model occurrence belongs to that model, not to this one.
    own_before = not any(hi == len(trimmed) for _, hi in spans)
    if VERSION_AFTER.match(after) or (own_before and VERSION_BEFORE.search(trimmed + " ")):
        fail(f"{role}: {match.group(0)!r} in {text!r} carries a version the alias table does not "
             f"map; use the full model ID from headless/data/claude-models.json or `codex debug models --bundled`")


def find_exact_ids(text: str, role: str, matches, exact: dict[str, ModelSpec]):
    """Every explicit full ID in the text, as (span, spec). Each resolves to itself or is
    rejected; it is never mapped to an alias of a different model."""
    found = []
    for token in FULL_ID.finditer(text):
        raw = token.group(0)
        while ID_SUFFIX.search(raw):
            raw = ID_SUFFIX.sub("", raw)
        if not any(ch.isdigit() for ch in raw):
            continue
        span = (token.start(), token.start() + len(raw))
        spec = exact.get(raw.lower())
        if spec is not None:
            found.append((span, spec))
            continue
        # Spelled like an alias over the whole token (e.g. `gpt-5-6-sol`): leave it to the alias table.
        if any(m.start() == span[0] and m.end() == span[1] for m, _ in matches):
            continue
        fail(f"{role}: {raw!r} is not a known model ID (partial or version mismatch); "
             f"name a model in headless/data/claude-models.json or `codex debug models --bundled`")
    return found


def model_aliases(grok_model: str) -> tuple[tuple[re.Pattern[str], ModelSpec], ...]:
    """Alias table for the non-Grok families."""
    return (
        (re.compile(r"\b(?:gpt[\s-]*)?6[\s-]*astra\b", re.I),
         ModelSpec("gpt", "gpt-6-astra", GPT_EFFORTS, True)),
        (re.compile(r"\b(?:claude[\s-]+)?opus[\s-]*5\b", re.I),
         ModelSpec("claude", "claude-opus-5", CLAUDE_EFFORTS, True)),
        (re.compile(r"\b(?:claude[\s-]+)?opus[\s-]*4(?:[.\s-]*8)\b", re.I),
         ModelSpec("claude", "claude-opus-4-8", CLAUDE_EFFORTS, True)),
        (re.compile(r"\b(?:claude[\s-]+)?sonnet[\s-]*5\b", re.I),
         ModelSpec("claude", "claude-sonnet-5", CLAUDE_EFFORTS, False)),
        (re.compile(r"\b(?:claude[\s-]+)?fable[\s-]*5\b", re.I),
         ModelSpec("claude", "claude-fable-5", CLAUDE_EFFORTS, False)),
        (re.compile(r"\b(?:gpt[\s-]*)?(?:5(?:[.\s-]*6)?[\s-]*)?sol\b", re.I),
         ModelSpec("gpt", "gpt-5.6-sol", GPT_EFFORTS, True)),
        (re.compile(r"\b(?:gpt[\s-]*)?(?:5(?:[.\s-]*6)?[\s-]*)?terra\b", re.I),
         ModelSpec("gpt", "gpt-5.6-terra", GPT_EFFORTS, True)),
        (re.compile(r"\b(?:gpt[\s-]*)?(?:5(?:[.\s-]*6)?[\s-]*)?luna\b", re.I),
         ModelSpec("gpt", "gpt-5.6-luna", LUNA_EFFORTS, True)),
        (re.compile(r"\bgpt[\s-]*5[.\s-]*5\b", re.I),
         ModelSpec("gpt", "gpt-5.5", GPT_EFFORTS - {"ultra", "max"}, True)),
    )


def fail(message: str) -> None:
    raise MusterError(message)


def split_answer(raw: str) -> tuple[list[str], str]:
    """`selection [= role instructions]`, selections separated by `+`, `,` or `and`."""
    selection, separator, instructions = raw.partition("=")
    parts = [p.strip() for p in re.split(r"\s*(?:\+|,|\band\b)\s*", selection, flags=re.I) if p.strip()]
    if not parts:
        fail("answer does not contain a model selection")
    return parts, instructions.strip() if separator else ""


def parse_entry(text: str, role: str, aliases, grok_model: str,
                grok_efforts: dict[str, frozenset[str]],
                exact: dict[str, ModelSpec]) -> dict[str, Any]:
    # Menus must never carry "(Recommended)" — but strip it defensively so a UI that
    # adds decoration of its own can never corrupt a roster entry.
    text = re.sub(r"\s*\(recommended\)\s*", " ", text, flags=re.I).strip()

    # Every model occurrence: exact IDs, aliases, Grok names. Overlapping readings of the
    # same words collapse to the exact ID; what remains must be one identity.
    alias_hits = [(m, spec) for pattern, spec in aliases for m in pattern.finditer(text)]
    exact_hits = find_exact_ids(text, role, alias_hits, exact)
    hits = [(span, spec, None) for span, spec in exact_hits]
    for m, spec in alias_hits:
        if not any(m.start() < hi and lo < m.end() for (lo, hi), _ in exact_hits):
            hits.append(((m.start(), m.end()), spec, m))
    for grok_match in GROK_PATTERN.finditer(text):
        version = grok_match.group(1)
        if not version:
            fail(f"{role}: explicit Grok version is required; discovery is not selection")
        model = f"grok-{version}"
        efforts = grok_efforts.get(model)
        if efforts is None:
            fail(f"{role}: {model} has no recorded effort set — add it to "
                 f"headless/data/grok-models.json, or ask the user which tier it accepts")
        hits.append((grok_match.span(), ModelSpec("grok", model, efforts, False), None))

    identities = sorted({spec.model for _, spec, _ in hits})
    if not identities:
        fail(f"{role}: expected exactly one known model in {text!r}")
    if len(identities) > 1:
        fail(f"{role}: expected exactly one model per selection, found {', '.join(identities)} in {text!r}")
    spec = hits[0][1]
    model_spans = [span for span, _, _ in hits]
    for _, _, match in hits:
        if match is not None:
            check_version_fragments(text, role, match, model_spans)

    lower = text.lower()
    effort_hits = [e for e in EFFORTS if re.search(rf"\b{re.escape(e)}\b", lower)]
    if len(effort_hits) > 1:
        fail(f"{role}: multiple efforts in {text!r}")

    if not effort_hits:
        fail(f"{role}: effort is required for {spec.model}")
    effort = effort_hits[0]
    if effort not in spec.efforts:
        fail(f"{role}: {effort} is not supported by {spec.model}; "
             f"supported: {', '.join(sorted(spec.efforts))}")

    fast = bool(re.search(r"\bfast\b", lower))
    standard = bool(re.search(r"\bstandard\b", lower))
    if fast and standard:
        fail(f"{role}: both fast and standard were supplied in {text!r}")
    if fast and not spec.fast:
        fail(f"{role}: fast mode is not supported by {spec.model}")
    speed = "fast" if fast else "standard"

    share_match = re.search(r"(?:^|\s)(100|[1-9]?\d)\s*%?\s*$", text)
    share = int(share_match.group(1)) if share_match else None

    # Blank out everything we consumed; whatever survives is a role instruction.
    consumed = list(model_spans)
    for token in effort_hits + (["fast"] if fast else []) + (["standard"] if standard else []):
        token_match = re.search(rf"\b{re.escape(token)}\b", text, re.I)
        if token_match:
            consumed.append((token_match.start(), token_match.end()))
    if share_match:
        consumed.append((share_match.start(), share_match.end()))
    chars = list(text)
    for start, end in consumed:
        chars[start:end] = " " * (end - start)
    residual = re.sub(r"\s+", " ", "".join(chars)).strip(" -:/")

    entry: dict[str, Any] = {
        "family": spec.family,
        "model": spec.model,
        "effort": effort,
        "speed": speed,
    }
    if share is not None:
        entry["share"] = share
    if residual:
        entry["instructions"] = residual
    return entry


STANCE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsuper[\s-]*soldiers?\b", re.I), "supersoldiers"),
    (re.compile(r"\bvibin\b", re.I), "vibin"),
    (re.compile(r"\bchillin\b", re.I), "chillin"),
)


def parse_infantry_subagents(raw: str) -> dict[str, Any]:
    text = re.sub(r"\s*\(recommended\)\s*", " ", raw, flags=re.I).strip()
    if not text:
        fail("infantry_subagents: stance is required")
    hits = [(match, stance) for pattern, stance in STANCE_PATTERNS if (match := pattern.search(text))]
    if len(hits) != 1:
        fail("infantry_subagents: expected exactly one of supersoldiers, vibin, chillin")
    match, stance = hits[0]
    residual = (text[:match.start()] + " " + text[match.end():]).strip(" -:/=,")
    residual = re.sub(r"\s+", " ", residual)
    entry: dict[str, Any] = {"stance": stance, "raw": raw}
    if residual:
        entry["instructions"] = residual
    return entry


def parse_role(raw: str, role: str, minimum: int, maximum: int, aliases,
               grok_model: str, grok_efforts: dict[str, frozenset[str]],
               exact: dict[str, ModelSpec]) -> tuple[list[dict[str, Any]], str]:
    parts, instructions = split_answer(raw)
    if not minimum <= len(parts) <= maximum:
        fail(f"{role}: expected {minimum} to {maximum} model selections, got {len(parts)}")
    return [parse_entry(part, role, aliases, grok_model, grok_efforts, exact) for part in parts], instructions


def compile_muster(admiral: str, general: str, infantry: str, grok_model: str,
                   grok_efforts: dict[str, frozenset[str]] | None = None,
                   infantry_subagents: str | None = None,
                   exact_catalog: dict[str, ModelSpec] | None = None) -> dict[str, Any]:
    aliases = model_aliases(grok_model)
    if grok_efforts is None:
        grok_efforts = load_grok_efforts(GROK_CATALOG)
    if exact_catalog is None:
        exact_catalog = load_exact_catalog()

    def role(raw: str, name: str, lo: int, hi: int):
        return parse_role(raw, name, lo, hi, aliases, grok_model, grok_efforts, exact_catalog)

    # One primary Admiral, plus an optional second that reviews the plan and owns
    # the final review. Exactly one General. One or more Infantry tiers.
    admirals, admiral_instructions = role(admiral, "fleet_admiral", 1, 2)
    generals, general_instructions = role(general, "general", 1, 1)
    infantry_entries, infantry_instructions = role(infantry, "infantry", 1, 20)

    shares = [entry.get("share") for entry in infantry_entries]
    if any(share is not None for share in shares):
        if any(share is None for share in shares):
            fail("infantry: every tier requires a share when fixed allocation is used")
        if sum(int(share) for share in shares) != 100:
            fail("infantry: fixed task-count shares must total 100")
        allocation: dict[str, Any] = {"mode": "fixed", "unit": "task_count"}
    else:
        allocation = {"mode": "task_fit"}

    raw_answers = {"fleet_admiral": admiral, "general": general, "infantry": infantry}
    compiled: dict[str, Any] = {
        "raw_answers": raw_answers,
        "admirals": admirals,
        "secondary_admiral": len(admirals) == 2,
        "general": generals[0],
        "infantry": infantry_entries,
        "allocation": allocation,
        "grok_model": grok_model,
        "role_instructions": {
            "fleet_admiral": admiral_instructions,
            "general": general_instructions,
            "infantry": infantry_instructions,
        },
    }
    stance_raw = infantry_subagents or "Vibin"
    stance = parse_infantry_subagents(stance_raw)
    stance["source"] = "stated" if infantry_subagents else "defaulted"
    raw_answers["infantry_subagents"] = infantry_subagents
    compiled["infantry_subagents"] = stance
    return compiled


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admiral", required=True, help="raw Fleet Admiral popup answer")
    parser.add_argument("--general", required=True, help="raw General popup answer")
    parser.add_argument("--infantry", required=True, help="raw Infantry popup answer")
    parser.add_argument("--infantry-subagents",
                        help="stated stance; omitted defaults to announced Vibin")
    parser.add_argument("--grok-model", default=BASELINE_GROK_MODEL,
                        help="discovered Grok catalog metadata; never supplies an omitted user model")
    parser.add_argument("--grok-catalog", type=Path, default=GROK_CATALOG,
                        help="per-model Grok effort table (headless/data/grok-models.json)")
    parser.add_argument("--output", help="write JSON to this path instead of stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = compile_muster(args.admiral, args.general, args.infantry, args.grok_model,
                              load_grok_efforts(args.grok_catalog),
                              args.infantry_subagents)
    except MusterError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
