
# Engine: Codex (headless GPT)

Read `~/.agents/skills/headless/references/contract.md` for authorization, continuity and output
handling. For implementation, also read `~/.agents/skills/stance/SKILL.md`.
The named implementer owns ordinary repairs; browser work stays with the dispatcher.

## Identity and current capabilities

Require the user's explicit model and effort together, or the exact approved
roster identity for this task. Ask only for missing values. Never reuse an unrelated
task's selection or silently inherit config defaults. Use full concrete model IDs.

Discover supported identities with `codex debug models --bundled`; the wrapper
validates the exact pair against that installed catalog. Do not maintain another
effort table here. Local policy excludes models below GPT-5.5 and routing aliases.
The menu normally offers supported `low`, `medium`, `high`, `xhigh` choices. Preserve
the user's existing menu preference: do not offer `max`/`ultra` as unsolicited
escalations, but honor them when explicitly named and supported. Never offer an
unsupported effort. No recommended or preselected tier.

Honor an explicit standard/fast choice. If speed was not requested, the wrapper
pins `standard` (`service_tier=default`); fast explicitly pins `priority`. Do not
promise a fixed speedup. A paid-tier change requires its separate authorization.

Read-only help/catalog/status checks start no model. Use `scripts/check-codex.sh`
for local discovery.


### Confirmed capabilities — verified on this machine

Add a row when a probe settles something; correct it when reality changes (probe rules:
`~/.agents/skills/headless/references/contract.md` §0b).

| Capability | Status | How it is reached |
|---|---|---|
| Image generation | ⚠️ likely, unverified headless | `~/.codex/generated_images/` holds prior output, so some Codex surface has it. **Not confirmed under headless `codex exec`** — probe before relying on it. |
| `--output-schema <FILE>` on `codex exec` | ✅ confirmed | Constrains the final message to a JSON Schema (Grok's equivalent is `--json-schema`). Direct path only. |
| `codex exec review` | ✅ confirmed | Review subcommand with `--uncommitted` / `--base <branch>` / `--commit <sha>`; narrower flags than `codex exec` — no `-C`, `--sandbox`, `-p`, or `-i`. |

## Launch

```sh
~/.agents/skills/headless/scripts/run-codex.sh \
  --cwd "<workdir>" --model <concrete-id> --effort <level> --lane <A|B|C> \
  --speed standard --prompt-file "<scratchpad>/task.md" \
  --out "<scratchpad>/last.md"
```

The wrapper uses **direct Codex CLI for every lane** so both standard and fast are
explicit. Companion task launches cannot pin the same service-tier contract and
are not its execution path. `--force-direct` remains a compatibility no-op.

| Lane | Pinned configuration |
|---|---|
| A | `read-only` |
| B | `workspace-write` |
| C | `danger-full-access`, requires `--approve-lane-c yes` |

Fresh runs use `--sandbox`; resume and review use `-c sandbox_mode=...` because
those subcommands accept narrower flags. Global settings must not replace the
selected lane. Lane names alone do not prove actual runtime containment or network
access: verify the current host and route. Never escalate a lane to borrow credentials.
Commits, pushes and deployment still require explicit authorization.

Use `--resume <recorded-id>` for the same task; never adopt a repository-scoped
resume candidate. Use `--review-uncommitted`, `--review-base <ref>` or
`--review-commit <sha>` for review. Check `--help` for prompt, image, schema and
other supported options. A dry-run prints the proposed command without launching.
The wrapper disables the configured `node_repl` server for headless runs.

## Results and continuity

Run with the host's supported background execution and bounded wait tools.
Record the returned session ID and stable log/output paths. Preserve exact errors;
a launch failure does not authorize local takeover or a different model.

Read the final result at the requested `--out` path. When omitted, the wrapper
creates a unique output directory under the system temporary directory and prints
`codex_output=...`. Store persistent handoffs outside repositories. For standalone
courier requests retain the core's verbatim contract; orchestrated work may return
its compact findings and acceptance status with the original artifact available.

WarFleet invocations carry `# warfleet-task:<id>`. The hook checks the parsed
model/effort against the session's approved auth record. Never remove tags, alter
auth records or bypass hooks to get around rejection. Shell-hook enforcement is
route-specific and cannot enforce ownership on every native edit tool.

## Verification

Run `sh tests/test-run-codex.sh` and the Python tests under `tests` after changing
the wrapper. Tests must use dry-runs or stub executables, not paid provider launches.
