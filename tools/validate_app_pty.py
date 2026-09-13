"""Real-time keyboard-only application run in a controlling Linux PTY.

Read-only capture telemetry guides key choices. No imported rule/movement calls,
no pose/state injection, no fixed clock. Every movement/action uses os.write.
"""
import argparse
import fcntl
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from citywalk.spatial import CityGenerator
from tools.validate_terminal_pty import vt_state


def attrs(value):
    return [item if not isinstance(item, list) else
            [v.hex() if isinstance(v, bytes) else v for v in item] for item in value]


class Session:
    def __init__(self, output, color="truecolor", launch_code=None, launch_command=None, cwd=None):
        output.mkdir(parents=True, exist_ok=True)
        self.output = output
        self.master, self.slave = pty.openpty()
        self.resize(100,36)
        self.before = termios.tcgetattr(self.slave)
        self.events = []
        self.raw = bytearray()
        self.trace = None
        self.latest = None
        self.started = time.monotonic()
        prefix = launch_command or ([sys.executable, "-c", launch_code] if launch_code else [sys.executable, "-m", "citywalk"])
        self.process_cwd = str(cwd or ROOT)
        self.command = prefix + ["--seed", "11", "--color", color,
                        "--capture-dir", str(output)]
        def controlling():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        self.process = subprocess.Popen(self.command, cwd=cwd or ROOT, stdin=self.slave, stdout=self.slave,
                                       stderr=self.slave, preexec_fn=controlling,
                                       env={**os.environ, "TERM": "xterm-256color"})
        self.next()
        self.active = termios.tcgetattr(self.slave)
        assert self.active != self.before

    def resize(self, cols, rows):
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        if hasattr(self, "events"):
            self.events.append({"resize": [cols, rows], "monotonic": time.monotonic()})

    def drain(self, timeout=.01):
        if select.select([self.master], [], [], timeout)[0]:
            self.raw.extend(os.read(self.master, 262144))

    def next(self):
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            self.drain()
            if self.trace is None and (self.output / "trace.jsonl").exists():
                self.trace = (self.output / "trace.jsonl").open()
            if self.trace:
                position = self.trace.tell()
                line = self.trace.readline()
                if line.endswith("\n"):
                    record = json.loads(line)
                    if "state" in record:
                        self.latest = record
                        return record
                elif line:
                    self.trace.seek(position)
            if self.process.poll() is not None:
                raise AssertionError(f"app exited {self.process.returncode}: {self.raw[-2000:]!r}")
        raise AssertionError("no actual application frame in 10 seconds")

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        os.write(self.master, data)
        self.events.append({"input_hex": data.hex(), "monotonic": time.monotonic(),
                            "after_frame": self.latest["frame"]})

    def wait(self, seconds):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            self.next()
        return self.latest

    def edge(self, key, field):
        self.send(key)
        for _ in range(20):
            record = self.next()
            if record["actions"][field]:
                return record
        raise AssertionError(f"edge {key!r} not observed")

    def orient(self, yaw=0, pitch=0):
        self.wait(.20)  # let terminal digital holds expire before measuring
        for _ in range(80):
            p = self.latest["player"]
            dy = (yaw-p["yaw"]+math.pi) % math.tau-math.pi
            dp = pitch-p["pitch"]
            if abs(dy) < .13 and abs(dp) < .10:
                return
            keys = ("l" if dy > 0 else "j") if abs(dy) >= .13 else ""
            keys += (("i" if dp > 0 else "k") if abs(dp) >= .10 else "")
            self.send(keys)
            self.wait(.21)
        raise AssertionError("digital-key aiming did not converge")

    def walk_to(self, point):
        deadline = time.monotonic()+90
        while time.monotonic() < deadline:
            p = self.latest["player"]
            dx, dz = point.x-p["feet"]["x"], point.z-p["feet"]["z"]
            if math.hypot(dx,dz) < .65:
                self.wait(.20)
                return
            # Local axes, feedback only; route waypoints are planning metadata.
            forward = dx*math.sin(p["yaw"])+dz*math.cos(p["yaw"])
            right = dx*math.cos(p["yaw"])-dz*math.sin(p["yaw"])
            keys = ("w" if forward > 0 else "s") if abs(forward) > .40 else ""
            keys += (("d" if right > 0 else "a") if abs(right) > .40 else "")
            self.send(keys)
            self.next()
            assert self.latest["state"]["phase"] == "playing", "survey ended before submission"
        raise AssertionError(f"route stalled approaching {point}: {self.latest}")

    def close(self, key="q"):
        if key is not None:
            self.send(key)
        deadline = time.monotonic()+10
        while self.process.poll() is None and time.monotonic() < deadline:
            self.drain()
        if self.process.poll() is None:
            raise AssertionError("application did not quit")
        while select.select([self.master], [], [], .05)[0]:
            self.drain(0)
        after = termios.tcgetattr(self.slave)
        assert after == self.before, "termios not exactly restored"
        state = vt_state(self.raw)
        (self.output / "terminal.ansi.gz").write_bytes(gzip.compress(bytes(self.raw), mtime=0))
        (self.output / "inputs.json").write_text(json.dumps(self.events, indent=2)+"\n")
        report = {"command": self.command, "cwd": self.process_cwd, "exit_code": self.process.returncode,
                  "wall_seconds": time.monotonic()-self.started,
                  "termios_before": attrs(self.before), "termios_active": attrs(self.active),
                  "termios_after": attrs(after), "termios_exactly_restored": after == self.before,
                  "vt_state": state, "raw_transcript_bytes": len(self.raw),
                  "raw_transcript_sha256": hashlib.sha256(self.raw).hexdigest(),
                  "last_frame": self.latest, "inputs": "inputs.json"}
        (self.output / "pty-result.json").write_text(json.dumps(report, indent=2)+"\n")
        if self.trace:
            self.trace.close()
        os.close(self.master)
        os.close(self.slave)
        return report


