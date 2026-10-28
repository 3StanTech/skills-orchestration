# Delegation core — the shared contract

The rules every headless worker obeys. The engine references (`engine-codex.md`, `engine-grok.md`, `engine-claude.md`) each state only their engine-specific facts and defer here for everything else. Read this once per delegation; it is the single place these rules are defined, so the engine skills cannot drift apart.

## 0. Maintenance contract — read before editing any of these skills

The delegation skills describe **one system from three angles**. A fact corrected in only one of them does not improve the system; it creates a contradiction the next reader cannot resolve. So:

**An enhancement to non-Claude model integration is not finished until every relevant skill carries it.** Today that set is `headless` (this skill and its three engine references), `stance` (its SKILL.md and `references/{capabilities,routes}.md`) and `warfleet` (one copy at `~/.agents/skills/warfleet`, symlinked into `~/.claude/skills`). Treat it as open — any future skill that routes work to an external model CLI joins it automatically.

**Route each fact to exactly one home; reference, never paste:**

| Fact type | Home |
|---|---|
| Shared contract — courier framing, lanes, continuity, prompt building, footer block, refusal rule, relay-verbatim, cost model | **this file** |
| Engine-specific — flags, sandbox behavior, auth, quirks | that engine's `SKILL.md` |
| Capability routing — lane by capability, family by task shape, browser rule, smoke tests, fallbacks, cross-family review | `~/.agents/skills/stance/references/capabilities.md` |
| Tier source and routes — named tier, approved roster or ask; family availability (`headless/data/families.json`); menus (`route.py menu`); routes per host; failure ladder (escalation asked); outcome log | `~/.agents/skills/stance/references/routes.md` |
| Orchestration — muster, roster, waves, dispatcher contract | `warfleet/SKILL.md` |

**Before calling an edit done, run the drift check and grep every skill in the set for the
superseded claim:** if the `workspace-hygiene` skill is installed, its drift check (`python3 ~/.agents/skills/workspace-hygiene/scripts/check-drift.py`) catches
fork drift, stale model ids, effort tables outside their owner, broken links and dead paths;
the grep catches prose it cannot. Two real failures came from skipping this: the Grok route once asserted both that Grok has and has not got network in lanes A/B, and both engine skills kept "recommend medium"-style guidance after recommendations were banned — which is exactly how `medium (Recommended)` reached a live muster. Verify with a checklist pass; do not assume propagation happened because you intended it.

## 0b. Never assert a delegate's incapacity without checking

