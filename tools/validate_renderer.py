"""Record real regression/build/isolated-zip-render execution for node 5."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"docs"/"renderer-run.json")
    args = parser.parse_args()
    records = []
    def run(argv, cwd=ROOT):
        start = time.perf_counter()
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=300)
        records.append({"argv": argv, "cwd": str(cwd), "returncode": p.returncode,
                        "seconds": time.perf_counter()-start, "stdout": p.stdout, "stderr": p.stderr})
        print("$ "+" ".join(argv), flush=True)
        print(p.stdout+p.stderr, end="", flush=True)
        return p.returncode
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "tools/capture_renderer.py", "--check"],
        [sys.executable, "tools/measure_projection.py", "--check"],
        [sys.executable, "tools/preview_appearance.py", "--seed", "11", "--check"],
        [sys.executable, "tools/build.py"],
        [sys.executable, "dist/lantern-survey.pyz", "--smoke", "--seed", "11"],
    ]
    for command in commands:
        run(command)
    archive = ROOT/"dist"/"lantern-survey.pyz"
    first = hashlib.sha256(archive.read_bytes()).hexdigest() if archive.exists() else None
    run([sys.executable, "tools/build.py"])
    second = hashlib.sha256(archive.read_bytes()).hexdigest() if archive.exists() else None
    # -I removes PYTHONPATH/cwd imports; insert only the built zipapp. This
    # exercises the actual renderer packaged in the artifact, not source fallback.
    code = ("import sys,json,hashlib,dataclasses; sys.path.insert(0,sys.argv[1]); "
            "from citywalk.spatial import CityGenerator; from citywalk.camera import Perspective; "
            "from citywalk.appearance import FacadeAppearance; from citywalk.rendering import CityRenderer; "
            "from citywalk.contracts import Camera,Viewport; import citywalk.rendering; "
            "w=CityGenerator().generate(11); lm=w.city.landmarks[2]; "
            "r=CityRenderer(Perspective()); c=Camera(lm.viewpoint,lm.view_yaw,lm.view_pitch); "
            "f=r.render(w,FacadeAppearance(),c,Viewport(100,32)); "
            "s=r.sightings(w,c,Viewport(100,32)); "
            "assert len(f.cells)==3200 and next(x for x in s if x.landmark_id==lm.id).visible; "
            "assert citywalk.rendering.__file__.startswith(sys.argv[1]); "
            "print(json.dumps({\"module\":citywalk.rendering.__file__,\"cells\":len(f.cells),"
            "\"cell_sha256\":hashlib.sha256(json.dumps([dataclasses.asdict(x) for x in f.cells],sort_keys=True).encode()).hexdigest(),"
            "\"sightings\":[dataclasses.asdict(x) for x in s]},sort_keys=True))")
    with tempfile.TemporaryDirectory(prefix="renderer-isolated-", dir=ROOT.parent) as scratch:
        run([sys.executable, "-I", "-c", code, str(archive)], Path(scratch))
    files = (sorted(ROOT.glob("citywalk/*.py"))+sorted(ROOT.glob("tests/*.py"))+
             [ROOT/"tools/capture_renderer.py", ROOT/"tools/validate_renderer.py"]+
             sorted((ROOT/"docs/renderer-frames").glob("*")))
    ok = all(record["returncode"] == 0 for record in records) and first is not None and first == second
    data = {"utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
            "platform": platform.platform(), "commands": records,
            "deterministic_build": {"first_sha256": first, "second_sha256": second, "equal": first == second},
            "file_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            "status": "passed" if ok else "failed",
            "limits": "Local headless renderer/build validation only; no Windows or interactive play/terminal/aesthetic evidence"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2)+"\n")
    print("validation="+data["status"]+" evidence="+str(args.output))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