def full_run(output, launcher=None, cwd=None):
    if output.exists():
        raise FileExistsError(f"Use a fresh evidence directory: {output}")
    session = Session(output, launch_command=[str(launcher)] if launcher else None, cwd=cwd)
    try:
        assert session.latest["help_page"] == 0
        for page in range(1,7):
            session.wait(.30)
            r = session.edge(" ", "shutter")
            assert r["help_page"] == page and r["state"]["remaining_s"] == 600
        session.edge("h", "help")
        session.wait(.20)
        session.edge("e", "interact")
        assert "rejected" in " ".join(session.latest["messages"])
        # Real collision, not an injected blocked flag: walk diagonally into a facade.
        deadline = time.monotonic()+25
        while not session.latest["blocked"] and time.monotonic() < deadline:
            session.send("wd")
            session.next()
        assert session.latest["blocked"], "no collision reached"
        collision_frame = session.latest["frame"]
        session.edge("r", "restart")
        assert session.latest["state"]["remaining_s"] == 600
        session.wait(.20)
        session.edge("p", "pause")
        frozen = session.latest["state"]
        feet = session.latest["player"]
        session.send("wl ")
        session.resize(80,24)
        # At least 300 real minimum-size frames (actual renderer + terminal).
        first = session.latest["frame"]
        while session.latest["frame"]-first < 305:
            session.next()
            assert session.latest["state"] == frozen and session.latest["player"] == feet
        session.resize(70,20)
        session.wait(.30)
        assert session.latest["small"] and session.latest["state"] == frozen
        session.resize(100,36)
        session.wait(.30)
        session.edge("p", "pause")
        # Actual turning then return to north, no pose changes outside the application.
        session.send("l")
        session.wait(.20)
        assert session.latest["player"]["yaw"] > 0
        session.orient()
        world = CityGenerator().generate(11)
        route = world.survey_route()
        todo = list(route.landmark_ids)
        landmarks = {l.id:l for l in world.city.landmarks}
        photo_frames = []
        for index, point in enumerate(route.points):
            session.walk_to(point)
            print("waypoint", index, "/", len(route.points), "frame", session.latest["frame"], flush=True)
            if todo:
                landmark = landmarks[todo[0]]
                if math.hypot(point.x-landmark.viewpoint.x, point.z-landmark.viewpoint.z) < 1e-8:
                    session.orient(landmark.view_yaw, landmark.view_pitch)
                    r = session.edge(" ", "shutter")
                    assert landmark.id in dict(r["state"]["photos"]), r
                    photo_frames.append(r["frame"])
                    todo.pop(0)
                    session.orient()
        assert not todo
        r = session.edge("e", "interact")
        assert r["state"]["phase"] == "won", r
        won = r
        session.send("wli ")
        session.wait(.40)
        assert session.latest["state"] == won["state"] and session.latest["player"] == won["player"]
        r = session.edge("r", "restart")
        assert r["state"]["score"] == 0 and r["state"]["remaining_s"] == 600 and r["seed"] == 11
        session.wait(.30)
        r = session.edge("n", "new_seed")
        assert r["seed"] == 12 and r["state"]["photos"] == []
        report = session.close()
        assert report["exit_code"] == 0
        summary = {"passed": True, "collision_frame": collision_frame, "photo_frames": photo_frames,
                   "won_frame": won["frame"], "won_state": won["state"], "won_player": won["player"],
                   "termios_exactly_restored": report["termios_exactly_restored"],
                   "wall_seconds": report["wall_seconds"], "native_windows_validated": False,
                   "independent_beauty_or_fun_validated": False}
        (output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
        print(json.dumps(summary, indent=2))
    finally:
        if session.process.poll() is None:
            try:
                session.close()
            finally:
                if session.process.poll() is None:
                    session.process.terminate()
                    session.process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/app-pty")
    parser.add_argument("--launcher", type=Path, help="Installed Linux launcher to exercise instead of source module")
    parser.add_argument("--cwd", type=Path, help="Unrelated working directory for installed launch")
    args = parser.parse_args()
    full_run(args.output.resolve(), args.launcher.resolve() if args.launcher else None,
             args.cwd.resolve() if args.cwd else None)


if __name__ == "__main__":
    main()
