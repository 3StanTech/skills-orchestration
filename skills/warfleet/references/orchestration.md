# WarFleet orchestration — planning constraints, manifest, and launch

Loaded twice: by the **Admiral** at Stage B, because its roster must be executable; and by the
**dispatcher** after plan approval, because it fires straight from the manifest.

The dispatcher copies the approved manifest. It does not re-plan it.

---

## Part 1 — Constraints the Admiral's roster must satisfy

### Required plan shape

- Objective and success criteria.
- **Task roster** — per task: `id`; a **self-contained instruction** executable with zero outside
  context (absolute paths, exact acceptance criteria); unit assignment; formation; dependency wave;
  subagent budget.
- Known risks and decision points that must return to the user.
- A verification step for the whole run (build, tests, manual check).

**Roster rule:** two tasks that touch the same file must never share a wave. The validator enforces
this from `edit_files`.

**Split rule:** assignments honor the muster split. A fixed split is a share of the **task count**,
not tokens or wall-clock; resolve it by largest-remainder rounding, then assign *which* tasks by fit
within each quota. End the roster with a one-line tally (`Grok 7 / GPT 3 of 10 — target 70/30`), and
flag any forced deviation with a one-line reason. A squad task counts once, toward its lead unit's
family.

### Capability, family, browser and fallback rules

Lane by capability, family by task shape, sandbox-as-guarantee, the browser rule, smoke tests,
fallbacks and cross-family review live in `~/.agents/skills/stance/references/capabilities.md`.
The roster must satisfy them. WarFleet-specific mechanics only:

- The validator rejects any task with `browser: true`; a visual task is a dispatcher capture step
  plus a unit assessment step.
- A network-risky task's pre-approved fallback carries its own auth entry at an approved tier, so a
  capability failure is a one-line reassignment inside the same wave.
- When a run is read-only, the plan names the Codex/Grok lane-A sandbox as its enforcement.

### Subagent budgets — the per-task ceiling

Apply the shared stance to optional assignments across the entire run, not only
Infantry descendants. The Admiral evaluates total completion time, dependencies,
integration, and risk. It may recommend a weaker stance once only after assessing
the whole plan; the dispatcher merely relays it and retains the original stance
unless the user accepts.

Every Infantry task carries a budget the Admiral sizes after planning, from
`muster.infantry_subagents.stance`. **Internal Infantry subagents only** — not squads, not
Admiral/General.

```json
"subagents": {"max_total": 3, "parallel": true,
              "rationale": "vibin: two independent verifiers improve coverage without extra nesting."}
```

**Efficiency binds every stance**, but the cost trade-off depends on the stance. Never spend a
subagent that does not improve the result. Do not report token counts or dollars.

| Stance | How the Admiral sets `max_total` |
|---|---|
| `supersoldiers` | **As many as needed** for progress and speed. Cost is secondary. Plan the task first, then set `max_total` to every helper that materially moves the work forward. No "stay moderate" bias. No "just in case" padding. Efficiency here means "don't spawn what does not help," not "keep the number small." The rationale must name those helpers. A simple task may still be `0`. |
| `vibin` | Fewer, broader assignments when useful concurrency outweighs startup, context, integration, and rereading |
| `chillin` | One implementation owner first; add help for required independent checks, missing capability, or clear overall efficiency |

- No hard numeric bands. Under `supersoldiers` the stance does not squeeze the number; the task
  breakdown does, and progress/speed win ties against cost. Under `vibin` / `chillin` the stance
  still squeezes.
- `max_total` is a **ceiling, not a target.** A unit may use fewer, including zero.
- The stance applies to every chosen Infantry model unless the user stated otherwise.
- It counts **every descendant across all nesting levels**.
- Every child inherits the parent task's exact model, effort, speed, lane, mission context, scope,
  and acceptance criteria.
- Parallel children must be independent and may never edit the same file. `max_total: 0` with
  `parallel: true` is rejected.
- Before launching a task with `max_total > 0`, capability-probe that surface without a paid call
  where possible. If subagents are unavailable, **block the task**.

