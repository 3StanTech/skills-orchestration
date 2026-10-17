# Capability routing — which lane, family and owner a task actually needs

The single home for capability routing. `stance`, `create-plan`, `implement`, `headless` and
`warfleet` point here instead of restating it. Engine flags and quirks stay in
`~/.agents/skills/headless/references/engine-*.md`; the shared delegation contract stays in
`headless/references/contract.md`. Every rule below came from a real run that failed without it.

## 1. Lane by capability

| Task needs | Minimum lane | Evidence |
|---|---|---|
| Read files, grep, reason | A (read-only) | — |
| Edit files in the repo | B (workspace) | — |
| **Outbound network on Codex** (curl a live URL, fetch a deployed site) | **C** | Codex A/B have no network, not even DNS: a real unit got `curl: (6) Could not resolve host` on every request and closed blocked |
| **Outbound network on Grok** | **A or B** | Grok's network block is seccomp-based, so Linux-only; on macOS a real Grok unit at read-only curled live sites. Lane C surrenders the sandbox for nothing |
| Outbound network on headless Claude | A or B | Claude permission modes are not an OS sandbox |
| Write outside the working directory, `/tmp`, installs | **C** | a real unit hit `couldn't create cache file '/tmp/…' (Operation not permitted)` on a read-only `git status` |
| **Any browser** (screenshots, DOM, a11y, visual checks) | **the dispatcher** | see §3 |

## 2. Family by task shape

Codex and Grok enforce containment in the macOS kernel (Seatbelt), irreversibly, for every child
process. Claude enforces nothing at that level. Use that in both directions.

| Task shape | First choice | Because |
|---|---|---|
| Bulk read / analyse / edit, many parallel units | Codex or Grok, lane A/B | the kernel sandbox is a guarantee, not a restriction |
| Fetch a live URL, no browser | Grok lane A/B (while active); else Codex lane C or headless Claude A/B; else the dispatcher | Grok keeps network *and* the sandbox |
| Anything with a browser | the dispatcher | §3 |
| Dev server, installs, writes outside the working directory | the dispatcher, or Codex/Grok lane C | subprocess-heavy work fights the sandbox |
| Review of another family's work | a different family when available; any family if the owner names it | §5 |

**Sandbox-as-guarantee.** A read-only run (audit, review, research) on Codex/Grok lane A
*mechanically cannot* mutate the repo even if a unit misreads its brief — a stronger promise than
any instruction to a Claude unit. A real audit run used this and ended with a verifiably clean
`git status`. When a run is read-only, say so in the plan and name the sandbox as the enforcement.

**Lane C for browser work is the worst of both:** it gives up the containment that was the reason
to pick Codex/Grok and still yields a worse browser than the dispatcher's.

## 3. Browser work: the dispatcher drives, a helper judges

No helper is ever assigned a browser. A browser cannot start inside a sandbox: `chrome-devtools`
MCP is configured for Codex and Grok, but in lanes A/B the process dies on spawn. A real Grok unit
reported Playwright, Chrome for Testing, headless_shell and system Chrome all `SIGSEGV` with
Crashpad "Operation not permitted" and lost 46 checks.

| Step | Who | What |
|---|---|---|
| Capture | the dispatcher (the session) | navigate, resize per breakpoint, screenshot, read page/console/network, measure hard numbers with JavaScript; write artifacts to disk |
| Assess | the assigned helper | reads the artifacts: Claude `Read`s PNGs, Codex `-i/--image`, Grok `--prompt-json` image blocks |

- The dispatcher may finish a browser task alone only when every acceptance criterion is objective
  ("zero console errors", "no horizontal overflow at 320px", "tap targets ≥44×44"). Taste goes to a
  helper with the artifacts.
- Never report a visual check as passing from a screenshot you did not measure.
- Serialize browser-driving work; other non-browser tasks may run in parallel.

## 4. Smoke tests and fallbacks — fail in the first thirty seconds

A helper whose tooling cannot work must find out before doing the work. In a real run a unit
completed a whole HTTP-layer audit and only then reported the browser had never worked: 46 checks
lost, a remediation round burned, no chance to reassign inside the wave.

- **Smoke test.** Any task needing network (or another ⚠️ capability) opens its packet with one
  probe, e.g. `curl -sS -o /dev/null -w '%{http_code}' <one target URL>`. On failure the helper
  stops with `STATUS: blocked` and `NOTES: capability probe failed at start — no task work
  attempted.` — never a degraded version of the task.
- **Fallback.** The same task names a pre-approved fallback tier/route (routing-table row or plan
  roster). A capability failure launches the fallback immediately, with no question and no repair
  round. Browser tasks need no fallback: the dispatcher's pane has nothing to fall back from.
- A capability failure is **not** a quality failure: it never counts toward the escalation ladder
  (`routing.md` §4).

## 5. Review family

Cross-family review is not required. A different family is the better pick when one is available
(evidence below); when it is not, the owner may name a same-family auditor. A launch failure still
never switches family on its own. In a real run a Grok builder and a GPT verifier were paired on one target; the GPT verifier
found a form-escape bug and several severity-1 blockers the Grok unit missed. Same-family
redundancy would likely have missed them twice. A GPT reviewer at lane A adds the sandbox
guarantee (§2). Verifiers may run one tier below the builder unless the risk justifies parity.

## 6. Probe before asserting incapacity

Before telling the owner a family "can't" do something, run the read-only probe in
`headless/references/contract.md` §0b (help output, skills, MCP config). Configured is not usable:
confirm a capability works **in the lane you plan to use**. Settled results go in that engine's
confirmed-capability table, not into a prompt.

## 7. Host notes

| Host | `native` helper route | Launch guard | Notes |
|---|---|---|---|
| Claude Code | subagent tool with alias + effort (`routing.md`) | `~/.claude/settings.json` PreToolUse | browser pane is the dispatcher's |
| Codex | native agents for GPT rows only | `~/.codex/hooks.json` PreToolUse | lanes A/B have no network |
| Grok | native subagents for Grok rows only | `~/.grok/hooks/headless-launch-guard.json` | family inactive while there is no subscription |
| Hermes | none, headless wrappers only | `~/.hermes/config.yaml` `hooks.pre_tool_call` (matcher `terminal`); needs the owner's one-time allowlist consent | create-plan guard not registered (no prompt-submit equivalent) |
| Pi / other | none, headless wrappers only | none known; wrappers still refuse missing tiers and unapproved lane C | verify Pi's skill folder when installed (re-run each bundle's `install.sh`) |
