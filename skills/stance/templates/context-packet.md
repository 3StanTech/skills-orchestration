# Context packet — <task id / step>

Give this to one helper. Keep it under a screen; link, don't paste, anything long. Check it before
launch: `python3 ~/.agents/skills/stance/scripts/packet-check.py <this file>`.

**Goal:** <one sentence: the outcome this helper delivers>

**Task type:** <plan | mechanical | standard | hard | review | network>

**Working directory:** <absolute path>

**You own (only these files):**
- `<path>` (append ` (new)` for a file this task creates, ` (delete)` for one the dispatcher removes; notes after the path are ignored)
Read-only review (task type `review`): the single bullet `none (read-only)`; acceptance may then be
`report: findings list in the Report format`.

**Do not touch:** <files other helpers own, generated files, secrets, `.env`>

**Contracts and interfaces you must respect:**
- <function signatures, data shapes, routes, tokens, API contracts this task touches — with paths>

**Rules that bind here:** <project hard rules from its AGENTS.md / CLAUDE.md that apply to this task, quoted or linked>
- A permission, classifier or hook refusal of an intended action stops that action: never retry it
  with another tool; report it verbatim in BLOCKERS. A lane's sandbox limit is not a refusal: switch
  to a method that fits the lane. Full rule: `~/.agents/skills/headless/references/contract.md` §5b.
- Long tasks only: at each checkpoint (a file finished, a test green), append one line to
  `<run-dir>/<task>-wip.md`: what is done, what is next.

**Already done / context you would otherwise re-read:**
- <decisions, prior waves' outputs, relevant file summaries — enough to skip exploration>

**Smoke test:** <first command to run before any work, e.g. `curl -sS -o /dev/null -w '%{http_code}' <url>`; on failure stop with `STATUS: blocked` and `NOTES: capability probe failed at start — no task work attempted.` Write `none` when the task needs no network or other ⚠️ capability>

**Fallback:** <tier/route the dispatcher launches if the smoke test fails, or `none`>

**Acceptance (all must pass; the dispatcher re-runs these):**
- <`runnable command` and its expected result, e.g. `python3 -m unittest` passes>
- <or `browser: <capture the dispatcher takes>` for visual criteria>

**Report format:** end with exactly:
```text
STATUS: done | blocked
FILES: <files changed, or none>
BLOCKERS: <verbatim error and what you tried, or none>
NOTES: <one line>
```
