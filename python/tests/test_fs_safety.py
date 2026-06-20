import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kbprep_worker.fs_safety import safe_rmtree, safe_unlink


class FileSystemSafetyTests(unittest.TestCase):
    def test_safe_rmtree_refuses_paths_outside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            outside = Path(tmp) / "outside"
            root.mkdir()
            outside.mkdir()

            with self.assertRaisesRegex(RuntimeError, "outside"):
                safe_rmtree(outside, root=root)

            self.assertTrue(outside.exists())

    def test_safe_rmtree_reports_windows_delete_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "locked"
            target.mkdir()

            with mock.patch("kbprep_worker.fs_safety.shutil.rmtree", side_effect=PermissionError("locked")):
                with self.assertRaisesRegex(RuntimeError, "Failed to remove directory"):
                    safe_rmtree(target, root=root, retries=1, retry_delay=0)

    def test_safe_unlink_respects_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "artifact.txt"
            target.write_text("keep", encoding="utf-8")

            removed = safe_unlink(target, root=root, dry_run=True)

            self.assertTrue(removed)
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
