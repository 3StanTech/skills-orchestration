"""Catalog-driven tier validation and the WarFleet roster check, via dry-runs only."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CLAUDE = SCRIPTS / "run-claude.sh"
GROK = SCRIPTS / "run-grok.sh"


def run_claude(*args, prompt="task"):
    with tempfile.TemporaryDirectory() as cwd:
        return subprocess.run(["sh", str(CLAUDE), "--cwd", cwd, "--lane", "A", "--dry-run", *args],
                              input=prompt, text=True, capture_output=True)


class ClaudeCatalogTests(unittest.TestCase):
    def test_recorded_model_and_effort_pass(self):
        r = run_claude("--model", "claude-opus-5-5", "--effort", "medium", "--speed", "standard")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('{"fastMode":false}', r.stdout)

    def test_fast_on_supported_opus(self):
        r = run_claude("--model", "claude-opus-5-5", "--effort", "high", "--speed", "fast")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('{"fastMode":true}', r.stdout)

    def test_fast_refused_where_unsupported(self):
        r = run_claude("--model", "claude-sonnet-5", "--effort", "high", "--speed", "fast")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not supported", r.stderr)

    def test_unrecorded_model_says_record_it(self):
        r = run_claude("--model", "claude-opus-9", "--effort", "high", "--speed", "standard")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not recorded", r.stderr)

    def test_unrecorded_effort_is_refused(self):
        r = run_claude("--model", "claude-sonnet-5", "--effort", "ultra", "--speed", "standard")
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not accept effort", r.stderr)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.auth = Path(self._tmp.name) / "auth.json"
        self.auth.write_text(json.dumps({"session_id": "s", "approved": [
            {"task": "t1", "model": "claude-opus-5-5", "effort": "medium", "speed": "standard"},
            {"task": "g1", "model": "grok-4.7", "effort": "medium"}]}))

    def tearDown(self):
        self._tmp.cleanup()

    def test_matching_launch_passes(self):
        r = run_claude("--model", "claude-opus-5-5", "--effort", "medium", "--speed", "standard",
                       "--auth", str(self.auth), "--task-id", "t1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_tier_mismatch_is_blocked(self):
        r = run_claude("--model", "claude-opus-5-5", "--effort", "high", "--speed", "standard",
                       "--auth", str(self.auth), "--task-id", "t1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("effort mismatch", r.stderr)

    def test_unapproved_task_is_blocked(self):
        r = run_claude("--model", "claude-opus-5-5", "--effort", "medium", "--speed", "standard",
                       "--auth", str(self.auth), "--task-id", "ghost")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not in the approved roster", r.stderr)

    def test_auth_needs_task_id(self):
        r = run_claude("--model", "claude-opus-5-5", "--effort", "medium", "--speed", "standard",
                       "--auth", str(self.auth))
        self.assertEqual(r.returncode, 2)
        self.assertIn("go together", r.stderr)

    def test_grok_wrapper_uses_the_same_check(self):
        with tempfile.TemporaryDirectory() as cwd:
            ok = subprocess.run(["sh", str(GROK), "--cwd", cwd, "--lane", "A", "--model", "grok-4.7",
                                 "--effort", "medium", "--prompt", "x", "--dry-run",
                                 "--auth", str(self.auth), "--task-id", "g1"], text=True, capture_output=True)
            bad = subprocess.run(["sh", str(GROK), "--cwd", cwd, "--lane", "A", "--model", "grok-4.7",
                                  "--effort", "medium", "--prompt", "x", "--dry-run",
                                  "--auth", str(self.auth), "--task-id", "t1"], text=True, capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
