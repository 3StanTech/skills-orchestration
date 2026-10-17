---
name: warfleet
description: Hierarchical multi-model execution workflow (formerly warroom) for any host (Claude Code, Codex, Grok, others). A clickable muster names the Fleet Admiral, General and Infantry tiers plus the Infantry-subagent stance; the Admiral plans and writes the launch manifest; the user approves; the dispatcher fires it wave by wave; the General gates waves; an Admiral returns for final review. Use when the user types /warfleet or $warfleet, mentions WarFleet or the Fleet Admiral, or asks to run the fleet workflow on a problem.
argument-hint: <problem or goal to solve>
---

# WarFleet

Shared stance, ownership, repair, recovery, and completion rules live in
`~/.agents/skills/stance/SKILL.md`. WarFleet retains its
role structure and host-specific launch mechanics. Its designated reviewing Admiral
owns in-scope final-review edits after implementation and ordinary repair complete.

Run a strict Fleet Admiral → General → Infantry chain. The current session, on whichever host, is a mechanical
dispatcher (host specifics: **Host notes** at the end). It relays literal artifacts and operates tools, but never plans, clarifies the goal,
routes tasks, adjudicates results, or implements work. **An explicit request to run WarFleet is an immediate routing interrupt for generic planning,
including an already-active Plan Mode, while respecting platform write boundaries.**
Incidental mentions, audits, explanations, or requests to edit this skill do not start a fleet.
A request for direct implementation stays direct; scoped work does not require WarFleet.

## Immediate trigger contract

The moment a triggering message is received, stop generic planning and route it to WarFleet. Before
reading repositories, handoff notes, images, or project context, preserve the complete message
verbatim as `raw_goal`, read `references/muster.md`, and start the muster. The dispatcher must not
write its own plan, explain what it intends to do, or ask the user to repeat the request with a
WarFleet command. Plan Mode does not change this ordering: the Admiral supplies the plan while the
dispatcher remains in Plan Mode, and the user's approval is followed by exactly one mode transition
before any approved mutation. The platform's Plan Mode write boundary remains intact.

1. Trigger when the user requests running, mustering, or continuing WarFleet or the fleet workflow. Do not require `$warfleet`, `/warfleet`,
   flags, or a follow-up explanation of what WarFleet means.
2. Preserve the complete triggering user message verbatim as `raw_goal`. Do not analyse, summarize,
   or act on it. Any pre-analysis is a violation — the Admiral does the thinking, at the Admiral's
   tier, and must not be primed by yours. The only allowed read of that text is **words-as-ask**:
   extract explicit tier tokens (a model name, an effort word, a percentage) and explicit
   Infantry-subagent stance words (`Supersoldiers`, `Vibin`, `Chillin`) so those popups can be
   skipped. Extraction, not inference. An implied tier ("keep it cheap") is not an answer.
3. Immediately read `references/muster.md` and start its clickable muster. Always show the remaining
   popups. If Plan Mode is already active, stay in it while the Admiral plans; do not create a
   dispatcher-authored plan or require a second planning detour. Plan approval is never skipped,
   even when every popup was answered in the request.
4. Use the host-native question mechanism described in `references/muster.md`. Prefer available
   clickable controls, including async questions outside Plan Mode. If none are available, ask
   the same question concisely in chat. Preserve choices and wait for required answers; tool
   availability does not require a mode change or authorize guessing.
5. After the answers return, run `scripts/parse-muster.py`. Preserve its canonical roster and raw
   answers; do not reinterpret or silently repair them. On `INVALID:`, show the line and re-ask that
   one popup.

## Role boundaries

- **Fleet Admiral:** The primary Admiral analyzes `raw_goal`, asks goal-level clarifying questions,
  creates the mission context, plan, task roster, acceptance criteria, executable launch file, and
  each task's subagent budget. An optional secondary Admiral reviews the plan and performs the final
  outcome review.
- **General:** Lazily commissioned read-only adjudicator. Verify blockers and wave gates; never code
  or re-plan.
- **Infantry:** Execute self-contained approved tasks and use as many subagents as useful within the
  Admiral-approved total budget. Stop on unhandled ambiguity and report the exact footer.
- **Dispatcher:** Run the UI, preflight, state files, manifest validator, launches, browser capture,
  and literal relays. Never absorb another role's judgment. **One narrow exception: browser work is
  yours** — you drive the pane and capture artifacts; a unit assesses them.

