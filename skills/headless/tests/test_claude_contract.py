"""Offline Claude wrapper checks: the stub records arguments and exact stdin."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WRAPPER = Path(__file__).resolve().parents[1] / 'scripts/run-claude.sh'

class ClaudeLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / 'call.json'
        stub = self.root / 'claude'
        stub.write_text(f'#!{sys.executable}\n' + '''import json, os, sys
with open(os.environ['CALL_LOG'], 'w') as f:
    json.dump({'argv': sys.argv[1:], 'stdin': sys.stdin.read(), 'cwd': os.getcwd()}, f)
sys.exit(int(os.environ.get('STUB_EXIT', '0')))
''')
        stub.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'], CALL_LOG=str(self.log), TMPDIR=str(self.root))
        self.base = ['--cwd', str(self.root), '--model', 'claude-opus-5', '--effort', 'high', '--speed', 'standard', '--lane', 'A']

    def run_wrapper(self, extra=(), text='', base=None):
        return subprocess.run([str(WRAPPER), *(self.base if base is None else base), *extra],
                              input=text, env=self.env, text=True, capture_output=True)

    def rejected(self, extra=(), text='', base=None):
        result = self.run_wrapper(extra, text, base)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse(list(self.root.glob('headless-claude-prompt.*')))

    def test_empty_or_whitespace_input_never_launches(self):
        for text in ['', ' \n\t']:
            with self.subTest(text=text): self.rejected(text=text)

    def test_missing_and_flag_shaped_values(self):
        for option in ['--cwd', '--model', '--effort', '--speed', '--lane', '--session', '--resume', '--prompt-file']:
            for values in [[], ['--chrome']]:
                self.rejected(base=[option, *values])

    def test_duplicate_and_ambiguous_prompt(self):
        p = self.root / 'prompt'; p.write_text('task')
        self.rejected(['--prompt-file', str(p), '--prompt-file', str(p)])
        self.rejected(['--session', 'one', '--session-id', 'two'], text='task')
        self.rejected(['--session', 'one', '--resume', 'two'], text='task')
        # --prompt-file wins and stdin is never read (engine-claude.md, fixed 2026-10-06).
        self.assertEqual(self.run_wrapper(['--prompt-file', str(p)], text='other task').returncode, 0)

    def test_unreadable_and_empty_prompt_files(self):
        self.rejected(['--prompt-file', str(self.root/'missing')])
        p = self.root / 'empty'; p.write_text('')
        self.rejected(['--prompt-file', str(p)])

    def test_stdin_bytes_identity_and_lane_a(self):
        text = 'literal $HOME `nothing` --help\n\n'
        result = self.run_wrapper(text=text)
        self.assertEqual(result.returncode, 0, result.stderr)
        call = json.loads(self.log.read_text()); argv = call['argv']
        self.assertEqual(call['stdin'], text)
        self.assertEqual(Path(call['cwd']).resolve(), self.root.resolve())
        for flag, value in [('--model','claude-opus-5'),('--effort','high'),('--permission-mode','plan'),('--settings','{"fastMode":false}')]:
            self.assertEqual(argv[argv.index(flag)+1], value)
        self.assertIn('--disallowed-tools', argv)
        self.assertFalse(list(self.root.glob('headless-claude-prompt.*')))

    def test_prompt_file_and_resume(self):
        p = self.root / 'prompt'; p.write_text('task\n\n')
        result = self.run_wrapper(['--prompt-file', str(p), '--resume', 'recorded-id'])
        self.assertEqual(result.returncode, 0, result.stderr)
        call = json.loads(self.log.read_text())
        self.assertEqual(call['stdin'], 'task\n\n')
        self.assertEqual(call['argv'][call['argv'].index('--resume')+1], 'recorded-id')

    def test_dry_run_never_launches_or_exposes_prompt(self):
        result = self.run_wrapper(['--dry-run'], text='PRIVATE_PROMPT')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('PRIVATE_PROMPT', result.stdout)
        self.assertFalse(self.log.exists())

    def test_lanes_and_fast_mode(self):
        for lane, permission in [('B','acceptEdits'),('C','bypassPermissions')]:
            base = self.base.copy(); base[-1] = lane; base[base.index('--speed')+1]='fast'
            result = self.run_wrapper(['--approve-lane-c','yes'], 'task', base)
            self.assertEqual(result.returncode, 0, result.stderr)
            argv = json.loads(self.log.read_text())['argv']
            self.assertEqual(argv[argv.index('--permission-mode')+1], permission)
            self.assertEqual(argv[argv.index('--settings')+1], '{"fastMode":true}')
            self.assertEqual('--dangerously-skip-permissions' in argv, lane == 'C')

    def test_invalid_identity_speed_lane_and_unapproved_c(self):
        for flag, value in [('--model','opus'),('--effort','nope'),('--speed','turbo'),('--lane','D'),('--lane','C')]:
            base = self.base.copy(); base[base.index(flag)+1] = value
            self.rejected(base=base, text='task')
        base=self.base.copy();base[base.index('--model')+1]='claude-sonnet-5';base[base.index('--speed')+1]='fast'
        self.rejected(base=base, text='task')

    def test_provider_failure_preserves_exit_and_cleans_buffer(self):
        self.env['STUB_EXIT']='17'
        self.assertEqual(self.run_wrapper(text='task').returncode, 17)
        self.assertFalse(list(self.root.glob('headless-claude-prompt.*')))

if __name__ == '__main__': unittest.main()
