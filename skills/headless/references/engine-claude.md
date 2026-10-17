
# Engine: Claude (headless Claude Code)

Use Claude through Claude Code's normal CLI. Preserve project context, Claude skills, plugins, connectors, Chrome support, hooks, and session persistence. For standalone requests, build the narrowest safe invocation and relay the final report verbatim. For orchestration and implementation, read `~/.agents/skills/headless/references/contract.md` and `~/.agents/skills/stance/SKILL.md` for compact output, stance and ownership rules.

## Invocation

```sh
~/.agents/skills/headless/scripts/run-claude.sh --cwd "<workdir>" --lane <A|B|C> \
  --model <full-id> --effort <level> --speed <standard|fast> --prompt-file "<scratchpad>/task.md"
```

Require model, effort, and speed on every paid call. Never select or inherit them. A clicked WarFleet muster or approved roster is explicit. `~/.agents/skills/headless/data/claude-models.json` is the only authority on which models, efforts and fast mode the wrapper accepts; an unrecorded model is recorded at plan time after asking the user, never by editing the wrapper.

Fast mode applies per session with `--settings '{"fastMode":true}'`; the wrapper passes `false` for standard so a global preference cannot leak into the run. It preserves model quality while increasing speed and billed usage, and is offered only where the catalog records `fast: true`.

Use normal session persistence. Start a fresh session for unrelated work and resume only a session created for the current task. Do not impose a budget or turn cap unless the user requests one.

## Permission lanes

- A — read, investigate, review, or explain: --permission-mode plan plus denied edit tools.
- B — edit inside the current workspace: --permission-mode acceptEdits.
- C — browser use, installs, or writes outside the workspace: --permission-mode bypassPermissions, only after explicit approval.

Lane C is gated by scripts/run-claude.sh --approve-lane-c yes. Browser work belongs to the dispatcher. The legacy --chrome flag remains available but does not override that ownership rule. Claude permission modes are not an OS sandbox; verify the outer host containment rather than assuming it from a lane name.

Always pass --exclude-dynamic-system-prompt-sections. Send the task through standard input so variadic flags cannot consume prompt text. Do not override the system prompt.

## Prompt and output contract

For long tasks, place the complete prompt in a unique scratchpad file and pass it through stdin. The prompt must include the absolute working directory and hard constraints. End every prompt with:

~~~text
Write the complete final report as your last message. End it with exactly:
STATUS: done | blocked
FILES: <files changed, or none>
BLOCKERS: <verbatim error and what you tried, or none>
NOTES: <one-line anything else the user should know>
~~~

For standalone courier requests, relay Claude's final report and footer verbatim. Orchestrated work may use the shared core's compact summary contract while preserving the original artifact. Never substitute another model or silently reduce capabilities. If Claude reports an authentication failure, show the exact error and ask the user to run claude auth login; never edit authentication files.

## Wrapper

Use scripts/run-claude.sh to make model, effort, speed, lane, session, Chrome, and prompt transport explicit and auditable. The wrapper uses claude -p as the only execution path.

### Offline launch validation

`run-claude.sh --dry-run` validates identity, speed, lane and nonempty prompt input,
then prints arguments without launching Claude or displaying private prompt text.
Use exactly one prompt file or stdin. With `--prompt-file`, stdin is never read, so an
open caller pipe cannot stall the launch (fixed 2026-10-06); still launch background
helpers with stdin closed. Lane B runs only the shell commands the project's
`.claude/settings.local.json` allows; brief helpers to run one command per call
(compound commands are refused). Duplicate options, empty input, missing
values and ambiguous input are rejected before launch. Stdin transport preserves
prompt bytes. Temporary prompt buffering stays outside the workspace and is removed
after the attempt. Normal attempts preserve the Claude exit status.
