"""Record actual regression/build/capture readback, after the real PTY run."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    commands = ([sys.executable,"-m","unittest","discover","-s","tests","-v"],
                [sys.executable,"-m","citywalk","--smoke","--seed","11"],
                [sys.executable,"tools/build.py"],
                [sys.executable,"dist/lantern-survey.pyz","--smoke","--seed","93"],
                [sys.executable,"tools/verify_app_evidence.py"])
    report={"platform":platform.platform(),"python":sys.version,"commands":[],
            "source_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                             for folder in ("citywalk","tests","tools") for p in sorted((ROOT/folder).glob("*.py"))}}
    try:
        report["cpu"]=subprocess.check_output(["lscpu"],text=True)
    except (OSError,subprocess.CalledProcessError):
        report["cpu"]=platform.processor()
    passed=True
    for command in commands:
        start=time.monotonic()
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=180)
        report["commands"].append({"command":command,"exit_code":result.returncode,
            "wall_seconds":time.monotonic()-start,"stdout":result.stdout,"stderr":result.stderr})
        print("exit",result.returncode," ".join(command),flush=True)
        passed &= result.returncode==0
    artifact=ROOT/"dist/lantern-survey.pyz"
    if artifact.exists():
        report["local_zipapp_sha256"]=hashlib.sha256(artifact.read_bytes()).hexdigest()
    report["passed"]=passed
    report["scope"]="Local source and zipapp smoke only; platform distribution verification belongs to node 10. No independent enjoyment/beauty or Windows runtime claim."
    (ROOT/"docs/integration-run.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if passed else 1


if __name__=="__main__":
    raise SystemExit(main())