### Squads are a different thing — do not conflate them

A **subagent budget** is task-level. A **squad** is roster-level: two or three separately rostered
units on one task. Default remains **one unit per task**.

- **Recon squad** — 2–3 parallel investigators; the General synthesizes.
- **Parallel-build squad** — independent sub-parts, worktree-isolated when they touch the same repo.
- **Adversarial pair** — builder + verifier. **Default to cross-family pairs.** Verifiers default one
  tier below their builder unless the plan justifies parity.

Never more than 3 units per task. The dispatcher may **downgrade** a planned squad to a single unit;
upgrading mid-run requires returning to the user.

### Who writes what

Stage B runs with **scratchpad-scoped write access** (Codex Admiral: lane B with the state dir as
workdir; Claude: add `--add-dir "<state>"`; Grok: `run-grok.sh --lane B`, which maps internally to
`--sandbox workspace`) and writes its own bulk
artifacts. Repo writes stay disabled until approval.

| File | Written by |
|---|---|
| `mission-context.md` | **Admiral** |
| `warfleet-plan.md` | **Admiral** |
| `warfleet-launch.json` | **Admiral** |
| `warfleet-task-<id>.md` | **Admiral** |
| `auth-<session-id>.json` | **Dispatcher**, after approval, to `~/.claude/warfleet/` |
| `warfleet-log.md` | **Dispatcher** |

The Admiral must still **emit the auth block in its reply** rather than write it. Stage B may write
**only** inside the state directory.

`warfleet-plan.md` may be a short header plus a pointer to the Admiral's full Stage B output — but
the target must be written first and its existence verified.

---

## Part 2 — The manifest

Use absolute paths everywhere. One entry per task. File name: **`warfleet-launch.json`**.

```json
{
  "id": "t1",
  "wave": 1,
  "family": "gpt",
  "model": "gpt-5.6-sol",
  "effort": "high",
  "speed": "standard",
  "executor": "native-agent",
  "lane": "A",
  "context_file": "/private/tmp/warfleet-<uuid>/mission-context.md",
  "task_file": "/private/tmp/warfleet-<uuid>/warfleet-task-t1.md",
  "output_file": "/private/tmp/warfleet-<uuid>/warfleet-out-t1.json",
  "thread_id": "<uuid>",
  "dependencies": [],
  "edit_files": [],
  "subagents": {"max_total": 2, "parallel": true, "rationale": "Independent verification."},
  "acceptance": ["Reports the requested finding"],
  "argv": "<the exact command line, tag included>"
}
```

The manifest root carries the canonical `muster` object and an absolute `mission_context`. Every task
repeats that path as `context_file`, names an explicit `executor`, includes the full subagent budget,
and carries a non-empty `argv`.

**Executors on the Codex host:**

| Family | Executor | Launch path |
|---|---|---|
| `gpt`, explicitly supported identity and controls | `native-agent` | only with current `native_agent_capabilities` evidence below |
| `gpt`, compatible approved CLI route | `codex-cli` | maintained wrapper pins model, effort, sandbox and service tier |
| `claude` | `claude-cli` | maintained Claude wrapper |
| `grok` | `grok-cli` | `../headless/scripts/run-grok.sh` |

**Executors on every other host (Claude Code, Grok, Hermes, Pi):** there is no native GPT agent
surface, so exactly three executors exist — `claude` → `claude-cli` (`run-claude.sh`), `gpt` →
`codex-cli` (`run-codex.sh`), `grok` → `grok-cli` (`run-grok.sh`). Validate with `--host claude`
on Claude Code and `--host other` elsewhere.

A native route must carry manifest-level `native_agent_capabilities`: `evidence`
(current tool/schema reference), `models` (concrete model → supported effort list),
`lanes`, and `speeds`. These are inspected capabilities, never invented parameters.
For example, a synthetic test host might record:

```json
{"native_agent_capabilities": {
  "evidence": "current host tool schema and verified inherited sandbox",
  "models": {"gpt-5.6-luna": ["high", "xhigh"]},
  "lanes": ["A"], "speeds": ["standard"]
}}
```

Do not copy this example as evidence. If the host cannot enforce the requested
lane or speed, omit it from the capability record and select `codex-cli` before
approval. This applies on Grok and Claude hosts as well as Codex. A native tool's
presence alone is insufficient. The validator cannot verify runtime truth of the
record, so retain the inspected source alongside the manifest. Approved roster
lane/executor values still cannot be silently replaced.

The General always launches with the exact family, concrete model, effort, speed, lane, and executor
selected in `muster.general`. Never route a General through an unrelated wrapper or substitute an
Infantry family because a launcher probe looks unhealthy.

If an approved GPT model is unavailable through the native agent surface, use direct `codex exec`
with the exact sandbox, model, effort, and speed. Never substitute a different model.

**`~/.claude/warfleet/auth-<session-id>.json`** — emitted by the Admiral verbatim, written by the
dispatcher after approval. Each wrapper verifies `--auth`/`--task-id` (the `# warfleet-task:<id>` tag) against this
file. Do not invent a second auth format.

```json
{"session_id": "<session-id>",
 "approved": [{"task": "t1", "model": "gpt-5.6-sol", "effort": "high", "speed": "standard"}]}
```

One entry per Codex, Grok, and Claude task, plus one per pre-approved fallback. Model strings must be
the exact ids the command line carries.

### Validate before you launch — and before the user approves

```bash
scripts/validate-manifest.py "<state>/warfleet-launch.json" --host codex \
  --grok-model "<resolved id>" \
  --auth ~/.claude/warfleet/auth-<session-id>.json
```

It rejects: unknown families, models, efforts, speeds, lanes, or executors; a model/effort/speed
identity outside the approved Infantry roster; a wrong executor for the family/model; missing mission
context, acceptance criteria, thread id, argv, or subagent budget; relative paths; a `context_file`
that does not match `mission_context`; duplicate task ids; dependencies in the same or a later wave;
same-wave edit collisions; roster drift; any task claiming a browser; and — with `--auth` — any task
whose tier does not match its auth entry **verbatim**.

Run it **twice**: once before presenting the plan (without `--auth`) and once immediately after
approval writes the auth file.

---

## Part 3 — Dispatcher sequence after approval

1. Persist the approved artifacts **with the Write tool, never Bash heredocs.** A heredoc carrying
   model names or flag-shaped text can false-positive the delegation hook.
2. Write `~/.claude/warfleet/auth-<session-id>.json` from the Admiral's emitted block, then re-run the
   validator with `--auth`.
3. Start Grok and Claude sessions first, via their wrappers and the exact approved lane. Record every
   thread/session id in `<state>/external-threads.json` before launching the rest.
4. Launch each wave's units in **one parallel block** unless the user chose sequential. Write each
   spec file first.
5. Use parallel only for independent tasks in the same wave. Never let two units edit one file in one
   wave.
6. At every status change, **update the existing row** in `warfleet-log.md`. One row per task, in
   place. Record `subagents_used/max_total` in NOTES. **Never track or report cost in any form.**
7. Store only the final structured output in `warfleet-out-<id>.json`.
8. At a wave gate, send the General only the task ids, footer blocks, changed-file list, and
   acceptance evidence.
9. Fire the next wave only after a green gate.

### Launch table

**GPT route** — use the native collaboration tool only when its current schema can
express the approved identity, effort, capabilities, and permissions. Fresh Infantry
uses `fork_turns: none`. If speed, lane, or another approved control is unavailable,
use the already-authorized same-model CLI wrapper. Never pass an argument absent from
the live native schema and never substitute a model.

**Claude unit** — `../headless/scripts/run-claude.sh` with the manifest's `--speed standard|fast`. The
wrapper applies a session-scoped `fastMode` setting. Never offer or pass fast mode for non-Opus
Claude models. Pass `--auth <auth file> --task-id <id>`. Never use `--bare` or `--safe-mode`.
Full form (all hosts):

