
# Engine: Grok (headless Grok Build CLI)

Use Grok as Grok. Preserve its normal system prompt, skills, plugins, tools, connectors, image capabilities, and web access. Act as a courier: build the narrowest safe invocation, run it, and relay the final report verbatim.

## Invocation

Require an explicit model and effort on every run, exactly as for a GPT delegation — but never re-ask a tier the user already named in the request. The bar is extraction, not inference: a stated tier ("grok 4.6 xhigh") counts, an implied one ("keep it cheap") does not.

**The effort menu depends on the model.** `grok-4.6` accepts low, medium, high, xhigh; `grok-4.5` accepts low, medium, high and has **no xhigh**. This cannot be probed — the CLI declares its effort flag as free text and enumerates nothing — so an unsupported tier fails only after the call is billed. `grok-models.json` is the authority, and the launch wrapper enforces it.

The model is **selected explicitly, never defaulted or aliased**. Run `scripts/resolve-grok-model.sh` for discovery and pass the concrete id the user selected; build the model menu from `grok_available` and each effort menu from that model's `grok_efforts_` line. `grok-build-latest` is not a launchable id — the catalog lists only concrete ids, so passing the alias fails at launch, and an unresolved alias also defeats any verbatim authorization comparison. If the resolver reports `grok_unknown=<id>`, an uncharacterized model shipped: ask the user which efforts it accepts, add it to `grok-models.json`, then continue — never guess a tier. If resolution fails entirely, use the known set, say so in one line, and never drop Grok over it.

Use a fresh UUID for unrelated work. Resume only a session created for the current task. The wrapper injects `--no-memory`, including on resume; callers do not pass it. Do not disable subagents by default. In WarFleet, pass the Admiral-approved total descendant budget in the prompt; Grok may stop below it but must not exceed it.

## Lane selection

Choose the least-permissive lane that can complete the task:

- A — read, investigate, review, or explain: `--lane A` (the wrapper maps this to
  Grok's internal `--sandbox read-only`).
- B — edit files inside the current workspace: `--lane B` (internal
  `--sandbox workspace`).
- C — browser processes, installs, or writes outside the workspace: `--lane C`
  (internal `--sandbox off`).

`--lane A|B|C` is the only public lane interface. Never pass Grok's internal
`--sandbox` flag to `run-grok.sh`; it fails fast with an actionable error. The
wrapper also injects `--no-memory` and `--verbatim` for every launch, so callers
must never pass either flag.

Network access has been observed in A and B on this host; verify current route
capabilities when needed. Direct in-scope Lane C launches use the standing
non-GPT authorization with `--approve-lane-c yes` as a mechanical acknowledgment.
Separate publication, credentials and destructive-action gates remain in force.

The wrapper performs **one attempt**, preserves its exit status, and prints the
stable log path. The installed CLI has no verified, machine-readable pre-work
failure signal; arbitrary output, even an exact sandbox error, cannot prove that
no task work happened. Therefore automatic Lane C replay is disabled.

The standing authorization still covers one same-identity Lane C recovery **only
after independent evidence establishes a pre-work sandbox initialization failure**.
The dispatcher records that evidence and the attempt before retrying; preserve the
exact model, effort, prompt and task, and resume the recorded session if one exists.
If progress or session state is uncertain, report the failure and do not replay.
Do not invent a status marker or infer pre-work state from silence or error prose.

**Network is not the keychain.** A Grok unit can curl the world and still fail to `git push`, because the sandbox blocks `git-credential-osxkeychain` (`failed to get: -50`, then `could not read Username for 'https://github.com'`). **A Grok unit may commit; the dispatcher pushes.** Do not escalate to lane C for it and do not act on the unit's auth diagnosis. Full rule: `~/.agents/skills/headless/references/contract.md` §2b.

Run scripts/check-grok.sh --doctor when CLI or capability status is uncertain. A doctor result or a real launch is the authentication signal; the model-listing command is not an authentication check.

### Confirmed capabilities — verified on this machine

Add a row when a probe settles something; correct it when reality changes (probe rules: `~/.agents/skills/headless/references/contract.md` §0b).

| Capability | Status | How it is reached |
|---|---|---|
| **Image generation + editing** | ✅ confirmed 2026-07-30 in a real build | `image_gen` / `image_edit` tool calls, documented in the bundled skill `~/.grok/bundled/skills/imagine/SKILL.md`. Instruct the delegate to load that skill first. `image_gen` takes `prompt` + `aspect_ratio`; `image_edit` additionally takes `image` (path or data URI). Neither exposes `n`/`count` — one call per variation. |
| Video (`image_to_video`, `reference_to_video`) | ⚠️ unverified | Described in the same `imagine` skill, which itself warns the tools may not exist. Verify before promising it. |
| Network in every sandbox lane (macOS) | ✅ confirmed | Lane section above; keychain still blocked (push stays with the dispatcher). |
| `grok-build-latest` as a model id | ❌ not launchable | `grok models` lists only concrete ids; the string appears only as `fork_secondary_model = "grok-build"` in `~/.grok/config.toml`. Resolve, never alias. |
| Per-model effort sets | ✅ confirmed per model | Not probeable — the CLI enumerates nothing. Authority: `grok-models.json`. |

## Prompt and output contract

For long tasks, write the complete prompt to a unique scratchpad file and use
`--prompt-file`. For image inputs use `--prompt-json`; for exact structured output
use `--json-schema`. The wrapper supplies `--verbatim` for the supplied task.
Add `--max-turns` only when the approved task explicitly authorizes a turn cap.

The prompt must include the absolute working directory and any hard constraints Grok cannot discover. End every delegated prompt with:

~~~text
Write the complete final report as your last message. End it with exactly:
STATUS: done | blocked
FILES: <files changed, or none>
BLOCKERS: <verbatim error and what you tried, or none>
NOTES: <one-line anything else the user should know>
~~~

Relay Grok's final report and footer verbatim. Do not summarize, correct, substitute another model, or silently reduce capabilities. If Grok reports an authentication failure, show the exact error and ask the user to run grok login; never edit authentication files.

## Wrapper

Use `scripts/run-grok.sh --model <approved-id> --effort <approved-effort>` with an
explicit lane and exactly one prompt source. The wrapper rejects missing model,
missing effort, unsupported pairings, duplicate prompt flags, and multiple prompt
sources before launching Grok. `scripts/resolve-grok-model.sh` supplies discovery
information for a model menu; it never chooses the user's launch tier.

Run `sh tests/test-run-grok.sh` and `python3 -m unittest discover -s tests` after
changing the wrapper. Both use local stubs, not paid model runs.

## Standing authorization and approval boundaries

The commander has granted persistent authorization for in-scope non-GPT handoffs
and sharing the private task context needed to complete them, including edits
inside `.agents` and `.claude`. Do not show a second approval prompt at each
wave, task, retry, or private-context handoff once the run's scope and roster
are approved. Direct in-scope Lane C launches and the one evidence-backed Lane C recovery
described above are included in this standing authorization. Passing
`--approve-lane-c yes` records that existing directive; it is not a new approval
prompt.

This does not authorize a new task or model/effort choice, credentials or paid
tier changes, production or unrelated destructive actions, commits, pushes,
deployments, or final submissions. Stop at those boundaries and obtain the
separate approval before launching or performing the action.
