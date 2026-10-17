# WarFleet muster — the clickable roster contract

Loaded at the very start of a run, before anything is read or analysed.

## Non-negotiable UI contract

- **Never ask a question the user has already answered.** See "Words-as-ask" below. Everything else
  in this file describes what to do with the questions that *remain*.
- **Three sequential host-native questions, one question each.** Popups 1–3 pick the roster.
  Never combine them, and never add extra stance, speed, allocation,
  parallelism, or additional-tier popups. Wait for each answer before showing the next.
- **The free-form `Other` box is the escape hatch** for anything the menu does not list — a second
  Admiral, a share split, a role instruction, an off-menu tier, or **`fast`** on a model that
  supports it (`Opus 5 High fast`, `GPT Sol High fast`, `Luna max fast`). The compiler understands
  all of it. `fast` on Grok, Fable, or Sonnet is `INVALID` — those models have no fast mode.
- **Only the root dispatcher may call the clickable-input tool.** If WarFleet is somehow entered
  inside a subagent, hand the tool-shaped question back to the root. Use available native
  controls (for example `request_user_input` in Plan Mode or `request_user_input_async`
  outside it). If none are available, ask the unchanged question and choices in chat.
  Wait for required answers; preselected defaults and elapsed time are not answers.

## Words-as-ask — skip what the user already told you

**A tier the user states in their request IS the answer to that question.** Do not re-ask it, do not
"confirm" it with a popup, and do not treat the popup as more authoritative than their words.

```
/warfleet <goal> [--admiral <model>/<effort>] [--general <model>/<effort>]
                 [--infantry <model>/<effort>[,<model>/<effort>…]]
                 [--split <fam><pct>/<fam><pct>]
```

Prose counts too: *"warfleet this with Opus 5 high as admiral, Grok 4.6 xhigh infantry, vibin"*
answers popups 1 and 3 plus the stance. Any unnamed roster role still gets its popup.

**Implementation-performance language selects `supersoldiers` only inside a WarFleet run
(user-set, 2026-08-20; corrected the same day).** Outside `/warfleet`, those phrases mean "spawn as
many subagents as needed of the named model+effort" and must **not** start Admiral/General popups.
Inside `/warfleet`, they set the stance only. Explicit stance tokens, not difficulty
inferences:

- "use as many [family] subagents as necessary"
- "as many as needed" / "as many subagents as needed"
- "as fast as possible without sacrificing quality" / "without sacrificing output quality"
- Canonical shorthand: *implement using grok 4.5 high supersoldiers* (any named Infantry tier +
  `supersoldiers`)

**This is extraction, not interpretation — and that distinction is what keeps it compatible with the
dispatcher's "never read the goal" rule.** You are pulling out explicit tier tokens (a model name, an
effort word, a percentage, or the word `fast`) and explicit stance words (`Supersoldiers`, `Vibin`,
`Chillin`, plus the performance-language aliases above). You are
**not** inferring intent, difficulty, or which model would suit the task. If a request merely
*implies* a tier — "use something cheap", "this is hard, go big" — that is **not** an answer: show
the popup. When genuinely unsure whether a phrase names a tier, show the popup; an extra question
costs seconds, a wrong silent tier costs a whole run.

Feed whatever you extracted straight into `parse-muster.py` as that role's raw answer, exactly as if
it had come back from the popup. The compiler validates it identically and still fails rather than
guessing, so a misread loadout is caught mechanically instead of launching.

If **every** question is answered in the request, run no popups at all — but still run the compiler,
still show the plan, and still require explicit approval. Words-as-ask replaces the *questions*, never
the *approval*.

### The three hard muster rules (the user set these — never violate)

- **No defaults, ever.** Every model and every effort is chosen explicitly, every run. **Never append
  "(Recommended)" to an option label, never pre-select, never carry a choice over from a previous
  run.** This has been violated in a real run — a live muster shipped `medium (Recommended)` because
  fit-guidance meant for the model's own reasoning leaked into the menu text. Treat it as an
  invariant, not a guideline. If you find yourself about to write "(Recommended)", that is the bug.
- **Every question is role-scoped, never family-scoped.** Ask "Fleet Admiral: model + effort", never
  "which model should Codex units use" — a family-scoped question wrongly forces one GPT tier across
  roles, when the user may well want GPT Sol as General and GPT Luna in Infantry.
- **Menus list exactly the options in this file.** `max` and `ultra` may appear when a menu option
  names them. The compiler still honors any supported tier the user names in `Other`. There is no
  "escalate beyond the menu" follow-up.

## The three roster popups

