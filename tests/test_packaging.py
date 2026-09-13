"""Packaging regressions; interactive validation is a separate real PTY run."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

from tools.package_linux import archive_bytes, committed_source

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="lantern packaging ")
        cls.base = Path(cls.temp.name)
        cls.repo = cls.base / "repo"
        cls.repo.mkdir()
        for name in ("citywalk", "packaging"):
            shutil.copytree(ROOT/name, cls.repo/name, ignore=shutil.ignore_patterns("__pycache__"))
        (cls.repo/"docs").mkdir()
        shutil.copyfile(ROOT/"docs/linux.md", cls.repo/"docs/linux.md")
        for args in (("init", "-q"), ("config", "user.name", "the gardener"),
                     ("config", "user.email", "root@g.seeger.net"),
                     ("add", "."), ("commit", "-qm", "Packaging test fixture")):
            subprocess.run(["git", *args], cwd=cls.repo, check=True, capture_output=True)
        cls.sha = committed_source(cls.repo)
        cls.data, cls.manifest = archive_bytes(cls.repo, cls.sha)
        cls.install = cls.base/"installed with spaces"
        cls.install.mkdir()
        with tarfile.open(fileobj=io.BytesIO(cls.data), mode="r:gz") as tar:
            # Archive names are generated internally; portable to Python 3.11.
            tar.extractall(cls.install)
        cls.launcher = cls.install/"lantern-survey-linux/lantern-survey"
        cls.cwd = cls.base/"unrelated"
        cls.cwd.mkdir()
        (cls.cwd/"citywalk.py").write_text("raise RuntimeError(\"wrong import\")\n")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def launch(self, *args, extra_env=None):
        env = {**os.environ, "LANTERN_PYTHON": sys.executable,
               "PYTHONPATH": str(self.cwd), **(extra_env or {})}
        return subprocess.run([str(self.launcher), *args], cwd=self.cwd,
                              env=env, text=True, capture_output=True, timeout=15)

    def test_validation_cli_and_scope_guards(self):
        from tools.validate_linux import validate
        result = subprocess.run([sys.executable, str(ROOT/"tools/validate_linux.py"), "--help"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaises(ValueError):
            validate("not-a-full-SHA", self.base/"must-not-exist", "unused")
        self.assertFalse((self.base/"must-not-exist").exists())
        with self.assertRaises(FileExistsError):
            validate(self.sha, self.base, "unused")

    def test_byte_reproducibility(self):
        self.assertEqual(archive_bytes(self.repo, self.sha)[0], self.data)

    def test_manifest_and_archive_metadata(self):
        with tarfile.open(fileobj=io.BytesIO(self.data), mode="r:gz") as tar:
            for member in tar.getmembers():
                self.assertTrue(member.name.startswith("lantern-survey-linux/"))
                self.assertTrue(member.isfile())
                self.assertEqual((member.uid, member.gid, member.mtime), (0,0,0))
                self.assertNotIn("__pycache__", member.name)
        root = self.launcher.parent
        manifest = json.loads((root/"BUILD.json").read_text())
        self.assertEqual(manifest["source_commit"], self.sha)
        self.assertEqual(manifest["target"], "linux-python-runtime")
        for name, digest in manifest["files_sha256"].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), digest)
        self.assertTrue(os.access(self.launcher, os.X_OK))

    def test_installed_launch_from_spaces_and_poisoned_cwd(self):
        result = self.launch("--smoke", "--seed", "11")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["stage"], "playable")
        self.assertEqual(json.loads(result.stdout)["seed"], 11)

    def test_help_and_redirected_tty_safety(self):
        self.assertEqual(self.launch("--help").returncode, 0)
        result = self.launch()
        self.assertEqual(result.returncode, 2)
        self.assertIn("TTY", result.stderr)
        self.assertNotIn("\x1b", result.stdout)

    def test_missing_python_is_actionable(self):
        result = self.launch(extra_env={"LANTERN_PYTHON": "/missing/lantern-python"})
        self.assertEqual(result.returncode, 127)
        self.assertIn("Python 3.11+", result.stderr)

    def test_dirty_and_untracked_source_refused(self):
        path = self.repo/"citywalk/app.py"
        original = path.read_bytes()
        try:
            path.write_bytes(original+b"\n# dirty\n")
            with self.assertRaisesRegex(RuntimeError, "provenance"):
                committed_source(self.repo)
        finally:
            path.write_bytes(original)
        path = self.repo/"citywalk/untracked.py"
        try:
            path.write_text("# must not enter release\n")
            with self.assertRaises(RuntimeError):
                committed_source(self.repo)
            self.assertEqual(archive_bytes(self.repo, self.sha)[0], self.data)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
