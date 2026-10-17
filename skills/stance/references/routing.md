# Routing table — how a task gets its tier

**You don't need to fill this in.** The table is only a fallback: a model, effort or stance you
name yourself (`implement using <model-id> <effort> <chillin|vibin|supersoldiers>`, or a plan's
roster) always wins. When neither you nor the table names a tier, the agent simply asks you.
Stance is not in this table: unnamed means Vibin. Auditors are always named or confirmed by you.

Owner-approved tiers per task type, so routing is a lookup instead of a fresh decision. The data
is your copy `~/.agents/skills/stance/data/routing.json` (untracked; `install.sh` creates it from
`routing.example.json`, every tier empty); the tool is
`python3 ~/.agents/skills/stance/scripts/route.py` (stdlib only, works from any host). Capability
rules (lanes, browser, smoke tests, fallbacks, cross-family review) live in `capabilities.md`.

## 1. Schema

```json
{
  "families": {"claude": {"active": true}, "gpt": {"active": true}, "grok": {"active": true}},
  "task_types": {
    "<type>": {"desc": "...", "tier": TIER|null, "route": "native|headless",
               "escalation": TIER|null, "fallback": TIER|null, "notes": ""},
    "visual": {"desc": "...", "dispatcher_only": true}
  },
  "projects": {"/abs/project/path": {"task_types": {"<type>": {<any row keys to override>}}}}
}
```

`TIER` is `{"model": "<concrete id>", "effort": "<level>", "speed": "standard|fast"}` (speed
optional, default standard). Model IDs come from the headless catalogs: Claude
`headless/data/claude-models.json`, GPT `codex debug models --bundled`, Grok
`headless/data/grok-models.json`. The family is the ID prefix (`claude-`, `gpt-`, `grok-`).

Task types: `plan`, `mechanical`, `standard`, `hard`, `review`, `network`, and `visual`
(dispatcher only, never delegated). Classify each task by the hardest thing it must do.
The `review` row also serves `work-audit`, but only as the suggested auditor: auditor tiers are always named or confirmed by the owner, so `resolve --task-type review` fills the 'routing default' option of a question, never a silent pick.

## 2. Precedence

1. A tier **named in the current request** — always wins, even for an inactive family (the
   owner's availability call).
2. The **plan roster** (Orchestration row).
3. The **project override** (`projects[<abs path>]`), merged over the global row key by key.
4. The **global row**.

A global row may hold only `escalation` (and `fallback`) with `tier: null`: the owner names the
first-pass tier per request, and the row still supplies the failure ladder. No tier at any level, or a table/roster tier in an inactive family → `resolve` exits 3: ask the
owner for that row only (words-as-ask; never a default). A model or effort missing from its catalog
exits 2: a blocker to report, never a substitution.

## 3. Routes per host

`route: native` uses the host's own helper when the tier's family is the host's family; otherwise,
and always for `route: headless`, the headless wrapper.

| Host (`--host`) | Same-family `native` route | Everything else |
|---|---|---|
| `claude` | `subagent` with `model=<alias>` and `effort=<level>`, when the catalog maps an alias to that exact ID and speed is standard | `headless:<engine>` |
| `codex` | `native:codex` (GPT rows) | `headless:<engine>` |
| `grok` | `native:grok` (Grok rows) | `headless:<engine>` |
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
| Smoke test fails (`capability probe failed`) | launch the row's `fallback` at once | no |
| Launch, auth or tier error | report verbatim and stop; never switch family | no |
| Acceptance fails the dispatcher's re-run (1st) | same owner repairs, given the failing command and its output | yes |
| Acceptance fails again (2nd) | launch the row's `escalation` tier — **any family** — fresh, with the packet and both failure outputs | — |
| Escalated attempt fails | mark the task `blocked` and report | — |

Only `acceptance` failures (see `returned_by` in §5) move a task down this ladder. Seam, review and
dispatcher-check returns go back to the owner as ordinary repairs and never trigger escalation.

An escalation is a fresh session either way, so crossing families costs no extra context and adds
different blind spots. For the reviewer, a family none of the task's owners used is the better pick
when one is available; the owner may name a same-family auditor (`capabilities.md` §5).

## 5. Outcome log and review

Every delegated task appends one line at close:

```sh
route.py log --plan <plan> --task <id> --task-type <type> --host <host> --project <dir> \
  --model <id> --effort <level> --route <route> --source <named|roster|project|global> \
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
  (a new session at the same tier), `dispatcher`, or `escalation` (the row's escalation tier).
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

- `route.py review [--min-fails 3]` — per task type × tier: `runs`, `first_pass` (passes over
  classified rows), escalated, blocked, alias mismatches, `returned_by` counts
  (acceptance/seam/review/dispatcher-check/unclassified) and `repair_rows`, plus `suggest:` lines
  for the nudge rule, for legacy rows still unclassified (`first_pass` false with no `returned_by`),
  and for hosts outside the list. It never edits the table; the owner does.
- `route.py nudge --task-type T --model M --effort E [--min-fails 3]` — exits 1 with one line when,
  among the **last 10 classified non-repair rows** for that task type × tier (file order), acceptance
  failures are 3 or more **and** the first-pass rate is below 50%. Unclassified legacy rows and
  repair rows do not count. Implement prints it at close.
- `route.py validate` — every tier, escalation and fallback exists in its catalog (inactive
  families skipped), every project path exists, every alias targets a catalog row. The drift check
  runs it.

## 6. Changing the table

Edit `routing.json` (or ask the session to), then run `route.py validate`. To add a project
override, add its absolute path under `projects` with only the keys that differ. To reactivate
Grok, set `families.grok.active` to `true`, confirm its rows, and run
`~/.agents/skills/headless/scripts/resolve-grok-model.sh`.
