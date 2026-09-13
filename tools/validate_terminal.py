#!/usr/bin/env python3
"""Execute and durably record terminal/regression/build verification, no fake data."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_terminal.py", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "tools/validate_terminal_pty.py"],
        [sys.executable, "tools/probe_terminal.py", "--help"],
        [sys.executable, "tools/build.py"],
        [sys.executable, "dist/lantern-survey.pyz", "--smoke", "--seed", "11"],
        [sys.executable, "-m", "citywalk", "--smoke", "--seed", "93"],
    ]
    results = []
    for command in commands:
        start = time.monotonic()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        results.append({"command": command, "returncode": run.returncode,
                        "seconds": time.monotonic()-start, "stdout": run.stdout, "stderr": run.stderr})
        print(f"exit={run.returncode}: {' '.join(command)}")
    source_files = ["citywalk/terminal.py", "citywalk/app.py", "tests/test_terminal.py", "tools/probe_terminal.py",
                    "tools/validate_terminal.py", "tools/validate_terminal_pty.py"]
    report = {"platform": platform.platform(), "python": sys.version,
              "base_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
              "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_files},
              "results": results, "all_commands_passed": all(r["returncode"] == 0 for r in results),
              "windows": {"native_validated": False, "host": sys.platform,
                          "wine64_on_path": shutil.which("wine64"),
                          "limitation": "No native Windows console accessible in this Linux worker. Wine is not native Windows proof. Portable Windows mocks are tested; delivery requires actual Windows launch/control/cleanup evidence at exact candidate SHA."}}
    (ROOT / "docs/terminal-run.json").write_text(json.dumps(report, indent=2)+"\n")
    return 0 if report["all_commands_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
