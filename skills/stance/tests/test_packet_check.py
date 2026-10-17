#!/usr/bin/env python3
"""Golden context packets: four launchable forms, and packets that must be rejected for specific reasons."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
CHECK = HERE.parent / "scripts" / "packet-check.py"
FIX = HERE / "fixtures"


class PacketCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name) / "repo"
        self.work.mkdir()
        for name in ("calc.py", "test_calc.py"):
            (self.work / name).write_text("")
        table = Path(self.tmp.name) / "routing.json"
        table.write_text(json.dumps({"task_types": {t: {} for t in
                                     ("plan", "mechanical", "standard", "hard", "review", "network")}}))
        self.env = dict(os.environ, ROUTE_TABLE=str(table))

    def tearDown(self):
        self.tmp.cleanup()

    def run_fixture(self, name, edit=lambda text: text):
        packet = Path(self.tmp.name) / name
        packet.write_text(edit((FIX / name).read_text().replace("{{WORKDIR}}", str(self.work))))
        return subprocess.run(["python3", str(CHECK), str(packet)], env=self.env, text=True, capture_output=True)

    def test_good_packet_passes(self):
        r = self.run_fixture("packet-good.md")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_annotated_owned_entries_pass(self):
        r = self.run_fixture("packet-annotated.md")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_deleted_owned_files_pass(self):
        r = self.run_fixture("packet-delete.md")  # one marked (delete), one asserted absent by `test ! -e`
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_read_only_review_passes(self):
        r = self.run_fixture("packet-review.md")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_read_only_form_needs_review_task_type(self):
        r = self.run_fixture("packet-review.md", lambda t: t.replace("**Task type:** review", "**Task type:** standard"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("owned file 'none' does not exist", r.stdout)
        self.assertIn("'report: findings list in the Report format' has no runnable", r.stdout)

    def test_thin_packet_lists_every_gap(self):
        r = self.run_fixture("packet-thin.md")
        self.assertEqual(r.returncode, 2)
        for problem in ("goal is empty", "is not an existing absolute path", "owned-file list is empty",
                        "acceptance has no bullets", "network task has no smoke test",
                        "report format is missing STATUS:, FILES:, BLOCKERS:, NOTES:"):
            self.assertIn(problem, r.stdout)

    def test_prose_acceptance_is_rejected(self):
        r = self.run_fixture("packet-prose-acceptance.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("has no runnable `command`", r.stdout)

    def test_placeholder_and_missing_owned_file_are_rejected(self):
        r = self.run_fixture("packet-placeholder.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("placeholder text left", r.stdout)
        self.assertIn("'missing.py' does not exist", r.stdout)
        self.assertNotIn("docs/USAGE.md", r.stdout)  # marked (new)


if __name__ == "__main__":
    unittest.main()
