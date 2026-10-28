---
name: stance
description: >-
  How implementation work is split, staffed and verified on any host (Claude Code, Codex, Grok,
  Hermes, Pi): the supersoldiers / vibin / chillin stances, helper counts, tier resolution (named
  tier or approved roster, else ask the owner), route per host (native helper vs headless worker), context packets and
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
References: `references/routes.md` (tier source, availability, menus, routes, failure ladder,
outcome log) and `references/capabilities.md` (lanes, browser, smoke tests, fallbacks,
cross-family review).

## 1. Read the request

- **Stance:** supersoldiers, vibin or chillin. "As many subagents as necessary" and "as fast
  as possible without sacrificing quality" mean supersoldiers. If none is named, announce
  exactly: **"No stance was specified, so I'll use Vibin."**
- **Tier per task:** every launch asks the owner for model + effort, unless the owner named a
  tier in the request or approved a plan roster that names one. Classify each delegated task
  (`plan`, `mechanical`, `standard`, `hard`, `review`, `network`; browser work is `visual` and
  stays with the session), then resolve it:
  `python3 ~/.agents/skills/stance/scripts/route.py resolve --task-type <t> --host <host> [--named M:E[:S]] [--roster M:E[:S]]`.
  A tier named in the request wins, then the approved roster. Exit 3 → ask the owner (no tier
  named, or a roster tier on a family marked inactive in `headless/data/families.json`): one
  question round built from `route.py menu`, nothing preselected; words-as-ask, extraction not
  inference. Exit 2 → a blocker, never a substitution. The auditor is always asked (or
  confirmed) by the owner.
- **Planning vs implementing:** in `/explore`, `/create-plan` or plan mode, the stance and tiers
  fill the plan's Orchestration section and launch nothing. In `/implement` or an explicit
  "implement", they set the run.
- A stance never starts WarFleet; open WarFleet only when the user says WarFleet or Fleet Admiral.

### Claude Code specifics

- Ask for model + effort together in one `AskUserQuestion` (two questions), never marking a tier
  "(Recommended)". **Words-as-ask:** a tier the owner already stated ("terra medium") is the
  answer; ask only for a missing half. Extraction, not inference: "keep it cheap" is not a tier.
  An approved plan roster answers both halves unless the owner names a tier; never for the auditor.
- "Use as many [family] subagents as necessary", "as fast as possible without sacrificing
  quality", or `implement using <model> <effort> supersoldiers` set the Supersoldiers stance at
  that exact tier (vibin and chillin likewise). In a planning request this only fills the plan's
  Orchestration section and launches nothing. It never starts WarFleet; open WarFleet only when
  the owner says WarFleet or Fleet Admiral.
- Claude helpers default to in-session subagents with the tier's alias + effort on each call;
  exact-ID needs use headless Claude (§5).

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

`resolve` returns the route; `references/routes.md` §3 has the full host table.

| Route | Means |
|---|---|
| `subagent` | Claude Code subagent launched with `model=<subagent_alias>` and `effort=<level>` |
| `native:codex` / `native:grok` | the host's own agents (Codex native agents, Grok subagents) for same-family tiers |
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
  effort on each launch. The named tier or approved roster is the owner's explicit effort
  instruction; without one, ask. `headless/data/claude-models.json` records which concrete ID each alias
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
   `capability probe failed` block launches the packet's named fallback at once, or asks the owner
   when none is named (`capabilities.md` §4).
2. **The dispatcher re-runs acceptance.** On `STATUS: done`, the session runs the packet's
   acceptance commands itself (non-mutating). Only a pass marks the task done.
3. **Failure ladder** (`routes.md` §4): first acceptance failure → the same owner repairs with the
   failing command and output; second → ask the owner for the escalation tier (any family, menu
   from `route.py menu`), then launch it fresh with the packet and both failures; a failed
   escalation → `blocked`. Launch, auth or tier errors never
   switch family; report them verbatim.
4. **Refusals stop the helper.** A refusal of an intended action stops it; a lane's sandbox limit
   does not (`headless/references/contract.md` §5b). The dispatcher asks the owner.
   Destructive steps approved in planning (deleting files, dropping data) are dispatcher-owned.
5. **Repair ownership.** Before routing a review finding, confirm its mechanism in the code. If
   the root-cause fix needs files outside the original task's, the repair packet lists them as
   owned, checked for overlap with any running task.
6. **Review.** The final review is a work-audit (`~/.agents/skills/work-audit/SKILL.md`). Its
   auditor is the plan's Reviewer, or one the owner names when asked (always asked when neither
   the request nor the plan names one), and may be any family; a GPT auditor runs lane A
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
| Verify and repair | same implementer, then the owner-named escalation tier per §6 | re-run acceptance; return failures with evidence; reviewers stay read-only |
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
- **Close:** for every delegated task run `route.py log …` (fields in `routes.md` §5). For a
  Claude subagent, first run `route.py check-model --transcript <its jsonl> --expect <model id>`
  and pass the result as `--model-check`.

## 8. Acceptance states

`planned` → `executing` → `verifying` → `repairing` → `final review` → `complete` | `partial` |
`blocked`. Mark `complete` only when the deliverables, verification, final review and
revalidation all pass. Failed or unavailable checks stay failed or unverified. Optional
suggestions never create an endless repair loop.

## 9. Plan Orchestration section

When the owner names tiers for the plan (in the request or in the planning question round), the
plan carries one row per task: wave, step, **task type**, model ID, effort, speed, **route**
(`subagent` / `native:<host>` / `headless:<engine>`), **source** (named / roster), lane, owned
files, dependencies, **allowed checks** (headless lane B: the permission rules passed as
`--allow-tools`), **smoke test**, **fallback** (named or "ask"), helper budget and reviewer. There
is no pre-set escalation column: a second acceptance failure asks the owner. It also has a
**Readiness** list (`route.py validate` exits 0 — catalogs and `families.json`, each wave's packet passes `packet-check.py`,
wrappers present, `claude --version` recorded) and one context packet per wave. `/implement` runs
this roster exactly; an invalid entry is a blocker to ask about, never a substitution.

## Guardrails

- Never exceed a stance ceiling; never pad helpers "just in case".
- Never let two helpers write the same file in one wave.
- Never launch a packet that fails `packet-check.py`.
- Never launch a tier the owner did not name, approve in a roster, or answer when asked.
- Never mark a task done without the dispatcher's acceptance re-run.
- Never launch during planning; never start WarFleet from stance words.
- Never show a token meter or cost tally in runs.