## Persistent commander directives

Unless the commander explicitly revokes or narrows them, these directives persist across future
WarFleet runs and sessions:

- Do not re-request authorization for in-scope work handed to non-GPT models. The commander grants
  standing authorization for those handoffs and the sharing of in-scope task material with them.
- Do not ask the commander to choose or approve a visual artifact from filenames or descriptions.
  Display every image intended for visual inspection or selection directly in chat using an absolute
  local-path preview first.
- The Admiral must ask goal-level clarifying questions until satisfied, with no more than six
  questions per round, and must finalize the plan only after `CLARIFICATIONS: none`. The dispatcher
  relays those questions and answers mechanically on the same Admiral thread.

**Visual-review directive:** Whenever an artifact is intended for the user's visual inspection or
selection (including mocks, design variants, browser captures, and final artwork), the dispatcher
must display every such image directly in the chat using absolute local-path previews before asking
the user to choose or approve. Never ask for a visual decision from filenames or descriptions alone.

## Dispatcher contract

You hold **zero judgment**. Every decision is pre-computed by the Admiral at plan time or the General
at run time.

1. Never compose a command. Run `argv` exactly as written in `warfleet-launch.json`.
2. Never interpret a footer block. Forward it verbatim to the General.
3. Routing is a table, not a decision:

   | Observation | Action |
   |---|---|
   | `STATUS: done` | Log it. If the wave is complete, send footers to the General for the gate. |
   | `STATUS: blocked` with `capability probe failed` | Launch the pre-approved fallback from the manifest. No General. |
   | `STATUS: blocked` (any other reason) | Send footer + task id to the General. Commission it now if it isn't running. |
   | General `ESCALATE: yes` | Stop that line, report verbatim. |
   | General `RESUME: yes\|no` + order | Relaunch per the manifest, resuming or fresh as stated. |
   | Wave gate green | Fire the next wave from the manifest. |

4. Never drop or substitute a model family. Not on a failed health check, not on a CLI that looks
   unauthenticated. Show the full menu, report what you saw in one line, let the user decide.
5. Never block on a background job you were told to leave running. Stage A recon overlaps popups 2
   and 3. Do not poll it, do not read it, do not wait for it before popup 2.
6. After compaction, re-read `warfleet-plan.md`, `warfleet-log.md`, and `warfleet-launch.json` before
   doing anything else.

## State and authorization

Create one `/private/tmp/warfleet-<uuid>/` state directory. Keep repository writes disabled until the
user approves the Admiral's plan. Store `warfleet-muster.json`, `mission-context.md`,
`warfleet-plan.md`, `warfleet-launch.json`, `warfleet-log.md`, `external-threads.json`,
`warfleet-task-<id>.md`, and `warfleet-out-<id>.json` there.

The clicked muster plus explicit plan approval authorizes only the approved roster — encoded in
`~/.claude/warfleet/auth-<session-id>.json` and verified by the `headless` wrapper (`--auth`/`--task-id`) on every tagged
launch. Preserve exact family, model, effort, speed, lane, and session identity. Never default,
inherit, downgrade, substitute, or silently remove a selected capability.

The commander's standing non-GPT authorization covers subsequent in-scope
handoffs, including `.agents` and `.claude` edits. It does not authorize new
model/effort choices or waive publication, credentials, production, destructive
actions, or paid-tier gates. Follow `../headless/references/engine-grok.md` for recovery: the wrapper never
replays based on output text. One same-identity Lane C recovery remains authorized
only with independent evidence of a pre-work initialization failure. Record the
evidence; uncertain progress is a reported failure, not a replay trigger.
Standing authorization must not be re-requested for each run, wave, task, private
context handoff, or retry. An evidence-backed recovery uses the exact same model,
effort, session, prompt, task and is logged once.
A wrapper-argument rejection is a launcher contract failure: repair the interface
without substituting a family or altering the approved identity.

## Fleet sequence

1. Start non-billing `scripts/preflight.sh` and show the three muster popups sequentially without
   analysing `raw_goal`, except to extract any tier the user already named. This is the first action
   after the immediate trigger; do not create a dispatcher plan or inspect the repository first.
2. The instant popup 1 returns: launch the Admiral's Stage A recon in the background and go straight
   to popup 2. Do not wait for it. If the session is already in Plan Mode, stay there and relay the
   Admiral's plan through the existing approval surface; do not require a dispatcher-authored plan
   or an extra mode flip. After explicit approval, make the single required transition before
   mutations.