```
../headless/scripts/run-claude.sh \
  --cwd "<workdir>" --model <model> --effort <effort> --speed <standard|fast> --lane <A|B|C> \
  --session <uuid> --prompt-file "<state>/warfleet-task-<id>.md" --output-format json \
  [--max-budget-usd <cap>] [--add-dir "<extra dir>"] [--approve-lane-c yes] \
  --auth ~/.claude/warfleet/auth-<session-id>.json --task-id <id> \
  > "<state>/warfleet-out-<id>.json" 2>&1   # warfleet-task:<id>
```

The final report is the JSON `result` field; ignore its cost fields. `--bare` forces API-key auth
and skips hooks; `--safe-mode` disables hooks — both bypass the launch guard.

**Grok unit** — `../headless/scripts/run-grok.sh`:

```
../headless/scripts/run-grok.sh \
  --cwd "<workdir>" --lane <A|B|C> --model <approved id> --effort <approved level> \
  --session <uuid> --prompt-file "<state>/warfleet-task-<id>.md" \
  [--approve-lane-c yes] --auth <auth file> --task-id <id> \
  > "<state>/warfleet-out-<id>.log" 2>&1   # warfleet-task:<id>
```

Always pass `--model` and `--effort` explicitly. The wrapper validates the effort against that
model's set, maps the public `--lane` to Grok's internal `--sandbox`, and injects `--no-memory` and
`--verbatim`. Callers must not pass `--sandbox`, `--no-memory`, or `--verbatim`; those are wrapper
owned and rejected clearly. The `grok-build-latest` alias is not launchable — resolve, never alias.

For Grok recovery, follow `../headless/references/engine-grok.md`: one wrapper attempt, original status and
stable log, no output-text-triggered replay. Independently established pre-work
initialization failure permits the standing one-time same-identity Lane C recovery;
record the evidence and preserve the task/session. Uncertain progress goes to the
General as unresolved. Fix argument rejections at the manifest/interface boundary.

**All units** carry the roster tag `# warfleet-task:<id>` at the end of the command. Wrapper launches
also pass `--auth <auth file> --task-id <id>`, which blocks off-roster ids and tier mismatches.

### Capability smoke-test — first line of any network task spec

Prepend the smoke test from `~/.agents/skills/stance/references/capabilities.md` §4 to every spec
that needs the network; a failed probe returns `capability probe failed`, which fires the fallback.

### Every unit prompt ends with

> Execute exactly this task. If you hit an error or ambiguity you cannot resolve within the task spec,
> STOP and report it. Do not redesign or expand scope. End your output with exactly this block:
> ```
> STATUS: done | blocked
> FILES: <files changed, or none>
> BLOCKERS: <verbatim error + what you tried, or none>
> NOTES: <one-line anything else the commander must know>
> ```

**Relay discipline:** forward footer blocks (plus any delta that changes a decision) up the chain —
never whole transcripts.

---

## Part 4 — Browser tasks: the dispatcher drives, a unit judges

Follow `~/.agents/skills/stance/references/capabilities.md` §3. This is the one deliberate exception
to "the dispatcher never absorbs a role": you operate the instrument, a unit interprets the
readings. Write every capture to `<state>/warfleet-capture-<id>/` and hand that folder to the
assessing unit.

---

## Part 5 — Model capability protection

Do not ask a model to imitate another model. Preserve each external model's normal prompt, skills,
plugins, tools, connectors, image generation, image editing, and structured-output features. Use
Grok `--prompt-json` for images and `--json-schema` where exact JSON is required; use Codex
`--output-schema` for the same. Do not disable external subagents by default.

**Never write a unit off as incapable without probing.** Before excluding a capability from the
roster, run the read-only probe in `~/.agents/skills/headless/references/contract.md` §0b.

- **Grok generates and edits images** (`image_gen` / `image_edit`) and it works in a sandboxed lane.
- **Codex image generation is unverified headless** — probe before assigning it, and prefer a Grok
  unit for image work.
