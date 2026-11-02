import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "orchestrate" / "scripts"


class OrchestrateScripts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        # A fake hc records every call, so a test can prove nothing reached the child.
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        self.hc_log = self.tmp / "hc.log"
        (bin_dir / "hc").write_text(f'#!/bin/sh\necho "$@" >> "{self.hc_log}"\n')
        (bin_dir / "hc").chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.tmp), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        self.run_ok("git", "init", "-q", "-b", "my-task")

    def run_ok(self, *cmd):
        subprocess.run(cmd, cwd=self.repo, env=self.env, check=True, capture_output=True)

    def script(self, name, *args):
        return subprocess.run([str(SCRIPTS / name), *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def task_dir(self):
        self.run_ok("python3", str(SCRIPTS.parents[1] / "rpilayer.py"), "state", "my-task")
        repo_id = subprocess.run(["git", "config", "--get", "rpilayer.repo-id"], cwd=self.repo,
                                 capture_output=True, text=True).stdout.strip()
        task = self.tmp / ".rpilayer/repos" / repo_id / "tasks/my-task"
        task.mkdir(parents=True, exist_ok=True)
        return task

    def outline(self, box):
        # PRD/TDD track: the outline is 03, outside the old 04-09 glob.
        task = self.task_dir()
        (task / "03-structure-outline-x.md").write_text(
            f"# Phase 1\n\n#### Manual Verification\n\n- [{box}] open the page\n\n# Phase 2\n")
        return task

    def test_gate_fails_on_unchecked_box_in_03_outline(self):
        task = self.outline(" ")
        (task / "verification").mkdir()
        (task / "verification/phase-1-check-1.png").write_bytes(b"")
        result = self.script("verify-gate.sh", str(self.repo))
        self.assertEqual(result.returncode, 1)
        self.assertIn("open the page", result.stdout)

    def test_gate_passes_when_checked_with_screenshot(self):
        task = self.outline("x")
        (task / "verification").mkdir()
        (task / "verification/phase-1-check-1.png").write_bytes(b"")
        self.assertEqual(self.script("verify-gate.sh", str(self.repo)).returncode, 0)

    def test_gate_sees_boxes_in_nested_subsections(self):
        task = self.task_dir()
        (task / "05-plan-x.md").write_text(
            "#### Manual Verification\n\n##### Keyboard\n\n- [ ] tab to the button\n\n## Phase 2\n")
        (task / "verification").mkdir()
        (task / "verification/phase-1-check-1.png").write_bytes(b"")
        result = self.script("verify-gate.sh", str(self.repo))
        self.assertEqual(result.returncode, 1)
        self.assertIn("tab to the button", result.stdout)

    def test_advance_resends_brief_and_parent_after_clear(self):
        task = self.task_dir()
        (task / "01-research-x.md").write_text("# Research\n")
        result = subprocess.run([str(SCRIPTS / "advance.sh"), "t1", str(self.repo)], cwd=self.repo,
                                env={**self.env, "ORCHESTRATE_PARENT": "boss"}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.hc_log.read_text().splitlines()
        self.assertTrue(calls[0].startswith("keys t1 / c l e a r"))
        self.assertIn("child-brief.md", calls[2])
        self.assertIn("boss", calls[2])
        self.assertEqual(calls[-1], "send t1 /rpilayer")

    def test_gate_fails_without_outline_or_plan(self):
        self.task_dir()
        self.assertEqual(self.script("verify-gate.sh", str(self.repo)).returncode, 1)

    def test_advance_sends_nothing_on_state_error(self):
        self.run_ok("git", "switch", "-q", "-c", "no-task")  # no task matches: state returns an error
        result = subprocess.run([str(SCRIPTS / "advance.sh"), "t1", str(self.repo)], cwd=self.repo,
                                env={**self.env, "ORCHESTRATE_PARENT": "boss"}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 5)
        self.assertFalse(self.hc_log.exists())


if __name__ == "__main__":
    unittest.main()
