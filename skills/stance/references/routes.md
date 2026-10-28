# Routes — how a task gets its tier and its launch route

**Every launch asks the owner for model + effort**, unless the owner names a tier in the request
or approves a plan roster that names one. Nothing pre-sets a tier: there is no table, no project
override and no pre-set escalation tier. Stance is separate: session-only implementation or
no helpers/subagents means Chillin; Vibin applies only without a stance or delegation constraint. The final
auditor is always asked (or confirmed) by the owner.

The tool is `python3 ~/.agents/skills/stance/scripts/route.py` (stdlib only, works from any host).
Capability rules (lanes, browser, smoke tests, fallbacks, cross-family review) live in
`capabilities.md`.

## 1. Task types

`plan`, `mechanical`, `standard`, `hard`, `review`, `network`, and `visual` (dispatcher only,
never delegated). Classify each task by the hardest thing it must do. The type labels the packet
and the outcome log; it never picks a tier.

## 2. Tier source

1. A tier **named in the current request** — always wins, even for an inactive family (the
   owner's availability call). Words-as-ask: a named tier is the answer; ask only for a missing
   half.
2. The **approved plan roster** (Orchestration row).
3. Otherwise **ask the owner** for model + effort (and speed for Claude).

```sh
route.py resolve --task-type <t> --host <host> [--named M:E[:S]] [--roster M:E[:S]]
```

`TIER` is `MODEL:EFFORT[:SPEED]` (speed `standard|fast`, default standard). Model IDs come from the
headless catalogs: Claude `headless/data/claude-models.json`, GPT `codex debug models --bundled`,
Grok `headless/data/grok-models.json`. The family is the ID prefix (`claude-`, `gpt-`, `grok-`).
Exit 3 → ask the owner (no tier named, or a roster tier on an inactive family). A model, effort
or speed missing from its catalog exits 2: a blocker to report, never a substitution. The output's
`escalation` and `fallback` are always `null`: both are asked of the owner (or named in the plan).

**Availability.** `~/.agents/skills/headless/data/families.json` is per user and untracked;
`install.sh` creates it from `families.example.json` with every family on. Set
`{"active": false, "reason": "..."}` for a family you cannot use. A missing file or family reads
as active. Inactive families are left out of menus and roster tiers on them exit 3; a tier the
owner names still resolves.

**Menus.** Build every tier question from `route.py menu [--family claude|gpt|grok]`: one line
per model of each active family, `<model-id><TAB><efforts>[<TAB>fast]`, read from the catalogs.
Never preselect an option or mark one "(Recommended)".

## 3. Routes per host

A tier whose family is the host's family uses the host's own helper; any other family uses the
headless wrapper.

| Host (`--host`) | Same-family `native` route | Everything else |
|---|---|---|
| `claude` | `subagent` with `model=<alias>` and `effort=<level>`, when the catalog maps an alias to that exact ID and speed is standard | `headless:<engine>` |
| `codex` | `native:codex` (GPT tiers) | `headless:<engine>` |
| `grok` | `native:grok` (Grok tiers) | `headless:<engine>` |
| `hermes`, `pi`, `other` | none | `headless:<engine>` |

**Exact-ID cases go headless** (`run-claude.sh`, which always pins the concrete ID): pinning an
older model (Opus 4.8, Sonnet 5, Fable 5), holding back a just-released model, fast mode (subagents
inherit the session's speed), reproducing or comparing a past run, and WarFleet units.

**Alias check.** In Claude Code the subagent tool only takes family aliases, so
`claude-models.json` records what each alias resolves to. After the run, verify the helper's
transcript: `route.py check-model --transcript <subagent jsonl> --expect <model id>` → `ok`,
`mismatch:<observed>` (the alias moved: update `aliases`) or `n/a` (no transcript found).

## 4. Failure ladder

| Failure | Next step | Counts toward escalation |
|---|---|---|
| Smoke test fails (`capability probe failed`) | launch the packet's **Fallback** (named by the owner or in the plan) at once | no |
| Launch, auth or tier error | report verbatim and stop; never switch family | no |
| Acceptance fails the dispatcher's re-run (1st) | same owner repairs, given the failing command and its output | yes |
| Acceptance fails again (2nd) | **ask the owner** for the escalation tier (menu from `route.py menu`; any family), then launch it fresh with the packet and both failure outputs | — |
| Escalated attempt fails | mark the task `blocked` and report | — |

Only `acceptance` failures (see `returned_by` in §5) move a task down this ladder. Seam, review and
dispatcher-check returns go back to the owner as ordinary repairs and never trigger escalation.

Nothing pre-sets the escalation tier, so no unusable tier is ever launched on its own. An
escalation is a fresh session either way, so crossing families costs no extra context and adds
different blind spots. For the reviewer, a family none of the task's owners used is the better pick
when one is available; the owner may name a same-family auditor (`capabilities.md` §5).

## 5. Outcome log and review

Every delegated task appends one line at close:

```sh
route.py log --plan <plan> --task <id> --task-type <type> --host <host> --project <dir> \
  --model <id> --effort <level> --route <route> --source <named|roster|asked> \
  --first-pass yes|no [--returned-by <list>|none] --repairs <n> \
  [--repaired-by original|fresh-helper|dispatcher|escalation] [--repairs-of <task>] \
  --status complete|done|partial|blocked [--escalated-to <id>] [--model-check ok|mismatch:<id>|n/a] \
  [--note "<evidence>"]
```

The log (`~/.agents/state/outcomes.jsonl`, outside every bundle repo, shared by every host) is append-only and holds no token or
cost fields. `--host` must be one of the `resolve` hosts (`claude, codex, grok, hermes, pi, other`);
`--status done` is stored as `complete`.

**Definitions**

- `first_pass` — `yes` when every check in the packet's **Acceptance** passed on the owner's first
  report (the dispatcher's re-run included). Returns for any other reason do not make it `no`.
- `returned_by` — a comma list of what sent the task back, or `none` (the default with
  `--first-pass yes`; required with `--first-pass no`):
  - `acceptance` — a check listed in the packet's Acceptance failed (e.g. `npm run build` exits 1,
    or the packet's `browser:` capture shows phone tabs collapsed to 0px).
  - `seam` — another task's report or the integration exposed a contract break (e.g. a shared type
    the next wave needs is missing a field).
  - `review` — the cross-family or final review raised a finding (e.g. R1 finds a rules bypass).
  - `dispatcher-check` — a check the dispatcher ran that is not in the packet (e.g. a live Fast 3G
    timing or a copy check during verification).

  Classification rule: *a failing check that is listed in the packet's Acceptance is `acceptance`,
  even if it is a `browser:` capture the dispatcher takes; a check not in the packet is
  `dispatcher-check`*. `--first-pass no` must include `acceptance`, and `--first-pass yes` must not
  (`log` and `correct` exit 2 otherwise).
- `repaired_by` — who did the repairs: `original` (the owner, resumed; default), `fresh-helper`
  (a new session at the same tier), `dispatcher`, or `escalation` (the tier the owner named after
the second acceptance failure).
- `repairs_of` — set on a row that exists only to repair another task (`--repairs-of <task>`).
  Repair rows are counted as `repair_rows` and left out of first-pass statistics.
  When the dispatcher repairs a helper's task itself, log one row such as `--task T1-dispatch
  --route dispatcher --repairs-of T1 --repaired-by dispatcher`, with `--note` citing the evidence
  (and "unrecorded" for a model or effort the record does not state).

**Corrections.** Never edit or delete a line. To fix a row, append a correction:

```sh
route.py correct --plan <plan> --task <id> [--date <YYYY-MM-DD>] [--host H] [--first-pass yes|no] \
  [--returned-by <list>|none] [--repairs N] [--repaired-by ...] [--repairs-of <task>] --note "<evidence>"
```

It appends `{"correction_of": {"plan", "task", "date"}, <fields>, "note", "corrected_on"}` and
validates like `log`. `--date` is needed only when the task has rows on several dates. Each
correction carries forward the fields of the previous one for that row, so the latest correction
merged over the original is the effective row; correction lines are never counted as runs. Classify
only from evidence; when the evidence does not show which check returned a task, pick the honest
best class and write "uncertain" in the note.

- `route.py review` — per task type × tier: `runs`, `first_pass` (passes over classified rows),
  escalated, blocked, alias mismatches, `returned_by` counts
  (acceptance/seam/review/dispatcher-check/unclassified) and `repair_rows`, plus `suggest:` lines
  for moved aliases, for legacy rows still unclassified (`first_pass` false with no
  `returned_by`), and for hosts outside the list. It informs the owner's next tier choice; it
  never picks one.
- `route.py validate` — the catalogs parse (the GPT one only where Codex is installed), every
  alias targets a Claude catalog row, and every family in `families.json` is known with a boolean
  `active`. Prints `routing_validate=clean count=0` or one `routing<TAB><finding>` line per
  problem and exits 1. The drift check runs it.

