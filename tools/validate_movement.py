"""Run actual movement/regression checks and persist their unedited output."""
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    inputs = sorted(set(ROOT.glob("citywalk/*.py")) | set(ROOT.glob("tests/*.py")) |
                    {ROOT / "tools/validate_movement.py", ROOT / "docs/movement.md",
                     ROOT / "README.md", ROOT / "docs/renderer-frames/frames.json"})
    report = {
        "scope": "G11 node 6: injected-action movement, not terminal/gameplay validation",
        "platform": platform.platform(), "python": sys.version,
        "base_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in inputs},
        "commands": [],
    }
    for args in (["-m", "unittest", "discover", "-s", "tests", "-p", "test_movement.py", "-v"],
                 ["-m", "unittest", "discover", "-s", "tests", "-v"],
                 ["tools/capture_renderer.py", "--check"]):
        command = [sys.executable, *args]
        start = time.perf_counter()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        entry = {"command": command, "returncode": run.returncode,
                 "elapsed_s": time.perf_counter()-start,
                 "stdout": run.stdout, "stderr": run.stderr}
        report["commands"].append(entry)
        print("COMMAND:", " ".join(command), flush=True)
        print(run.stdout, end="", flush=True)
        print(run.stderr, end="", flush=True)
    report["passed"] = all(c["returncode"] == 0 for c in report["commands"])
    output = ROOT / "docs/movement-run.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print("Evidence:", output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
