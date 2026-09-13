#!/usr/bin/env python3
"""Independent readback of real PTY files; geometric checks do not call Walker.
Requires completed fresh-linux and supplemental-* directories under --workspace.
"""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.workspace.resolve()
    clone = root/"fresh-linux/clone"
    sys.path.insert(0, str(clone))
    from citywalk.spatial import CityGenerator
    from tools.validate_terminal_pty import vt_state
    source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (clone/"citywalk").glob("*.py")}
    validation = json.loads((root/"fresh-linux/validation.json").read_text())
    assert validation["passed"]
    cases = [root/"fresh-linux/pty"]
    for flavor in ("source", "artifact"):
        directory = root/("supplemental-"+flavor)
        assert json.loads((directory/"summary.json").read_text())["passed"]
        cases.extend(directory/name for name in ("controls_q", "escape_256", "ctrl_c", "sigterm"))
    results = []
    for case in cases:
        meta = json.loads((case/"metadata.json").read_text())
        assert meta["source_sha256"] == source
        if "supplemental-source" in str(case):
            assert meta["source_sha"] == validation["source_commit"] and not meta["dirty"]
        else:
            assert meta["distribution"]["source_commit"] == validation["source_commit"]
        raw = gzip.decompress((case/"terminal.ansi.gz").read_bytes())
        result = json.loads((case/"pty-result.json").read_text())
        assert hashlib.sha256(raw).hexdigest() == result["raw_transcript_sha256"]
        assert len(raw) == result["raw_transcript_bytes"]
        assert result["termios_before"] == result["termios_after"] != result["termios_active"]
        vt = vt_state(raw)
        frames = [json.loads(line) for line in gzip.decompress((case/"frames.jsonl.gz").read_bytes()).decode().splitlines()]
        assert frames and any(f["cells"] for f in frames)
        results.append(dict(path=str(case.relative_to(root)), actual_captured_checkpoints=len(frames),
                            source_hashes_match=True, exit_code=result["exit_code"],
                            termios_exactly_restored=True, vt_state=vt))
    records = [json.loads(line) for line in (root/"fresh-linux/pty/trace.jsonl").read_text().splitlines()]
    states = [r for r in records if "state" in r]
    worlds = {seed: CityGenerator().generate(seed).city for seed in {r["seed"] for r in states}}
    def distance(p, rect):
        return math.hypot(max(rect.xmin-p["x"], 0, p["x"]-rect.xmax),
                          max(rect.zmin-p["z"], 0, p["z"]-rect.zmax))
    minimum = math.inf
    collisions = []
    for r in states:
        p, city = r["player"]["feet"], worlds[r["seed"]]
        assert p["y"] == 0
        assert city.bounds.xmin+.3 <= p["x"] <= city.bounds.xmax-.3
        assert city.bounds.zmin+.3 <= p["z"] <= city.bounds.zmax-.3
        nearest = min(city.buildings, key=lambda b: distance(p, b.footprint))
        clearance = distance(p, nearest.footprint)
        minimum = min(minimum, clearance)
        assert clearance >= .3-1e-8, (r["frame"], nearest.id, clearance)
        if r["blocked"]:
            assert clearance < .3001, ("not a verified building collision", r["frame"], clearance)
            collisions.append(dict(frame=r["frame"], building=asdict(nearest), player=r["player"], clearance_m=clearance))
    assert collisions
    won = next(r for r in states if r["state"]["phase"] == "won")
    assert won["actions"]["interact"] and won["state"]["remaining_s"] > 0
    photos = won["state"]["photos"]
    assert len({photo[0] for photo in photos}) >= 3
    depot = worlds[won["seed"]].depot
    depot_distance = math.hypot(won["player"]["feet"]["x"]-depot.x, won["player"]["feet"]["z"]-depot.z)
    assert depot_distance < 3
    result = dict(passed=True, source_commit=validation["source_commit"], pty_sessions=results,
                  geometry_checked_frames=len(states), minimum_building_clearance_m=minimum,
                  building_collisions=collisions, win_frame=won["frame"], win_state=won["state"],
                  depot_distance_at_submission_m=depot_distance,
                  limitations="World geometry reused from committed generator; clearance independently calculated from rectangles, not game collision result. Frame replay in validator is scripted consistency verification. PTY mode and ANSI checks do not certify a physical emulator or human enjoyment.")
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
