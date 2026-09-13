"""Read-back checks of actual PTY trace, captured frames and source binding.

The real PTY run is required first; replay checks consistency, not human quality.
"""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from citywalk.app import Application
from citywalk.contracts import Actions, Player, Vec3
from tools.validate_terminal_pty import vt_state


def verify(path):
    meta=json.loads((path/"metadata.json").read_text())
    for name,digest in meta["source_sha256"].items():
        assert hashlib.sha256((ROOT/"citywalk"/name).read_bytes()).hexdigest()==digest, name
    transcript=gzip.decompress((path/"terminal.ansi.gz").read_bytes())
    result=json.loads((path/"pty-result.json").read_text())
    assert hashlib.sha256(transcript).hexdigest()==result["raw_transcript_sha256"]
    assert len(transcript)==result["raw_transcript_bytes"]
    assert result["termios_before"]==result["termios_after"]!=result["termios_active"]
    assert result["exit_code"]==0
    vt_state(transcript)
    summary=json.loads((path/"summary.json").read_text())
    assert summary["passed"] and summary["won_state"]["phase"]=="won"
    app=Application(meta["seed"],meta["cell_aspect"])
    records=[json.loads(line) for line in (path/"trace.jsonl").read_text().splitlines()]
    distance=0.0
    frames=0
    blocked=0
    for r in records:
        actions=Actions(**r["actions"])
        if r.get("event")=="quit":
            assert actions.quit
            continue
        before=app.player
        app.tick(actions,r["dt_s"],r["size"])
        assert json.loads(json.dumps(asdict(app.player)))==r["player"], (r["frame"],"player")
        assert json.loads(json.dumps(asdict(app.state)))==r["state"], (r["frame"],"state")
        assert app.blocked==r["blocked"]
        assert list(app.hud(r["size"]))==r["hud"]
        assert app.world.walkable(app.player.feet,.3)
        if not actions.restart and not actions.new_seed:
            step=math.hypot(app.player.feet.x-before.feet.x,app.player.feet.z-before.feet.z)
            assert step <= 4*min(.1,r["dt_s"])+1e-8
            distance+=step
        blocked+=int(app.blocked)
        frames+=1
    checkpoints=[json.loads(line) for line in gzip.decompress((path/"frames.jsonl.gz").read_bytes()).decode().splitlines()]
    by_frame={r["frame"]:r for r in records}
    for frame in checkpoints:
        r=by_frame[frame["frame"]]
        assert r["checkpoint"]==frame["checkpoint"]
        app=Application(r["seed"],meta["cell_aspect"])
        p=r["player"]
        app.player=Player(Vec3(**p["feet"]),p["yaw"],p["pitch"])
        app.small=r["small"]
        actual=app.render(r["size"])
        assert json.loads(json.dumps([[c.glyph,c.fg,c.bg] for c in actual.cells]))==frame["cells"]
        assert [v if math.isfinite(v) else None for v in actual.depth]==frame["depth"]
        if not r["small"]:
            for line in r["hud"]:
                assert line.encode() in transcript, (r["frame"],line)
    inputs=json.loads((path/"inputs.json").read_text())
    keys=b"".join(bytes.fromhex(r["input_hex"]) for r in inputs if "input_hex" in r)
    assert all(key in keys for key in (b"w",b"d",b"l",b"i",b" ",b"e",b"h",b"p",b"r",b"n",b"q"))
    assert any(r.get("resize")==[80,24] for r in inputs)
    assert any(r.get("resize")==[70,20] for r in inputs)
    report={"passed":True,"source_hashes_match":True,"trace_frames_replayed_exactly":frames,
            "actual_checkpoints_regenerated_exactly":len(checkpoints),"collision_frames":blocked,
            "walked_distance_m_excluding_resets":distance,"transcript_sha256":result["raw_transcript_sha256"],
            "termios_exactly_restored":True,"won_state":summary["won_state"],
            "limitations":"Exact action replay and regenerated frames confirm consistency of actual PTY evidence, not independent beauty, enjoyment or native Windows execution."}
    (path/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path",type=Path,nargs="?",default=ROOT/"docs/app-pty")
    verify(parser.parse_args().path)
