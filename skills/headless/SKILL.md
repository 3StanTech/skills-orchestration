---
name: headless
description: >-
  Launch a separate CLI worker — Claude Code, Codex (GPT) or Grok — with an
  explicit model, effort, speed, permission lane and resumable session, and relay
  its report. Trigger: /headless, "implement using <GPT or Grok tier>", "have
  codex/gpt/grok do this", "ask grok", "headless claude", a plan Orchestration row
  whose Route is headless, or any WarFleet unit launch. Use for GPT/Grok helpers,
  work that must be resumable after the session, or fast-mode Claude helpers. Not
  for ordinary Claude helpers (in-session subagents; see stance).
---

# Headless

Run one task in a separate CLI process on an explicitly chosen engine and tier, then relay
its result. Paths below are relative to this skill's folder
(`~/.agents/skills/headless/`).

## 1. Pick the engine from the tier

| Tier named | Engine | Wrapper | Tier authority | Reference |
|---|---|---|---|---|
| `claude-*` | Claude Code | `scripts/run-claude.sh` | `data/claude-models.json` | `references/engine-claude.md` |
| `gpt-*` | Codex | `scripts/run-codex.sh` | `codex debug models --bundled` | `references/engine-codex.md` |
| `grok-*` | Grok Build | `scripts/run-grok.sh` | `data/grok-models.json` via `scripts/resolve-grok-model.sh` | `references/engine-grok.md` |

Read `references/contract.md` once per delegation (lanes, prompt and report contract,
continuity, git-push rules), then the engine reference. Which lane, family and owner a capability
needs (network, browser, writes outside the workspace) is in
`~/.agents/skills/stance/references/capabilities.md`.

## 2. Get an explicit tier

- Model and effort are both required, plus speed for Claude. **Words-as-ask:** a tier the
  user already named is the answer; ask only for a missing half, in one question round.
  Extraction, not inference.
- **An approved routing-table row is explicit too.** With no named tier, resolve it:
  `python3 ~/.agents/skills/stance/scripts/route.py resolve --task-type <t> --host <host>`
  (`stance/references/routing.md`). A named tier overrides the table; exit 3 means ask the owner
  for that row only. Families marked inactive in `stance/data/routing.json` (e.g. one you have no
  subscription for) are not offered unless the user names them. **Auditors are the exception:** a
  routing row never approves an auditor on its own; the owner names or confirms it.
- Build menus from the tier authority above, never from memory. Never mark a tier
  "(Recommended)" and never preselect one.
- An approved plan roster or WarFleet muster is explicit.
- A model missing from its catalog is not a substitution cue. Record it at plan time: ask
  the user for its efforts (and Claude fast support), add the row to the data file, then
  continue.
- Never drop or substitute a model family; availability is the user's call. `grok models`
  printing "not authenticated" is a known false negative.

## 3. Launch through the wrapper only

- Use the wrappers, one literal invocation per command, with `--cwd`, `--lane A|B|C`,
  `--model`, `--effort` (and `--speed` for Claude and Codex) and one prompt source
  (`--prompt-file` for anything long).
- Lane C needs `--approve-lane-c yes`.
- Claude lanes A/B: pass the plan's **Allowed checks** with `--allow-tools "<rule>,<rule>"`
  (permission rules such as `Bash(npx vitest run:*)`, forwarded as `--allowedTools`), so a
  helper runs its own checks in any project without a per-project allow list.
- WarFleet units also pass `--auth <auth file> --task-id <id>`; the wrapper refuses any tier
  that differs from the approved entry.
- `~/.agents/hooks/headless-launch-guard.py` blocks raw `codex exec`, `grok` and
  `claude -p` launches that bypass the wrappers. If it blocks, ask; never reshape the command
  to slip past it.
- Run long workers with the host's background execution and bounded waits. Record the
  session or thread ID; repairs resume the same session.

## 4. Host view

- **From Claude Code:** all three engines run through these wrappers.
- **From Codex:** GPT helpers may use Codex's native agents instead; Grok and Claude run here.
- **From Grok:** Grok helpers may use Grok's native subagents; GPT and Claude run here.
- **From Hermes, Pi or any other host:** all three engines run through these wrappers.

## 5. Report

- For a standalone request, relay the worker's final report and footer verbatim.
- Inside orchestration, return the compact evidence the stance calls for and keep the
  original report as an artifact.
- Preserve exact errors. A launch failure never authorizes local takeover or a different
  model.

## Guardrails

- Never pass a moving alias; use concrete IDs only.
- Never `--bare` or `--safe-mode` for Claude (both skip hooks).
- Browser work and `git push` stay with the dispatcher.
- Never edit auth files, strip tags, or bypass a guard.
- After changing a wrapper, catalog or reference, run `python3 -m unittest discover -s tests`,
  `sh tests/test-run-grok.sh` and `sh tests/test-run-codex.sh`, then the drift check.
