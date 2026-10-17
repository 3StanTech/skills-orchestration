"""Offline argument verification with a stub Codex executable."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WRAPPER=Path(__file__).resolve().parents[1]/'scripts/run-codex.sh'
class CodexLaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.log=self.root/'calls.jsonl'
        stub=self.root/'codex'
        stub.write_text(f'#!{sys.executable}\n'+'''import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
if sys.argv[1:]==['debug','models','--bundled']:
    print(json.dumps({'models':[{'slug':'gpt-6-astra','supported_reasoning_levels':[{'effort':'high'}]}]}))
else:
    sys.exit(int(os.environ.get('STUB_EXIT','0')))
''');stub.chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.root)+os.pathsep+os.environ['PATH'],CALL_LOG=str(self.log),TMPDIR=str(self.root))
    def run_wrapper(self,args):
        return subprocess.run([str(WRAPPER),'--cwd',str(self.root),'--model','gpt-6-astra','--effort','high',*args],env=self.env,capture_output=True,text=True)
    def calls(self):return [json.loads(x) for x in self.log.read_text().splitlines()]
    def test_all_entry_paths_pin_lane_and_speed(self):
        for mode in ['fresh','resume','review']:
            for lane,sandbox in [('A','read-only'),('B','workspace-write'),('C','danger-full-access')]:
                for speed,tier in [('standard','default'),('fast','priority')]:
                    with self.subTest(mode=mode,lane=lane,speed=speed):
                        extra=['--lane',lane,'--speed',speed]
                        if lane=='C':extra+=['--approve-lane-c','yes']
                        extra+=['--review-uncommitted'] if mode=='review' else ['--prompt','task']
                        if mode=='resume':extra+=['--resume','recorded-id']
                        r=self.run_wrapper(extra);self.assertEqual(r.returncode,0,r.stderr)
                        argv=self.calls()[-1]
                        if mode=='fresh':self.assertEqual(argv[argv.index('--sandbox')+1],sandbox)
                        else:self.assertIn('sandbox_mode='+sandbox,argv)
                        self.assertIn('service_tier='+tier,argv)
                        self.assertEqual(argv[argv.index('-m')+1],'gpt-6-astra')
                        self.assertIn('model_reasoning_effort=high',argv)
                        self.assertFalse((self.root/'codex-last.md').exists())
                        self.assertIn('/headless-codex-output.',argv[argv.index('-o')+1])
    def test_one_catalog_query_and_no_launch_on_dry_run(self):
        r=self.run_wrapper(['--lane','A','--review-uncommitted','--dry-run'])
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.calls(),[['debug','models','--bundled']])
        self.assertIn('sandbox_mode=read-only',r.stdout)
    def test_lane_c_requires_approval(self):
        r=self.run_wrapper(['--lane','C','--review-uncommitted'])
        self.assertEqual(r.returncode,2)
        self.assertTrue(all(x[0]=='debug' for x in self.calls()))
    def test_invalid_inputs_never_launch(self):
        prompt=self.root/'empty';prompt.write_text('')
        cases=[['--lane','A','--prompt',' '],
               ['--lane','A','--prompt-file',str(prompt)],
               ['--lane','A','--prompt','task','--prompt','other'],
               ['--lane','A','--review-uncommitted','--review-base','main'],
               ['--lane','A','--review-uncommitted','--resume','id'],
               ['--lane','A','--review-uncommitted','--profile','name'],
               ['--lane','A','--resume','id','--prompt','task','--add-dir','/tmp'],
               ['--lane','A','--review-uncommitted','--image','file'],
               ['--lane','A','--prompt']]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(self.run_wrapper(case).returncode,2)
                if self.log.exists():self.assertTrue(all(x[0]=='debug' for x in self.calls()))

    def test_provider_exit_preserved(self):
        self.env['STUB_EXIT']='19'
        self.assertEqual(self.run_wrapper(['--lane','A','--prompt','task']).returncode,19)
if __name__=='__main__':unittest.main()
