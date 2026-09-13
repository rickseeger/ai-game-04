import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from citywalk.contracts import Actions, Camera, Vec3, Viewport


class FoundationSmoke(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "citywalk", *args],
                              capture_output=True, text=True, timeout=10)

    def test_real_smoke_launch(self):
        run = self.run_cli("--smoke", "--seed", "93")
        self.assertEqual(run.returncode, 0, run.stderr)
        data = json.loads(run.stdout)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["stage"], "foundation")
        self.assertEqual(data["seed"], 93)
        self.assertEqual(data["eye_height_m"], 1.7)
        self.assertEqual(data["viewport"], [100, 32])

    def test_default_launch_is_honest_and_terminal_safe(self):
        run = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("not implemented", run.stdout)
        self.assertNotIn("\x1b", run.stdout)

    def test_help_and_version(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        self.assertEqual(self.run_cli("--version").stdout.strip(), "0.1.0")

    def test_invalid_seed_rejected(self):
        self.assertEqual(self.run_cli("--seed", "bad").returncode, 2)

    def test_shared_defaults_are_immutable(self):
        camera = Camera(Vec3(0, 1.7, 0))
        self.assertEqual(camera.near, 0.1)
        self.assertEqual(Viewport(100, 32).cell_aspect, 0.5)
        self.assertFalse(Actions().shutter)
        with self.assertRaises(FrozenInstanceError):
            camera.yaw = 1


if __name__ == "__main__":
    unittest.main()