The payloads below are canonical question data, not a claim about a host tool schema.
Ask them in order and preserve their text, choices, and answer-to-role mapping. Adapt
only the envelope to the available tool: async uses `title` and string `options`, while
Plan controls use `header`, `id`, `question`, and object `options`. Do not pass unsupported
keys such as `multiSelect`. Respect the host's option/question caps; if a cap cannot fit
the complete menu, show it unchanged in chat and collect the answer rather than dropping
a model or adding a fake choice. Preserve natural-language answers verbatim for parsing.

### Popup 1 — Fleet Admiral

~~~json
{"questions":[{"header":"Fleet Admiral","id":"fleet_admiral","question":"Fleet Admiral: model + effort?","multiSelect":false,"options":[{"label":"Opus 5 High","description":"Claude Opus 5 at high effort, standard speed."},{"label":"Grok 4.6 High","description":"Grok 4.6 at high effort, standard speed."},{"label":"GPT Sol High","description":"GPT Sol at high effort, standard speed."},{"label":"Fable 5 High","description":"Claude Fable 5 at high effort, standard speed."}]}]}
~~~

To muster a **second Admiral** — one that reviews the draft plan and owns the final review — the user
types both in `Other`, joined by `+`: `Opus 5 high + GPT Sol high`. One or two is the accepted range.

> **The instant Popup 1 returns: launch the Admiral's Stage A recon in the background, and go
> straight to Popup 2 without waiting for it.** Do not poll it, do not read its output, do not mention
> it again until Stage B. Answering two more questions takes seconds; reading a codebase takes
> minutes. Blocking here throws away the entire reason the muster is split. If the session is already
> in plan mode, stay there; do not require a Claude-only plan-mode flip.

### Popup 2 — General

~~~json
{"questions":[{"header":"General","id":"general","question":"General: model + effort?","multiSelect":false,"options":[{"label":"GPT Sol High","description":"GPT Sol at high effort, standard speed."},{"label":"Grok 4.6 High","description":"Grok 4.6 at high effort, standard speed."},{"label":"Opus 5 High","description":"Claude Opus 5 at high effort, standard speed."},{"label":"Grok 4.6 Medium","description":"Grok 4.6 at medium effort, standard speed."}]}]}
~~~

### Popup 3 — Infantry

~~~json
{"questions":[{"header":"Infantry","id":"infantry","question":"Infantry: model + effort?","multiSelect":false,"options":[{"label":"Grok 4.5 High","description":"Grok 4.5 at high effort, standard speed."},{"label":"GPT Luna XHigh","description":"GPT Luna at xhigh effort, standard speed."},{"label":"GPT Luna Max","description":"GPT Luna at max effort, standard speed."},{"label":"GPT Terra High","description":"GPT Terra at high effort, standard speed."}]}]}
~~~

**Multiple Infantry tiers** go in `Other`, comma-separated: `Grok 4.5 high, Luna xhigh`. A **fixed
task-count split** appends a percentage per tier: `Grok 4.5 high 70, Luna xhigh 30` — every tier
needs a share and the shares must total 100, or the compiler rejects the answer rather than guessing.

**Every Grok pick must name a version and an effort** (`Grok 4.5 High`, `Grok 4.6 xhigh`). A bare
`Grok` in `Other` — no version, no effort — is `INVALID`. Show the line and re-ask that role. Do not
open a fifth popup. `Grok high` (effort, no version) is also invalid: ask for the missing
version. `resolve-grok-model.sh` provides discovery only, never authorization.

### Stance — stated or announced default

If words-as-ask named `Supersoldiers`, `Vibin`, or `Chillin`, preserve it. Otherwise
announce exactly: **“No stance was specified, so I’ll use Vibin.”** Do not show a
stance popup. Record `source: stated|defaulted`. The stance binds optional allocation
across the run, including internal Infantry subagents; it does not alter required roles.

~~~json
No popup is emitted here.
~~~

The Admiral reads the compiled stance at Stage B and writes each Infantry task's `subagents.max_total`
**after** that task is broken down. There are no hard numeric bands. A budget is a ceiling, never a
target; a unit may use zero.

**Efficiency binds every stance**, but the trade-off is not the same:

- `vibin` / `chillin` — smallest token-cost that still wins on quality and speed.
- `supersoldiers` — **as many as needed.** Progress and speed outrank cost. Plan the task first, then
  set the cap to every helper that materially moves the work forward. No "stay moderate" bias. Still
  no wasted helpers and no "just in case" padding — efficiency here means "don't spawn what does not
  help," not "keep the number small."

| Stance | How the Admiral sets `max_total` |
|---|---|
| `supersoldiers` | As many as the planned work needs for progress and speed. Cost is secondary. The rationale names those helpers. A simple task may still be `0`. |
| `vibin` | Selective useful concurrency; no fixed count or mandatory reviewer |
| `chillin` | Minimum optional allocation; required independent checks remain |

The stance applies to every chosen Infantry model unless the user stated otherwise (role `Other` /
`=` instructions). Squads stay a separate Admiral call.

