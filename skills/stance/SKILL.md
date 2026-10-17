---
name: stance
description: >-
  How implementation work is split, staffed and verified on any host (Claude Code, Codex, Grok,
  Hermes, Pi): the supersoldiers / vibin / chillin stances, helper counts, tier resolution from the
  approved routing table, route per host (native helper vs headless worker), context packets and
  their check, file-ownership splits, the dispatcher's acceptance re-run, the failure ladder,
  cross-family review, outcome logging, phases and completion states. Trigger: "implement using
  <model> <effort> <supersoldiers|vibin|chillin>", "use as many subagents as necessary", "as fast
  as possible without sacrificing quality", "orchestrate to …", "/stance", or any /implement,
  /create-plan or /explore request that names a tier or stance. Not for launching GPT/Grok workers
  itself (headless) or WarFleet's role hierarchy (warfleet).
---

# Stance

Decide how a piece of implementation is staffed, then keep ownership, verification and completion
honest. This governs implementation started from any host, with or without another skill.
References: `references/routing.md` (table, precedence, routes, failure ladder, outcome log) and
`references/capabilities.md` (lanes, browser, smoke tests, fallbacks, cross-family review).

## 1. Read the request

- **Stance:** supersoldiers, vibin or chillin. "As many subagents as necessary" and "as fast
  as possible without sacrificing quality" mean supersoldiers. If none is named, announce
  exactly: **"No stance was specified, so I'll use Vibin."**
- **Tier per task:** classify each delegated task (`plan`, `mechanical`, `standard`, `hard`,
  `review`, `network`; browser work is `visual` and stays with the session), then resolve it:
  `python3 ~/.agents/skills/stance/scripts/route.py resolve --task-type <t> --host <host> [--project <dir>] [--named M:E] [--roster M:E]`.
  A tier named in the request wins, then the plan roster, then the project override, then the
  global row; an approved row is the owner's explicit choice (the table itself is optional, only a
  fallback: `references/routing.md`). Auditors are the exception: always named or confirmed by the owner. Exit 3 → ask the owner for that
  row only (words-as-ask, extraction not inference). Exit 2 → a blocker, never a substitution.
- **Planning vs implementing:** in `/explore`, `/create-plan` or plan mode, the stance and tiers
  fill the plan's Orchestration section and launch nothing. In `/implement` or an explicit
  "implement", they set the run.
- A stance never starts WarFleet; open WarFleet only when the user says WarFleet or Fleet Admiral.

## 2. Stance defaults

The session (or planner) always coordinates, integrates, and keeps tasks too small to hand off.

| Stance | Helpers | Ceiling | Reviewer |
|---|---|---|---|
| **Chillin** | 0 — the session implements | 1, only for an independent review or a missing capability | the final work-audit auditor (implement runs it) |
| **Vibin** | 1 per independent task of real size | 3 at once | the final work-audit auditor (implement runs it) |
| **Supersoldiers** | 1 per independent, file-disjoint task | none (physical limits only: rate limits, machine load) | the final work-audit auditor (implement runs it) |

- Going below a default needs a one-line reason in the plan or run log.
- Correctness and acceptance never change with the stance.
- The same defaults apply to every route and every host, including mixed rosters.

## 3. Route per helper

`resolve` returns the route; `references/routing.md` §3 has the full host table.

| Route | Means |
|---|---|
| `subagent` | Claude Code subagent launched with `model=<subagent_alias>` and `effort=<level>` |
| `native:codex` / `native:grok` | the host's own agents (Codex native agents, Grok subagents) for same-family rows |
| `headless:<engine>` | a `headless` wrapper (`~/.agents/skills/headless/SKILL.md`); the only route on Hermes, Pi and other hosts, and for exact-ID cases |
| `dispatcher` | the session does it (browser work) |

