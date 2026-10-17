#!/usr/bin/env python3
"""Candidate commands are data; none is executed."""
import json
import subprocess
import unittest
from pathlib import Path

GUARD = Path(__file__).with_name("headless-launch-guard.py")


def allowed(command: str) -> bool:
    r = subprocess.run(["python3", str(GUARD)], input=json.dumps({"tool_input": {"command": command}}),
                       text=True, capture_output=True)
    assert r.returncode in (0, 2), r.stderr
    return r.returncode == 0


class Blocks(unittest.TestCase):
    def test_raw_launches(self):
        for c in [
            'codex exec "fixture"', "codex exec --model gpt-5.6-terra --effort high x",
            "codex resume abc", "codex review --uncommitted", 'codex "do it"', "codex",
            'grok -p "x"', "grok -m grok-4.7 --effort medium --single x",
            '/opt/homebrew/bin/grok --single "x"', 'claude -p "x"',
            "claude --model claude-opus-5-5 --print hi", "env A=1 codex exec x",
            "cd /tmp && codex exec x", 'echo "$(codex exec fixture)"', "echo `grok -p x`",
            'sh -c "codex exec fixture"', "bash -c 'claude -p hi'",
            'for x in 1; do codex exec "p"; done', "if true; then grok --single x; fi",
            "cat prompt | claude -p", "timeout 60 codex exec x", "nohup grok -p x &",
            "node /x/codex-companion.mjs task --fresh ok",
            "cat <<'EOF' | sh\ncodex exec x\nEOF",
            "codex exec --help && codex exec x", "codex exec -h fixture", "codex exec 2>&1",
        ]:
            with self.subTest(command=c):
                self.assertFalse(allowed(c))


class Allows(unittest.TestCase):
    def test_wrappers_management_and_data(self):
        for c in [
            "~/.agents/skills/headless/scripts/run-codex.sh --cwd . --model gpt-5.6-terra --effort high --lane A --prompt x",
            "sh ~/.agents/skills/headless/scripts/run-grok.sh --model grok-4.7 --effort medium --lane A --prompt x",
            "cat t.md | ~/.agents/skills/headless/scripts/run-claude.sh --cwd . --model claude-sonnet-5 --effort high --speed standard --lane A",
            "codex debug models --bundled", "codex --version", "codex login status", "grok models",
            "grok --help", "claude --version", "claude mcp list", "claude plugin list",
            'rg "codex exec|spawn" file', 'grep -n "claude -p" notes.md', "echo 'grok -p x'",
            "for f in ~/.claude/skills/*; do wc -l \"$f\"; done", "echo $HOME/.claude",
            "diff <(cat ~/.codex/AGENTS.md) x", "ls ~/.grok/skills",
            "python3 - <<'PY'\nimport subprocess\nprint('codex exec x', \"grok -p\")\nPY",
            "cat > notes.md <<EOF\nrun: claude -p hi\nEOF",
            "grep -rn run-grok.sh ~/.agents/skills",
            "codex exec --help", "codex exec -h", "codex exec --help 2>&1 | head -3", "grok sessions --help >/dev/null", "codex resume --help", "claude -p --help",
        ]:
            with self.subTest(command=c):
                self.assertTrue(allowed(c))


class StdoutDecision(unittest.TestCase):
    def test_patch_payload_is_data_but_shell_substitution_is_not(self):
        patch = "*** Begin Patch\n*** Add File: plan.md\n+Use `codex` here.\n*** End Patch"
        for tool in ("apply_patch", "functions.apply_patch"):
            with self.subTest(tool=tool):
                result = subprocess.run(
                    ["python3", str(GUARD)], text=True, capture_output=True,
                    input=json.dumps({"tool_name": tool, "tool_input": {"command": patch}}))
                self.assertEqual(result.returncode, 0, result.stderr)
        for tool in ("Bash", "exec_command", "functions.exec_command"):
            with self.subTest(tool=tool):
                result = subprocess.run(
                    ["python3", str(GUARD)], text=True, capture_output=True,
                    input=json.dumps({"tool_name": tool, "tool_input": {
                        "command": 'echo "*** Begin Patch `codex` *** End Patch"'}}))
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_block_also_emits_stdout_json_for_hermes(self):
        r = subprocess.run(["python3", str(GUARD)], text=True, capture_output=True,
                           input=json.dumps({"tool_input": {"command": "codex exec x"}}))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stdout)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