**Before telling the user a delegate cannot do something, look.** 
A claim that Codex or Grok "can't do X" is a factual claim about a CLI installed on this machine, and it is checkable in seconds. Making it from memory is how the user gets told to do work by hand that the tool would have done — it already happened once (see the engine skills' confirmed-capability tables).

**The probe, in order — all read-only, none starts a model, none is billed:**

| Step | Command |
|---|---|
| Flags and subcommands | `codex --help` · `grok --help` |
| Bundled + user skills (the real capability surface) | `ls ~/.codex/skills ~/.grok/skills ~/.grok/bundled/skills` |
| Tool names inside a skill | `grep -ril "<capability>" ~/.grok/bundled/skills ~/.grok/skills ~/.codex/skills` |
| Configured MCP servers | `~/.codex/config.toml` · `~/.grok/config.toml` · `grok mcp doctor` |
| Evidence the feature has run before | artifact dirs, e.g. `~/.codex/generated_images/` |

The engine skills' own SKILL.md files are **not** an authority on what the CLI can do — they are a summary that goes stale every time the vendor ships. Disk is truth.

**Phrase honestly when you haven't checked.** "I don't know whether Grok can generate images — let me check" costs one tool call. "Grok can't generate images" costs the user the capability.

**Two failure directions, both real:**
- *Asserting absence* — the failure above. Cheap to avoid; always probe first.
- *Asserting presence* — configured ≠ usable. `chrome-devtools` is configured for both engines and still dies in every sandboxed lane (see §4). Confirm the capability works **in the lane you plan to use**, not merely that it exists.

### Confirmed capabilities — verified on this machine, do not re-litigate

Each engine's confirmed-capability table lives in its route skill, next to its flags — Grok in
`references/engine-grok.md`, GPT in `references/engine-codex.md`, Claude in `references/engine-claude.md`. Add a row there when a probe settles something; correct it when reality changes. Only the cross-engine row stays here:

| Engine | Capability | Status | How it is reached |
|---|---|---|---|
| Both | Browser via `chrome-devtools` MCP | ✅ exists, ❌ unusable in sandboxed lanes | Lane C only. See §4. |

When a delegated task depends on a capability marked ⚠️, open the prompt with the smoke-test pattern in §4 so the delegate discovers a dead tool in its first thirty seconds rather than its last.

## 0c. Engine defaults are hostile — pin everything, every call

Neither engine is safe unflagged, and the two are unsafe in different ways.

| Engine | What an unflagged call inherits | Pin it with |
|---|---|---|
| Codex | the stored `model`, `model_reasoning_effort` and `sandbox_mode` in `~/.codex/config.toml` — **read them live, never quote them from a document** (they drift). The sandbox setting has been observed as full access, i.e. no sandbox at all | `-m`, `-c model_reasoning_effort=`, and `--sandbox` (or `-c sandbox_mode=` on the `resume`/`review` subcommands, which do not accept `--sandbox`) |
| Grok | its own default effort | `-m <resolved id> --effort <level>`, always both; the level must be one the model actually accepts (§3b) |

The wrappers exist to make this unforgettable: `scripts/run-grok.sh`, `scripts/run-codex.sh`
and `scripts/run-claude.sh` refuse to launch without the flags that matter, and gate lane C behind
an explicit `--approve-lane-c yes`. Prefer them over a hand-built command line. All three are recognized by name in `~/.agents/hooks/headless-launch-guard.py`, which blocks any raw engine launch that bypasses them — **renaming one without updating the guard opens an unguarded path.**

## 1. Courier and orchestrator modes

The delegated model's output quality depends **only** on the model + effort chosen for it — never on your own model or effort. Your tokens buy nothing but the ferrying of text, so ferry as little as possible without corrupting the task.

- Never spawn a subagent just to run the Bash call. That pays a whole agent bootstrap for one command.
- For a standalone delegation request, relay the original report or exact requested
  output without silent correction.
- For orchestrated implementation, return compact evidence summaries and artifact
  paths to the planner. Preserve exact errors, explicit verbatim requests, and the
  original report as artifacts. Summaries must not change findings.
- Reverify only when the user requested it, the plan assigns verification, or required
  acceptance makes it part of the current role.

## 2. Lanes

Every engine exposes three lanes. Pick by what the task actually needs, not by what is convenient.

| Lane | When |
|---|---|
| **A — Investigate** | Read-only: diagnose, review, explain |
| **B — Edit** | File changes in the working directory; no network needed |
| **C — Full** | Needs localhost/network/dev server, installs, writes outside the CWD, or live self-verification |

The engine skill maps each lane to its own sandbox flags.

## 2b. Never delegate `git push` — the sandbox cannot reach the keychain

**Engine-agnostic. This is a property of the macOS sandbox, not of any one model or CLI, so it binds every present and future delegate: Codex, Grok, headless Claude, and anything added later.**

A sandboxed unit cannot read the login keychain, so `git-credential-osxkeychain` fails and an HTTPS push dies with:

```
failed to get: -50
fatal: could not read Username for 'https://github.com': terminal prompts disabled
```

**That is not a credential failure, and `gh auth status` reporting an invalid token from inside the sandbox is not evidence that the token is invalid.** Verified 2026-08-16: a unit reported exactly this, and the identical push from the session shell succeeded at once with no re-authentication.

The rule:
- **A delegate may `git add` and `git commit`.** Those touch only the working tree and `.git`.
- **The dispatcher pushes.** Never put `git push`, `gh pr create`, `gh release`, or any other
  network-authenticated git operation in a delegate's task, and never escalate to lane C to get
  around it — lane C is for browsers, installs, and writes outside the CWD, not for borrowing
  credentials.
- **If a delegate reports an auth failure on push, do not act on its diagnosis.** Do not run
  `gh auth login`, do not edit credential helpers, do not tell the user to re-authenticate. Confirm the commit, then push from the session shell.
- The same holds for any task needing a keychain-backed secret. Use the supported
  credential mechanism or keep the privileged operation with the dispatcher. Never
  place a secret in a model prompt.

Inside WarFleet this is a dispatcher duty: the release step never becomes a unit's task.

## 3. Session-scoped continuity

The registry lives in the scratchpad, which dies with the session, so continuity is fresh across
Claude sessions unless entries are carried over as imported entries (below).

- Maintain `<scratchpad>/external-threads.json`. Record every fresh run as `{"engine":"<codex|grok|claude>","id":"<thread id>","topic":"<one line>","task":"<ref>","lane":"A|B|C"}`.
- **Follow-ups may resume** when a later task in the same Claude session genuinely builds on an
  earlier one — references its output, same files or topic, or the user says "continue".
- **Relatedness rule:** unrelated tasks always start fresh. Resuming feeds the whole old thread back
  in (costlier per call) and pollutes context. Continuity is a tool, not a default.
- Parallel or independent tasks (e.g. one WarFleet wave) always run fresh — concurrent units cannot
  share a thread.
- **Imported entries:** when the handoff skill (pause or urgent mode) writes a registry entry
  `{"engine","id","task","lane","topic"}` into the owning doc (plan or explore Start here, roadmap
  In-flight handoff, or handoff file), the resuming session may import exactly those entries into
  its own `<scratchpad>/external-threads.json` and resume them for that same task only.
- Never adopt an engine plugin's own "resume candidate" — those are repo-scoped and bleed across
  Claude sessions. Only ids in this session's registry, recorded or imported, are resumable.

## 3b. Grok model resolution — the effort menu depends on the model

Owned by `references/engine-grok.md` (Invocation). In short: the effort menu is per model,
`~/.agents/skills/headless/data/grok-models.json` is the only effort table, discovery runs
`~/.agents/skills/headless/scripts/resolve-grok-model.sh` (read-only, never an authorization),
`grok_unknown=<id>` means ask the user and record it, and an alias such as `grok-build-latest` is
never passed — it is not launchable and defeats the hook's verbatim auth-file comparison.

## 3c. Words-as-ask — never re-ask what the user already stated

**A tier named in the request IS the answer to that question.** Do not re-ask it, do not "confirm" it
with a popup, and never treat a menu as more authoritative than the user's own words. If only one
half is named, ask for the missing half alone. If everything is named, ask nothing.

The bar is **extraction, not inference**. A stated tier counts (`codex, terra medium`;
`grok 4.6 xhigh`). An *implied* one does not — "use something cheap", "this one's hard, go big" are
hints about the task, not authorizations, and they get the normal question. When genuinely unsure
whether a phrase names a tier, ask: one question costs seconds, a wrong silent tier costs a run.

This applies to standalone `/headless` requests and to the WarFleet muster alike. In WarFleet it
does **not** weaken anything downstream: the compiler still validates the extracted answer, the plan
is still shown, and explicit approval is still required. Words-as-ask replaces *questions*, never
*approval*.

## 4. Building the prompt — lean but self-contained

- The user's task text goes in **verbatim**. Do not restate conversation history.
- Add only what the delegate cannot know: absolute working directory, specific file paths named
  earlier, and hard constraints (e.g. a repo's "no template brand names" grep rule when touching client sites).
- **Long or multi-line prompts go via file, not inline.** Write the spec to
  `<scratchpad>/<engine>-task-<slug>.md` and pass it by the engine's file flag or `"$(cat <file>)"`.
  This kills shell-escaping bugs on long specs. Short one-liners may stay inline.
- **Skill bridging:** delegates cannot resolve Claude slash commands. Replace `/impeccable` etc. with
  "Read and follow the instructions in `~/.agents/skills/<name>/SKILL.md`" (or `~/.claude/skills/<name>/` for Claude-only skills) — verify the path exists
  first; plugin skills live under `~/.claude/plugins/`. Forward the skill's *mode argument* (e.g.
  "live") as intent, with a note of what it means.
- **Browser and network routing** (dispatcher drives and the delegate judges, lane by capability,
  sandbox network differences, one browser at a time) lives in
  `~/.agents/skills/stance/references/capabilities.md` §1–§3. Engine facts that stay here: a
  standalone headless task with no orchestration around it may use the engine's own browser, in
  lane C only for Codex/Grok:

  | Engine | Own browser | Images at prompt time |
  |---|---|---|
  | Claude | `--chrome` → `mcp__claude-in-chrome__navigate` / `__computer` / `__read_page` | `Read` the file |
  | Codex | `chrome-devtools` MCP (29 tools) — **lane C only** | `-i/--image <FILE>...` |
  | Grok | `chrome-devtools` MCP, same server — **lane C only** | `--prompt-json` content blocks |

  `chrome-devtools-mcp` is configured globally in both `~/.codex/config.toml` and
  `~/.grok/config.toml`, so Codex and Grok units get it with no per-call flags. Codex additionally
  ships an app-owned `node_repl` browser backend, but that one requires the ChatGPT desktop app — see
  `references/engine-codex.md`.

- **Remote MCP connects asynchronously.** A delegate that needs a connector must reach it via
  `ToolSearch`, which waits for connecting servers. Never conclude a tool is missing from an early
  tool listing.
- **Make capability failures happen early:** open any network- or browser-dependent prompt with the
  smoke test in `~/.agents/skills/stance/references/capabilities.md` §4.
- End every prompt with:
  > Write your complete final report as your last message. Plain text, self-contained. End it with
  > exactly: `STATUS: done|blocked` / `FILES: …` / `BLOCKERS: …` / `NOTES: …`

## 5. The footer block

Every delegated unit ends its output with exactly this, and nothing after it:

```
STATUS: done | blocked
FILES: <files changed, or none>
BLOCKERS: <verbatim error + what you tried, or none>
NOTES: <one-line anything else the commander must know>
```

This is the only part of a delegate's output any orchestration layer parses. Forward footer blocks
up the chain, never whole transcripts.

## 5b. A refusal stops the action

Every delegated unit, on any engine or route:

- **A refusal** is a permission-prompt denial, an auto-mode classifier denial, or a hook block of an
  action the task intends (writes, deletes, launches, network, git). Stop that action, never retry
  it through another tool, and report the verbatim refusal in BLOCKERS. It is a stop, not a routing
  problem, even when its text suggests other tools. The dispatcher asks the owner.
- **A sandbox or tool limit of the assigned lane** (read-only filesystem, no temp files, no network
  in lane A) is not a refusal. Switch to a method that fits the lane (`diff -u`, `python3 -c`,
  reading files directly) and continue; mention it in NOTES only if it limited coverage.
- **Destructive steps approved in planning** (deleting files, dropping data) are dispatcher-owned
  and never part of a unit's task.

## 6. Wait and report progress

Use completion events and bounded host-native waits. While a delegate runs, do useful
independent work that stays inside the dispatcher's role. Read a stable progress log
or request a checkpoint only when output, a concrete blocker, or the user's question
warrants it. Quiet output is not proof of a stall and never justifies a duplicate run.

## 7. Preserve results

Standalone courier requests relay the delegate's result unedited. Orchestrated work
may use a compact faithful summary plus result paths. Always preserve exact errors,
explicit verbatim requests, and source reports. If the dispatcher disagrees, label
that observation separately; never silently rewrite a finding.

## 8. Cost model

- Claude spends tokens only on: the ask, one Bash call, reading the final message, relaying it.
- Codex bills to the ChatGPT account; Grok to the SuperGrok account; Claude to the Claude account.
  The split is per task, and the session's Claude model has **zero** effect on Codex or Grok output.
- Batch runs: resolve any script path glob **once** and reuse it for every call in the run; launch
  independent tasks as parallel background calls in one block, never sequentially.