3. If the request names `Supersoldiers`, `Vibin`, or `Chillin`, record it. Otherwise
   announce “No stance was specified, so I’ll use Vibin.” Do not show a stance popup.
4. Compile the answers mechanically, including `--infantry-subagents`. Preserve the canonical roster
   and the raw answers. A bare `Grok` with no version or effort is `INVALID` — show the line and
   re-ask that role.
5. Relay any Admiral clarification objects unchanged (up to six questions per round; one-to-three in
   one clickable batch, four-to-six in exactly two sequential order-preserving batches). Return the
   round's answers together to the same Admiral thread; repeat until `CLARIFICATIONS: none` with no
   total-round cap. The dispatcher validates schema and the six-question ceiling only — never rewords,
   merges, answers, or invents questions.
6. Read `references/orchestration.md` and give the Admiral its Stage B brief. It writes
   `mission-context.md`, the plan, the task specs, and `warfleet-launch.json` itself — you transcribe
   nothing.
7. If a secondary Admiral was selected, give it the same mission context and draft plan. Run no more
   than two reciprocal review cycles; stop early on explicit agreement. If disagreement remains, stop
   before approval and ask the user to arbitrate.
8. Validate with `scripts/validate-manifest.py` and present the agreed plan for explicit approval. Do
   not launch execution before approval. If rejected or edited, revise *through the Admiral*.
9. After approval: write artifacts with the **Write tool, never Bash heredocs**, write the auth file
   from the Admiral's emitted block, re-run the validator with `--auth`, then launch each wave exactly
   as approved. Update **one existing log row per task**, in place.
10. Read `references/late-phases.md` only at the first blocker, wave gate, remediation, or final
    review. A clean single-wave run never loads it.

## Efficiency without quality loss

- Use `fork_turns: none` and self-contained task specs for fresh native Infantry; resume the same
  unit for related remediation.
- Let the Admiral write bulk artifacts; relay paths, compact deltas, footer blocks, changed files,
  and acceptance evidence instead of transcripts.
- Commission the General only when the first blocker or wave gate requires it.
- For every Infantry task, the Admiral sets `subagents.max_total` after breaking that task down.
  `supersoldiers` is as many as needed for progress and speed (cost secondary; no wasted helpers).
  `vibin` / `chillin` squeeze. There is no WarFleet-wide numeric ceiling and no hard band per stance.
- Infantry may use fewer than the approved maximum, including zero. The budget counts every
  descendant subagent across all nesting levels.
- Every subagent inherits the parent task's mission context, scope, acceptance criteria, lane, and
  exact model/effort/speed identity.
- Parallelize independent tasks, external-session startup, preflight, and Admiral recon. Serialize
  browser driving and same-file edits.
- Use the cheapest selected unit that satisfies each task's risk and capability needs; reserve
  stronger selected units for architecture, ambiguity, adjudication, and final synthesis.
- Fail capability probes early and use only a fallback already present in the approved roster.
- Final review may be lightweight only when task complexity, behavioral risk, and
  required acceptance make an independent pass unnecessary. File count alone never
  decides this. Record the rationale. Use the secondary Admiral when selected;
  otherwise the primary.

Every unit prompt must end with the exact four-line footer defined in `references/muster.md`.

## Standing rules

- Plan approval and scope changes belong to the user alone — including every squad formation and every
  tier in the roster.
- `warfleet-plan.md` is the authoritative plan, `warfleet-launch.json` the authoritative commands, and
  `warfleet-log.md` the authoritative run state. After any compaction, re-read all three first.
- **Never track or report cost in any form** — no dollar totals, no per-family tallies, no token
  counts.
- Grok's model and effort must be named on the role popup or in `Other`. There is no deferred Grok
  popup. `grok-4.6` has `xhigh`; `grok-4.5` does not. See `references/muster.md` and
  `../headless/references/engine-grok.md`.
- There is no stance popup. The Infantry-subagent stance (`supersoldiers` / `vibin` / `chillin`) is the
  one the request names, else the announced Vibin default. The Admiral writes each Infantry
  `max_total` **after** breaking down that task. `supersoldiers` is **as many as needed** for
  progress and speed (cost is secondary); efficiency still forbids wasted helpers, not a small
  number. `vibin` / `chillin` still squeeze. Internal Infantry subagents only; squads are separate.
