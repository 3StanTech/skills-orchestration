# WarFleet late phases — General, casualties, debrief, final review

Loaded on demand, the first time an Infantry unit reports `STATUS: blocked` or a wave completes and
needs its gate check. A clean single-wave run never pays for this file.

The dispatcher contract from `SKILL.md` still holds throughout: you copy artifacts and fire commands;
the General and the Admiral hold all judgment.

---

## Phase 3 — Commission the General (lazily)

Launch the General the **first time** either trigger fires: (a) an Infantry unit reports
`STATUS: blocked`, or (b) wave 1 completes and needs its gate check. A clean single-wave run pays for
the General exactly once, at debrief.

Launch it at the exact `muster.general` family, concrete model, effort, speed, executor, and lane A
read-only. The General must never be routed through an unrelated wrapper or silently replaced by an
Infantry family:

- **Codex General:** native-agent or `codex exec` at lane A.
- **Claude General:** `../headless/scripts/run-claude.sh --lane A` (lane A denies edit tools).
- **Grok General:** `../headless/scripts/run-grok.sh --lane A`.

Its brief must contain:

- The full approved plan + roster, **verbatim from `warfleet-plan.md`**.
- `mission-context.md`.
- Its role, stated exactly:
  > You are the General. You do not write code and you do not re-decompose the plan. You adjudicate
  > Infantry blockers, gate wave transitions, and verify results against the roster's acceptance
  > criteria. Your replies must be structured orders.
- **Its required output contract** — every reply ends with:
  ```
  VERDICT: pass | fail
  RESUME: yes | no        (resume the unit's own thread, or spawn fresh)
  ESCALATE: yes | no
  NEXT: <task id(s) to launch, or none>
  ORDER: <the remediation instruction, verbatim-ready for the unit's prompt>
  ```

**Continuity.** Record the General's session id in `<state>/external-threads.json`. Every later
consultation resumes it — Codex: `codex exec resume` or the wrapper's `--resume`; Claude: `--resume`; Grok:
`-r <uuid>`. **Send deltas only**: task id + footer block + question.

**Wave gates.** Before firing wave N+1, send the General wave N's footer blocks and ask it to verify
each task against its acceptance criteria. Only a green-lit wave unlocks the next.

**Clarification-contract gate.** At the first wave gate and again at debrief, the General formally
verifies that the plan was finalized only after `CLARIFICATIONS: none`, and that recorded
clarification rounds complied: at most six questions per round; one-to-three questions in one batch
and four-to-six in exactly two sequential order-preserving batches; answers returned together to the
same Admiral thread; rounds repeated with no total-round cap; dispatcher never reworded, merged,
answered, or invented questions. Fail the gate if any of that is missing or violated.

**Budget honesty at the gate.** Each footer's `subagents_used=<actual>/<max_total>` goes to the
General unchanged. Usage **above** the ceiling is a roster violation — fail the gate. Usage well
**below** is not a problem.

---

## Phase 4 — Casualty protocol

### Launcher/environment failures before unit work

If the wrapper rejects a caller-supplied `--sandbox`, `--no-memory`, or `--verbatim` flag, stop at
the launcher contract and report the exact error. It is not a task failure, so do not commission the
General, reassign the task, or ask the commander to approve a different family.

The Grok wrapper makes one attempt and never retries from output text. Only
independent evidence of a pre-work sandbox initialization failure permits the
standing one-time Lane C recovery. Preserve model, effort, speed, recorded session,
prompt and task; log the evidence and recovery once, do not append a second task row,
and do not show another private-context or Lane C approval prompt. If task progress
is uncertain or that recovery fails, use the ordinary casualty protocol below.

When a unit reports `STATUS: blocked`, fails its wave gate, or returns a failure:

1. Send the **General** the unit's footer block + task id, commissioning it now if this is the first
   trigger.
2. The General returns its structured order. **You do not evaluate it.**
3. Dispatch exactly as ordered:
   - `RESUME: yes` → relaunch the unit's own thread from the registry with `ORDER` as the prompt.
   - `RESUME: no` → relaunch fresh from the manifest's `argv`, with `ORDER` as the prompt.
   - Either way, keep the same `# warfleet-task:<id>` tag and the same approved flags.
4. **A capability-probe block takes the pre-approved fallback** named in the roster, if the task has
   one — a one-line reassignment inside the same wave, no General, no remediation round.
5. **If the order creates a task not in the approved roster**, muster-scope authorization does not
   cover it. **Ask the user for model + effort** using the exact popup for that role with no defaults,
   then append the new entry to `~/.claude/warfleet/auth-<session-id>.json` and launch it tagged.
   Re-run `validate-manifest.py --auth` afterwards. The auth file is only ever extended by a fresh
   user answer.
6. **The workload split governs the approved roster, not remediation.** Retries need not preserve the
   split.
7. **Cap: 3 remediation rounds per task.** After that, or if the General says the master plan itself
   is wrong, halt that line and escalate to the user. If the plan must change materially, that is a
   return to Phase 1 — the Admiral re-plans, the user re-approves, and `warfleet-plan.md` plus
   `warfleet-launch.json` are rewritten and re-validated.

---

## Phase 5 — Debrief

1. Send the General the final wave's footer blocks plus the battle log. Ask it to confirm every task
   passed its acceptance criteria and the plan's overall verification step. Interior waves were
   already gate-verified — the debrief is a diff, not a re-audit. Re-confirm the clarification-contract
   gate: plan finalized only after `CLARIFICATIONS: none`, and recorded round/batch behavior complied.
2. Run the plan's verification step (tests / build / manual check) **for real**. Do not take the
   General's word alone.

---

## Phase 6 — Final review (verdict + polish)

**Who runs it.** The **secondary Admiral** when one was mustered; otherwise the primary. The secondary
reviews the **final outcome**, not routine orchestration decisions.

### Review depth

Final review may be lightweight only when complexity, behavioral risk, and required
acceptance make a separate deep pass unnecessary. File count is not a proxy. Record
the Admiral's rationale; required independent judgment is never removed by stance.

### Running it

Launch the reviewing Admiral at its muster tier — this time with edit rights (Codex: lane B; Claude:
no `--disallowedTools`; Grok: `run-grok.sh --lane B`). The muster answer was the ask, so there is no
re-ask. Give it: `warfleet-plan.md` verbatim, `mission-context.md`, the battle log, the General's
debrief verdicts, and the set of files changed.

Its orders:

1. **Verdict** — `SUCCESS` / `PARTIAL` (list exactly what is unmet) / `FAIL`. Independent judgment.
2. **Polish** — **read-only runs have nothing to polish.** If zero files were touched, say so in the
   prompt explicitly and verify with `git status --short`. Otherwise, edit the touched code to the
   Admiral's standards: behavior-preserving only, scoped to files the run touched.
3. **Final-review fixes.** The reviewing Admiral may fix in-scope defects discovered
   during legitimate final review. Missing core deliverables return to the same
   implementer before review resumes. No new features, redesign, unrelated refactors,
   or phase-label takeover.
4. After review edits, **re-run affected checks and integration verification**.

### Two-Admiral disagreement

If the secondary Admiral's verdict contradicts the primary's plan in a way that changes what "done"
means, **stop and ask the user to arbitrate.** Do not average the two.

### Close out

5. Report to the user: outcome first (led by the Admiral's verdict), then the battle log as a
   per-task status table, deviations, files changed, and a short list of what the polish pass cleaned
   up. **Never report accumulated cost.**
6. Delete `~/.claude/warfleet/auth-<session-id>.json`. The run is over, so its authorization is too.