Subagents can nest (Claude Code: three levels, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`). Nest only
when a helper's task splits into file-disjoint parts; each level re-reads context and adds an
integration step.

## 4. Split by files, brief once, check the brief

- Each helper **owns its files**. Tasks in one wave never share files; shared-file work is
  serialized or kept with the session. Worktrees (a merge step) are a last resort.
- Give every helper a **context packet** (`templates/context-packet.md`); re-exploration is the
  largest repeated cost. **WIP trail:** packets for tasks likely to exceed one sitting carry the
  template's WIP-note line; repairs likely to outlive the session prefer the headless route,
  which can be resumed.
- **Check every packet before launch:** `python3 ~/.agents/skills/stance/scripts/packet-check.py <packet>`.
  A failing packet is fixed, never launched.
- Browser work and `git push` stay with the session.

## 5. Per-call tiers

- **Claude Code subagents:** pass the resolved `subagent_alias` as the model and the resolved
  effort on each launch. The approved table row, roster or named tier is the owner's explicit
  effort instruction. `headless/data/claude-models.json` records which concrete ID each alias
  means; verify after the run with `route.py check-model` (§7).
- **Exact-ID cases route `headless:claude`** (`run-claude.sh` pins the concrete ID): an older
  model (Opus 4.8, Sonnet 5, Fable 5), a just-released model being held back, fast mode
  (subagents inherit the session's speed), reproducing or comparing a past run, WarFleet units.
- **Headless helpers:** launch in the background with stdin closed (`< /dev/null`). Pass the plan's
  allowed checks as `--allow-tools "<rule>,<rule>"` (e.g. `Bash(npx vitest run:*)`); lane B runs
  those plus what the project's `.claude/settings.local.json` allows, else the dispatcher runs
  every check. A Claude helper
  with no session transcript in `~/.claude/projects/<project>/` two minutes after launch has
  stalled: kill and relaunch it.

## 6. Verify, review, escalate

1. **Smoke test first.** Network or other ⚠️-capability tasks open with the packet's smoke test; a
   `capability probe failed` block launches the row's fallback at once (`capabilities.md` §4).
2. **The dispatcher re-runs acceptance.** On `STATUS: done`, the session runs the packet's
   acceptance commands itself (non-mutating). Only a pass marks the task done.
3. **Failure ladder** (`routing.md` §4): first acceptance failure → the same owner repairs with the
   failing command and output; second → the row's `escalation` tier, any family, fresh, with the
   packet and both failures; a failed escalation → `blocked`. Launch, auth or tier errors never
   switch family; report them verbatim.
4. **Refusals stop the helper.** A refusal of an intended action stops it; a lane's sandbox limit
   does not (`headless/references/contract.md` §5b). The dispatcher asks the owner.
   Destructive steps approved in planning (deleting files, dropping data) are dispatcher-owned.
5. **Repair ownership.** Before routing a review finding, confirm its mechanism in the code. If
   the root-cause fix needs files outside the original task's, the repair packet lists them as
   owned, checked for overlap with any running task.
6. **Review.** The final review is a work-audit (`~/.agents/skills/work-audit/SKILL.md`). Its
   auditor is the plan's Reviewer, or one the owner names or confirms when asked (the `review` row
   is only the suggested default), and may be any family; a GPT auditor runs lane A
   (`capabilities.md` §5). Findings return to the named implementer as repairs.
   Without the Workcycle bundle (no `~/.agents/skills/work-audit`), the final review is a read-only
   review of the run's diff by the reviewer tier, using the lenses Correctness, Ripple and Cleanup;
   findings return to the named implementer as repairs.

## 7. Phases and ownership

| Phase | Write owner | Coordinator |
|---|---|---|
| Understand and plan | none | inspect, clarify, define acceptance; resolve tiers; plans stop here |
| Launch pending | none | validate route, tier, packet and identity; record real session IDs |
| Implement | named implementer and its helpers | coordinate, inspect, run non-mutating checks, capture browser evidence |
| Verify and repair | same implementer, then the escalation tier per §6 | re-run acceptance; return failures with evidence; reviewers stay read-only |
| Final review | WarFleet: reviewing Admiral; otherwise the named implementer, for audit findings | run work-audit (read-only auditor); in-scope fixes only |
| Revalidate and close | whoever made the final-review edits | rerun affected checks; log outcomes; report limits |

- Resolve a named implementer before any source change. A planned launch is not launch evidence.
- Repairs resume the same owner; only the §6 ladder moves a task to another tier.
- A launch failure never authorizes local takeover, family substitution, a guard bypass, a
  credential change or a paid-tier change.
- Formatters, snapshot updaters and fixture generators that change source count as writes.
- Keep a compact task record outside repositories (scope, identities, stance, phase,
  dependencies, session IDs, ownership, acceptance). WarFleet uses its manifest and log. After
  compaction, recover the record before writing.
- **Close:** for every delegated task run `route.py log …` (fields in `routing.md` §5). For a
  Claude subagent, first run `route.py check-model --transcript <its jsonl> --expect <model id>`
  and pass the result as `--model-check`. Then run `route.py nudge --task-type <t> --model <m>
  --effort <e>` and print its line if it exits 1.

## 8. Acceptance states

`planned` → `executing` → `verifying` → `repairing` → `final review` → `complete` | `partial` |
`blocked`. Mark `complete` only when the deliverables, verification, final review and
revalidation all pass. Failed or unavailable checks stay failed or unverified. Optional
suggestions never create an endless repair loop.

## 9. Plan Orchestration section

When a roster is named or the table is used, the plan carries one row per task: wave, step,
**task type**, model ID, effort, speed, **route** (`subagent` / `native:<host>` /
`headless:<engine>`), **source** (named / roster / project / global), lane, owned files,
dependencies, **allowed checks** (headless lane B: the permission rules passed as
`--allow-tools`), **smoke test**, **fallback**, **escalation**, helper budget and reviewer. It also
has a **Readiness** list (`route.py validate` exits 0, each wave's packet passes `packet-check.py`,
wrappers present, `claude --version` recorded) and one context packet per wave. `/implement` runs
this roster exactly; an invalid entry is a blocker to ask about, never a substitution.

## Guardrails

- Never exceed a stance ceiling; never pad helpers "just in case".
- Never let two helpers write the same file in one wave.
- Never launch a packet that fails `packet-check.py`.
- Never mark a task done without the dispatcher's acceptance re-run.
- Never launch during planning; never start WarFleet from stance words.
- Never show a token meter or cost tally in runs.