- **Never ask a question the user already answered.** A tier named in the request is that
  question's answer; extraction, not inference. See `references/muster.md`.
- **The release is a dispatcher duty, never a unit's task.** A unit of any family may `git add` and
  `git commit`; `git push`, `gh pr create`, and `gh release` stay with the dispatcher. Sandboxed
  units cannot reach the macOS keychain, so an HTTPS push fails with `failed to get: -50` and
  `could not read Username for 'https://github.com'` — which looks like a dead token and is not.
  **This is a sandbox property, not a model property**, so it binds Codex, Grok, headless Claude, and
  any engine added to the fleet later; do not exempt a new family because nobody has seen it fail
  yet. Never escalate a lane to borrow credentials and never act on a unit's "re-authenticate"
  advice. Full rule: `~/.agents/skills/headless/references/contract.md` §2b.
- The Admiral's final-review edit rights are the **only** exception to "the Fleet Admiral never
  executes." Everything mid-run goes through Infantry.
- `claude ultrareview` is user-triggered and separately billed — WarFleet never invokes it.

## Editing this skill

**Do not read this section at runtime.**

WarFleet (one copy, shared by every host), `headless` and `stance` describe one system. **An enhancement to non-Claude
model integration is not finished until every one of them carries it**, and any future skill routing
work to an external model CLI joins that set. The shared contract
lives in `~/.agents/skills/headless/references/contract.md` §0 — read it before editing, run the drift check, and grep the sibling
files for the superseded claim before calling an edit done.

Facts belong in exactly one home: capability routing in `stance/references/capabilities.md`, shared contract in `headless/references/contract.md`, engine quirks in
`headless/references/engine-*.md`, stance semantics in `stance/SKILL.md`, muster contract in `references/muster.md`, planning constraints and launch
mechanics in `references/orchestration.md`, post-wave phases in `references/late-phases.md`.

`tests/` pins the invariants that have been broken before — run
`python3 -m unittest discover -s tests` from this directory after any change to `scripts/` or
`references/muster.md`.


## Progress and completion evidence

Use task boundaries and changed output as checkpoints. A running status alone is not
proof of progress; a quiet interval alone is not failure. Inspect the latest output,
active command, and reported artifacts before reporting a stall. Request a checkpoint
from the same worker: completed criteria, current operation, and concrete blocker.
Relay unresolved stalls to the General with that evidence. Preserve model and session
identity; do not replace the worker, repeat a mutation, or silently lower acceptance.

Completion requires the planned deliverables, relevant verification, and the required
review gates. Report unresolved defects and unverified criteria explicitly. Remediation
returns to the same implementation owner; an independent reviewer does not edit that
owner's files. Under Vibin, size implementation and review from task risk and useful
concurrency; do not manufacture an owner-plus-one-reviewer quota or fill spare slots.

## Host notes

One copy serves every host (`~/.claude/skills/warfleet` is a symlink to this folder). Only the
mechanics below differ; every rule above applies everywhere.

| Concern | Claude Code | Codex | Grok, Hermes, Pi, other |
|---|---|---|---|
| Question popups | `AskUserQuestion` (at most three per call, so 4–6 Admiral questions go as two batches); clickable muster required, never a plain-text questionnaire | `request_user_input` in Plan Mode, `request_user_input_async` outside it; chat only if neither exists | the host's question mechanism; chat if none |
| Plan Mode | load `EnterPlanMode`/`ExitPlanMode` with one ToolSearch (`select:EnterPlanMode,ExitPlanMode`) if deferred; present the Admiral's plan via `ExitPlanMode` | native Plan Mode approval surface | present the plan in chat and wait for explicit approval |
| Unit executors | all three families headless through the `headless` wrappers (no native GPT surface) | GPT may use `native-agent` only with recorded `native_agent_capabilities`, fresh Infantry `fork_turns: none`; Claude and Grok through wrappers | all families through the wrappers |
| Manifest validator | `scripts/validate-manifest.py … --host claude` | `--host codex` | `--host other` (wrapper-only executor rules) |
| Artifacts | write with the Write tool, never Bash heredocs | the host's file-write tool | the host's file-write tool |
| Browser capture | the browser pane (`mcp__Claude_Browser__*`; Claude in Chrome only if the pane is unavailable, said out loud) | the host's browser tool, else the user | the host's browser tool, else the user |
| Background launches | `run_in_background` Bash calls, one parallel block per wave | background exec / async calls | the host's background execution |