These three calls are the complete muster. Clarifications the Admiral raises later are **not** muster
questions.

Grok efforts still differ per model. When compiling a Grok answer, run
`../headless/scripts/resolve-grok-model.sh` first. `grok-4.7` has the user-selected `medium` route recorded; `grok-4.6` has `xhigh`; `grok-4.5` does not.
`grok_unknown=<id>` asks the user which efforts to record in the shared `~/.agents/skills/headless/data/grok-models.json`.
`grok_resolution=fallback` uses the known set, says so in one line, and never drops Grok.

## Mechanical normalization — never interpret an answer yourself

Discover available Grok IDs when needed, then compile the explicit user selections.
Discovery does not fill a missing model choice. Both commands are read-only:

```bash
../headless/scripts/resolve-grok-model.sh
scripts/parse-muster.py \
  --admiral "<answer 1>" --general "<answer 2>" --infantry "<answer 3>" \
  [--infantry-subagents "<stated stance>"] \
  --grok-model "<resolved id>" --output "<state>/warfleet-muster.json"
```

The compiler accepts friendly aliases and case-insensitive prose, supports one or two Admirals,
exactly one General and one or more Infantry tiers, preserves text after `=` as role instructions,
defaults omitted speed to `standard` while preserving an explicit `fast`, pins Grok, compiles the
Infantry-subagent stance, and **fails with `INVALID:` on anything ambiguous instead of guessing**.
Its output is canonical; the three roster answers and stated/defaulted stance are preserved as authorization
evidence.

**If it exits non-zero, do not repair the answer.** Show the user the exact `INVALID:` line and
re-ask that one popup.

## Defaults that replace old muster questions

These are **mechanical resolutions of questions that are never asked** — not pre-selected menu
answers. That distinction is what keeps them compatible with the no-defaults rule, and a future
editor should not "fix" it: the ban is on presenting the user a choice with a thumb on the scale, not
on the system having deterministic behavior where no choice is offered.

| Dimension | Resolution |
|---|---|
| Speed | `standard`, unless the answer explicitly says `fast` (GPT any model; Claude Opus 5 / 4.8 only) |
| Allocation | Task fit, unless fixed percentages are present |
| Parallelism | Parallelize independent tasks; serialize browser driving and overlapping file edits |
| Subagents | Stated stance or announced Vibin default; size each Infantry `max_total` from task need |
| Grok speed | `standard` always — Grok has no fast-mode control. Its model and effort must be named on the role popup or in `Other` |
| Infantry subagents | Stated stance or announced `vibin` default. Size each task ceiling from task need. |
| Dispatcher | Runs at low effort by design; never infer or change the current session model |

## Admiral-owned clarifications

**The primary Admiral alone decides whether the goal needs clarification** and may ask **up to six
individual questions per round**. The dispatcher has not read the goal and must not start now.

Stage A recon ends with either `CLARIFICATIONS: none` or up to six questions in the exact
`request_user_input` shape. Then:

1. The root dispatcher validates **schema and the six-question round ceiling only** — six or fewer
   questions, each with a header, a question, and 2–4 options. It does not judge whether they are
   good questions. It **never rewords, merges, answers, or invents** questions.
2. For a host accepting **at most three questions per call**, relay the round **unchanged**
   in sequential batches that preserve order: **one batch** for one-to-three questions; **exactly two
   batches** for four-to-six. Never compress, reorder, or rewrite across batches.
   On other hosts, use their actual cap; plain chat can relay the same ordered questions.
   Adapt envelopes only, preserve the complete round, and wait for all required answers.
3. Return all answers from the round **together** to **the same Admiral thread**.
4. Repeat rounds until the Admiral returns `CLARIFICATIONS: none`. There is **no total-round cap**.

If the objects are malformed, resume the Admiral and ask for corrected ones — do not rewrite them
yourself. Stage A may overlap the remaining muster questions; do not claim time savings without evidence.

## Authorization and no substitution

The three answers, recorded stance, and user's plan approval authorize **exactly** the compiler's canonical roster
and nothing else. Every launch preserves the exact family, model, effort, speed, lane, and session
id. For GPT, `fast` maps to `service_tier: priority`. For Claude Opus, `fast` maps to session-scoped
`fastMode: true` and `standard` maps explicitly to `false`, so a unit can never inherit or mutate the
user's global preference. **A failed health check never silently removes or replaces a selected
model** — availability is the user's call.

## Required unit footer

Every task prompt ends exactly with:

~~~text
STATUS: done | blocked
FILES: <files changed, or none>
BLOCKERS: <verbatim error and what you tried, or none>
NOTES: <one-line anything else the commander must know>
~~~

When a task carries a subagent budget, `NOTES` begins with `subagents_used=<actual>/<max_total>;`.
