# skills-orchestration

How implementation work is split, staffed and verified across agents: stances and helper tiers, headless Claude/Codex/Grok workers, and the WarFleet multi-model workflow. Works with Claude Code, Codex and Grok through the shared `~/.agents/skills` folder.

## Contents

| Skill | Role |
| ----- | ---- |
| `stance` | Supersoldiers / vibin / chillin stances, tier resolution, context packets, verification and outcome logging |
| `headless` | Launch a separate Claude Code, Codex or Grok worker with explicit model, effort, speed and lane, and relay its report |
| `warfleet` | Hierarchical multi-model execution: Admiral plans, General gates waves, Infantry executes |

The `hooks/` folder holds the headless launch guard and its test.

## Setup

### 1. Prerequisites

- Python 3 and git.
- The engine CLIs you will delegate to: `claude` (Claude Code), `codex` (Codex), `grok`. Each wrapper checks for its own; you only need the families you use.
- Optional: [`skills-workcycle`](https://github.com/3StanTech/skills-workcycle) for the explore → plan → implement → audit cycle these skills staff.

### 2. Install

```sh
git clone https://github.com/3StanTech/skills-orchestration.git ~/.agents/bundles/skills-orchestration
~/.agents/bundles/skills-orchestration/install.sh
~/.agents/bundles/skills-orchestration/install.sh --check
```

`install.sh` symlinks each skill into `~/.agents/skills` (read natively by Codex and Grok) and into the skills folder of every installed host (`~/.claude/skills` for Claude Code, `~/.hermes/skills`, `~/.pi/agent/skills`; created when the host is installed but has no skills folder yet). The hook goes to `~/.agents/hooks`. It also creates your routing table, `skills/stance/data/routing.json`, from the empty `routing.example.json` (only if you have none). It never replaces a real file or a link pointing elsewhere (reported as `conflict`); `--check` changes nothing and exits 1 on any finding. Re-run it after installing a new host. To update later: `git -C ~/.agents/bundles/skills-orchestration pull` (your `routing.json` is untracked, so it never conflicts).

### 3. Register the hook

The headless launch guard makes every Claude/Codex/Grok worker launch go through the wrappers with an explicit model and effort. Claude Code, in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "\"$HOME/.agents/hooks/headless-launch-guard.sh\"", "timeout": 10 }] }
    ]
  }
}
```

Merge it into any hooks you already have. Codex (`~/.codex/hooks.json`) and Grok (`~/.grok/hooks/headless-launch-guard.json`) take the same shape; use the absolute path to your home folder there, in quotes if it contains a space.

| Event | Claude Code | Codex | Grok | Script |
| ----- | ----------- | ----- | ---- | ------ |
| `PreToolUse` | `Bash` | no matcher | `Bash\|run_terminal_command` | `~/.agents/hooks/headless-launch-guard.sh` |

### 4. Model routing (optional — you can skip this)

**You don't need to fill in the routing table.** It is only a fallback: a model, effort or stance you name yourself (`implement using <model-id> <effort> <chillin|vibin|supersoldiers>`, or a plan's roster) always wins. When neither you nor the table names a tier, the agent simply asks you. Stance is not in the table: unnamed means Vibin. The auditor that reviews finished work is always named or confirmed by you; the table's `review` row is only the suggested default.

`install.sh` created `skills/stance/data/routing.json` with every tier empty. Leave it that way to be asked each time, or fill a row once you notice you always give the same answer (schema: `skills/stance/references/routing.md`; model IDs: `skills/headless/data/*.json` and `codex debug models --bundled`). Check it with `python3 ~/.agents/skills/stance/scripts/route.py validate`.

The stances: **chillin** — your session works alone; **vibin** — up to 3 helpers for independent tasks; **supersoldiers** — one helper per independent task.

### 5. Your policy file

The skills defer to `~/AGENTS.md` for your personal rules. `skills-workcycle` ships an `AGENTS.example.md` to start from; without the file the skills still run.

### 6. Verify

```sh
~/.agents/bundles/skills-orchestration/install.sh --check
cd ~/.agents/bundles/skills-orchestration
for s in warfleet stance headless; do python3 -m unittest discover -s skills/$s/tests; done
python3 -m unittest discover -s hooks -p 'test_*.py'
```

The same suites run on GitHub Actions for every push and pull request to `main` (`.github/workflows/test.yml`).

### 7. Uninstall

Remove the hook entry from each host config, then every link that resolves into the bundle (including relative host links), then the clone:

```sh
python3 - <<'PY'
import glob, os
bundle = os.path.realpath(os.path.expanduser("~/.agents/bundles/skills-orchestration")) + os.sep
dirs = ["~/.agents/skills", "~/.agents/hooks", "~/.claude/skills", "~/.hermes/skills", "~/.pi/agent/skills"]
links = [p for d in dirs for p in glob.glob(os.path.join(os.path.expanduser(d), "*"))
         if os.path.islink(p) and os.path.realpath(p).startswith(bundle)]
for p in links:
    os.remove(p)
print(f"removed {len(links)} links")
PY
rm -rf ~/.agents/bundles/skills-orchestration
```

## Dependencies

- Python 3 and git.
- The engine CLIs you route to (`claude`, `codex`, `grok`); each wrapper checks for its own.
- Independent of `skills-workcycle`, which uses it optionally. Without it (no `~/.agents/skills/work-audit`), the final review is a read-only review of the run's diff by the reviewer tier, using the lenses Correctness, Ripple and Cleanup, with findings back to the named implementer.

## Not in this repo

Secrets, the routing outcome log (`~/.agents/state/outcomes.jsonl`), your routing table `skills/stance/data/routing.json` (untracked; made from `routing.example.json`), and your policy file `~/AGENTS.md`.

## License

MIT. See `LICENSE`.
