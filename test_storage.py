"""Storage regression tests using real Git worktrees and an isolated home."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rpilayer import PLUGIN, base, judge, migrate, state, tasks_root


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "home"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.home.mkdir()
        self.cwd = Path.cwd()
        self.addCleanup(os.chdir, self.cwd)
        os.chdir(self.repo)
        self.home_patch = patch("rpilayer.Path.home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.env_patch = patch.dict(os.environ, {"RPI_REPO": str(self.base), "GIT_CONFIG_GLOBAL": os.devnull})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.git("init")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "init")

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()

    def worktree(self):
        path = self.base / "workspace"
        self.git("worktree", "add", "-b", "test-task", str(path))
        return path

    def write(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_shared_state_from_nested_worktree_and_new_session(self):
        first = state("test-task")
        task = Path(first["task_dir"])
        self.assertTrue(task.is_relative_to(self.home / ".rpilayer/repos"))
        self.write(task, "01-research-questions-test.md", "questions")
        wt = self.worktree()
        nested = wt / "src"
        nested.mkdir()
        os.chdir(nested)
        self.assertEqual(state()["task_dir"], str(task))
        self.write(task, "02-research-test.md", "updated")
        env = dict(os.environ, HOME=str(self.home))
        script = Path(__file__).resolve().with_name("rpilayer.py")
        result = subprocess.run(["python3", str(script), "state"], env=env, check=True, capture_output=True, text=True)
        import json
        resumed = json.loads(result.stdout)
        self.assertEqual(resumed["latest"]["kind"], "research")
        self.assertEqual(resumed["next"], "create-design-discussion")
        os.chdir(self.repo)
        self.assertEqual(state()["latest"], resumed["latest"])

    def test_humanlayer_checkout_clones_then_refreshes_daily(self):
        upstream = self.base / "upstream"
        skill = upstream / PLUGIN / "skills/x/SKILL.md"
        commit = lambda text: (self.write(upstream, skill.relative_to(upstream), text),
                               self.git("-C", str(upstream), "add", "-A"),
                               self.git("-C", str(upstream), "-c", "user.name=T", "-c", "user.email=t@e", "commit", "-m", text))
        self.git("init", str(upstream))
        commit("v1")
        os.environ.pop("RPI_REPO")
        with patch("rpilayer.REPO_URL", upstream.as_uri()):
            read = lambda: (base() / "skills/x/SKILL.md").read_text()
            self.assertEqual(read(), "v1")
            commit("v2")
            self.assertEqual(read(), "v1")  # fetched less than a day ago
            stamp = self.home / ".rpilayer/humanlayer/.git/rpilayer-fetched"
            os.utime(stamp, (0, 0))
            self.assertEqual(read(), "v2")

    def test_explicit_migration_combines_worktrees_and_keeps_backups(self):
        original = self.repo / ".humanlayer/tasks/test-task"
        self.write(original, "ticket.md", "ticket")
        self.write(original, "01-research-questions-test.md", "questions")
        wt = self.worktree()
        local = wt / ".humanlayer/tasks/test-task"
        self.write(local, "02-research-test.md", "updated")
        os.chdir(wt)
        before = state()
        self.assertTrue(before["migration_required"])
        self.assertNotIn("next", before)
        self.assertEqual(len(before["legacy_task_dirs"]), 2)
        with patch("rpilayer.urllib.request.urlopen") as request:
            self.assertIn("error", judge("test-task", {"message": "continue"}))
            request.assert_not_called()
        result = migrate("test-task")
        self.assertNotIn("error", result)
        self.assertEqual(len(result["backups"]), 2)
        self.assertTrue(all(Path(path).is_dir() for path in result["backups"]))
        self.assertFalse(original.exists())
        self.assertFalse(local.exists())
        after = state()
        self.assertEqual(after["latest"]["kind"], "research")
        self.assertTrue(after["has_ticket"])
        self.assertEqual(len(after["artifacts"]), 2)
        self.assertEqual(migrate()["backups"], [])
        self.write(Path(after["task_dir"]), "02-research-test.md", "new canonical update")
        os.chdir(self.repo)
        self.assertNotIn("error", state())

    def test_conflict_does_not_copy_or_archive_anything(self):
        original = self.repo / ".humanlayer/tasks/test-task"
        file = self.write(original, "ticket.md", "original")
        self.write(original, "01-research-questions-test.md", "questions")
        wt = self.worktree()
        local = wt / ".humanlayer/tasks/test-task"
        other = self.write(local, "ticket.md", "different")
        result = migrate()
        self.assertIn("conflicts", result)
        self.assertFalse(tasks_root().exists())
        self.assertEqual(file.read_text(), "original")
        self.assertEqual(other.read_text(), "different")

    def test_conflict_with_central_document_is_not_overwritten(self):
        central = self.write(tasks_root() / "test-task", "ticket.md", "central")
        legacy = self.write(self.repo / ".humanlayer/tasks/test-task", "ticket.md", "legacy")
        self.assertIn("conflicts", migrate("test-task"))
        self.assertEqual(central.read_text(), "central")
        self.assertEqual(legacy.read_text(), "legacy")

    def test_identical_copies_can_be_migrated(self):
        central = self.write(tasks_root() / "test-task", "ticket.md", "same")
        self.write(self.repo / ".humanlayer/tasks/test-task", "ticket.md", "same")
        self.assertNotIn("error", migrate())
        self.assertEqual(central.read_text(), "same")
        self.assertTrue(state()["has_ticket"])

    def test_empty_task_migration_and_nested_assets(self):
        legacy = self.repo / ".humanlayer/tasks/test-task"
        legacy.mkdir(parents=True)
        self.assertNotIn("error", migrate())
        self.assertTrue((tasks_root() / "test-task").is_dir())
        self.write(legacy, "assets/note.txt", "nested")
        self.assertNotIn("error", migrate())
        self.assertEqual((tasks_root() / "test-task/assets/note.txt").read_text(), "nested")

    def test_symlink_requires_manual_migration(self):
        legacy = self.repo / ".humanlayer/tasks/test-task"
        legacy.mkdir(parents=True)
        outside = self.write(self.base, "outside.md", "outside")
        (legacy / "ticket.md").symlink_to(outside)
        self.assertIn("conflicts", migrate())
        self.assertFalse(tasks_root().exists())
        self.assertEqual(outside.read_text(), "outside")

    def test_file_directory_conflict_blocks_the_whole_migration(self):
        original = self.repo / ".humanlayer/tasks/test-task"
        self.write(original, "assets", "a file")
        wt = self.worktree()
        self.write(wt / ".humanlayer/tasks/test-task", "assets/note.txt", "nested")
        self.assertIn("conflicts", migrate())
        self.assertFalse(tasks_root().exists())
        self.assertTrue(original.exists())

    def test_central_completion_is_read_from_other_worktree(self):
        central = tasks_root() / "test-task"
        file = self.write(central, "04-structure-outline-test.md", "- [ ] Phase 1: first\n")
        wt = self.worktree()
        self.assertEqual(state()["next"], "implement-outline")
        file.write_text("- [x] Phase 1: first\n")
        os.chdir(wt)
        self.assertEqual(state()["next"], "describe-pr")

    def test_repository_identity_survives_move_and_separates_same_names(self):
        first = tasks_root()
        moved = self.base / "moved"
        os.chdir(self.base)
        self.repo.rename(moved)
        os.chdir(moved)
        self.assertEqual(tasks_root(), first)
        other = self.base / "other/repo"
        other.mkdir(parents=True)
        os.chdir(other)
        self.git("init")
        self.assertNotEqual(tasks_root(), first)

    def test_finished_task_is_not_picked_and_worktree_remembers_its_task(self):
        root = tasks_root()
        self.write(root / "old-task", "pr-description.md", "done")
        wt = self.worktree()  # branch test-task, unlike the slug below
        os.chdir(wt)
        self.assertEqual(state()["tasks"], ["old-task"])
        self.write(root / "other-task", "ticket.md", "other")
        state("new-task")
        self.write(root / "new-task", "ticket.md", "new")
        self.assertEqual(state()["slug"], "new-task")
        # The main checkout remembers nothing: two open tasks there means asking.
        os.chdir(self.repo)
        self.assertEqual(state()["tasks"], ["new-task", "old-task", "other-task"])

    def test_task_selection_and_path_validation(self):
        root = tasks_root()
        (root / "task-a").mkdir(parents=True)
        (root / "task-b").mkdir()
        self.assertEqual(state()["tasks"], ["task-a", "task-b"])
        self.assertEqual(state()["tasks_dir"], str(root))
        for slug in ("../outside", "/outside", "a/b"):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                state(slug)
            with self.assertRaises(ValueError):
                migrate(slug)


if __name__ == "__main__":
    unittest.main()
