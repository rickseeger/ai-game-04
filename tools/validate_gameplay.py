"""Run real node 8 evidence commands; retain failures as failures. Stdlib only."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    inputs = sorted(p for folder in ("citywalk", "tests", "tools")
                    for p in (ROOT / folder).glob("*.py"))
    inputs += [ROOT / "docs/design.md", ROOT / "docs/gameplay.md", ROOT / "README.md"]
    report = {"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "platform": platform.platform(), "python": sys.version,
              "executable": sys.executable, "cwd": str(ROOT),
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in inputs}, "commands": []}
    commands = [[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                [sys.executable, "tools/simulate_survey.py", "--seeds", "11", "93", "2026"],
                [sys.executable, "tools/simulate_survey.py", "--replay", "docs/gameplay-simulation.json"],
                [sys.executable, "tools/build.py"],
                [sys.executable, "dist/lantern-survey.pyz", "--smoke", "--seed", "11"]]
    for command in commands:
        print("COMMAND:", " ".join(command), flush=True)
        start = time.perf_counter()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        report["commands"].append({"argv": command, "returncode": run.returncode,
                                   "wall_seconds": time.perf_counter()-start,
                                   "stdout": run.stdout, "stderr": run.stderr})
        print(run.stdout, end="", flush=True)
        print(run.stderr, end="", flush=True)
    report["passed"] = all(c["returncode"] == 0 for c in report["commands"])
    simulation = ROOT / "docs/gameplay-simulation.json"
    if simulation.exists():
        report["simulation_sha256"] = hashlib.sha256(simulation.read_bytes()).hexdigest()
        report["route_outcomes"] = [
            {k: run["summary"][k] for k in ("seed", "elapsed_s", "distance_m", "steps", "final_state")}
            for run in json.loads(simulation.read_text())["runs"]]
    output = ROOT / "docs/gameplay-run.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print("Evidence:", output, "passed:", report["passed"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
