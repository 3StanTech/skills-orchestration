"""Offline launch contract tests. The real Grok binary is never invoked."""
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WRAPPER = Path(__file__).resolve().parents[1] / 'scripts/run-grok.sh'

class LaunchContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / 'calls.jsonl'
        stub = self.root / 'grok'
        stub.write_text(f'#!{sys.executable}\n' + '''import json, os, sys
with open(os.environ['TEST_CALL_LOG'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
if os.environ.get('TEST_POST_WORK'):
    open(os.environ['TEST_CALL_LOG'] + '.work', 'w').write('work completed')
    print('Task work was performed. A later test failed to initialize sandbox.')
    sys.exit(42)
if os.environ.get('TEST_FAILURE'):
    print('ordinary task failure; sandbox settings were inspected')
    sys.exit(7)
print('done')
''')
        stub.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'], TEST_CALL_LOG=str(self.log))
        self.base = ['--cwd', str(self.root), '--lane', 'A']
        self.tier = ['--model', 'grok-4.6', '--effort', 'high']

    def run_wrapper(self, args):
        return subprocess.run([str(WRAPPER), *self.base, *args], env=self.env, capture_output=True, text=True)

    def assert_rejected_without_launch(self, args):
        result = self.run_wrapper(args)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists(), 'A rejected request invoked Grok')

    def test_missing_model(self):
        self.assert_rejected_without_launch(['--effort', 'high', '--prompt', 'test'])

    def test_missing_effort(self):
        self.assert_rejected_without_launch(['--model', 'grok-4.6', '--prompt', 'test'])

    def test_flag_words_in_prompt_do_not_supply_tier(self):
        self.assert_rejected_without_launch(['--prompt', 'Explain --model grok-4.6 --effort high'])

    def test_every_pair_of_prompt_sources_is_rejected(self):
        sources = [['--prompt', 'text'], ['--prompt-file', str(self.root / 'p')], ['--prompt-json', '[]']]
        for left, right in itertools.combinations(sources, 2):
            with self.subTest(left=left[0], right=right[0]):
                self.assert_rejected_without_launch(self.tier + left + right)

    def test_duplicate_or_empty_prompt_is_rejected(self):
        for prompts in [['--prompt', 'one', '--prompt', 'two'], ['--prompt', ''], []]:
            with self.subTest(prompts=prompts):
                self.assert_rejected_without_launch(self.tier + prompts)

    def test_unknown_model_and_unsupported_effort(self):
        for tier in [['--model', 'grok-build-latest', '--effort', 'high'], ['--model', 'grok-4.5', '--effort', 'xhigh']]:
            with self.subTest(tier=tier):
                self.assert_rejected_without_launch(tier + ['--prompt', 'test'])

    def test_valid_selection_is_forwarded_without_catalog_probe(self):
        result = self.run_wrapper(self.tier + ['--resume', 'same-session', '--prompt', 'literal --model text'])
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(x) for x in self.log.read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        args = calls[0]
        self.assertEqual(args[args.index('-m') + 1], 'grok-4.6')
        self.assertEqual(args[args.index('--effort') + 1], 'high')
        self.assertEqual(args[args.index('--resume') + 1], 'same-session')
        self.assertEqual(args[args.index('--single') + 1], 'literal --model text')
        self.assertIn('--no-memory', args)

    def test_ordinary_failure_does_not_retry(self):
        self.env['TEST_FAILURE'] = '1'
        result = self.run_wrapper(self.tier + ['--prompt', 'test'])
        self.assertEqual(result.returncode, 7)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)
        self.assertNotIn('RETRY:', result.stderr)

    def test_post_work_sandbox_error_never_replays(self):
        self.env['TEST_POST_WORK'] = '1'
        result = self.run_wrapper(self.tier + ['--resume', 'same-session', '--prompt', 'test'])
        self.assertEqual(result.returncode, 42)
        self.assertEqual(len(self.log.read_text().splitlines()), 1)
        self.assertTrue(Path(str(self.log) + '.work').exists())
        self.assertIn('A later test failed to initialize sandbox', result.stdout)
        self.assertNotIn('RETRY:', result.stderr)

    def test_invalid_prompt_file_json_and_duplicate_identity(self):
        empty=self.root/'empty';empty.write_text('')
        for extra in [['--prompt-file',str(empty)],['--prompt-file',str(self.root/'missing')],
                      ['--prompt-json','[]'],['--prompt-json','not json'],['--prompt',' '],
                      ['--model','grok-4.5','--prompt','task']]:
            with self.subTest(extra=extra):self.assert_rejected_without_launch(self.tier+extra)

    def test_help_is_read_only(self):
        self.assertEqual(self.run_wrapper(['--help']).returncode, 0)
        self.assertFalse(self.log.exists())

if __name__ == '__main__':
    unittest.main()
