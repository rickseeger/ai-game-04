#!/usr/bin/env python3
"""Fresh real-game PTY control/lifecycle checks. No state injection or fake clock.
Run with --repo an exact fresh checkout; optionally --launcher an installed build.
All input uses the existing PTY Session transport. Assertions read real telemetry.
"""
import argparse
import hashlib
import json
import math
import signal
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--launcher", type=Path)
    parser.add_argument("--cwd", type=Path)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(repo))
    from tools.validate_app_pty import Session
    checks, cases = [], []
    prefix = [str(args.launcher.resolve())] if args.launcher else [sys.executable, "-m", "citywalk"]
    cwd = args.cwd.resolve() if args.cwd else repo

    def start(name, color="truecolor"):
        return Session(output / name, launch_command=prefix, cwd=cwd, color=color)

    def finish(session, name, key, expected):
        report = session.close(key=key)
        assert report["exit_code"] == expected, report
        assert report["termios_exactly_restored"]
        cases.append(dict(case=name, exit_code=report["exit_code"],
                          termios_exactly_restored=True, vt_state=report["vt_state"],
                          transcript_sha256=report["raw_transcript_sha256"]))

    session = start("controls_q")
    try:
        assert session.latest["help_page"] == 0
        session.wait(.30)
        assert session.latest["state"]["remaining_s"] == 600
        r = session.edge(" ", "shutter")
        assert r["help_page"] == 1
        r = session.edge("p", "pause")
        assert r["help_page"] is None
        session.wait(.30)
        assert session.latest["state"]["remaining_s"] < 600
        checks.append(dict(control="SPACE help page; P starts", passed=True))
        axes = [("w", "forward", 1), ("s", "forward", -1),
                ("a", "strafe", -1), ("d", "strafe", 1),
                ("j", "turn", -1), ("l", "turn", 1),
                ("i", "look", 1), ("k", "look", -1),
                ("\x1b[D", "turn", -1), ("\x1b[C", "turn", 1),
                ("\x1b[A", "look", 1), ("\x1b[B", "look", -1)]
        for key, axis, sign in axes:
            session.wait(.30)
            before = session.latest["player"]
            session.send(key)
            observed = None
            for _ in range(20):
                r = session.next()
                if r["actions"][axis] == sign:
                    observed = r
                    break
            assert observed is not None, (key, "action not observed")
            session.wait(.22)
            after = session.latest["player"]
            if axis in ("forward", "strafe"):
                dx = after["feet"]["x"]-before["feet"]["x"]
                dz = after["feet"]["z"]-before["feet"]["z"]
                yaw = before["yaw"]
                delta = dx*math.sin(yaw)+dz*math.cos(yaw) if axis == "forward" else dx*math.cos(yaw)-dz*math.sin(yaw)
            elif axis == "turn":
                delta = (after["yaw"]-before["yaw"]+math.pi) % math.tau-math.pi
            else:
                delta = after["pitch"]-before["pitch"]
            assert delta*sign > .001, (key, before, after)
            checks.append(dict(control=repr(key), axis=axis, sign=sign, delta=delta,
                               action_frame=observed["frame"], before=before, after=after, passed=True))
        session.wait(.30)
        r = session.edge("h", "help")
        assert r["help_page"] == 0
        frozen, player = r["state"], r["player"]
        session.send("w")
        session.wait(.35)
        assert session.latest["state"] == frozen and session.latest["player"] == player
        r = session.edge("h", "help")
        assert r["help_page"] is None
        session.wait(.30)
        r = session.edge("p", "pause")
        assert r["paused"]
        frozen, player = r["state"], r["player"]
        session.send("wl ")
        session.wait(.35)
        assert session.latest["state"] == frozen and session.latest["player"] == player
        r = session.edge("p", "pause")
        assert not r["paused"]
        checks.append(dict(control="H help toggle and freeze; P pause/resume and freeze", passed=True))
        session.wait(.30)
        r = session.edge("e", "interact")
        assert "rejected" in " ".join(r["messages"])
        session.wait(.30)
        r = session.edge("r", "restart")
        assert r["state"]["remaining_s"] == 600 and r["state"]["score"] == 0
        session.wait(.30)
        r = session.edge("n", "new_seed")
        assert r["seed"] == 12 and not r["state"]["photos"]
        checks.append(dict(control="E early submission rejected; R reset; N seed+1", passed=True))
        finish(session, "controls_q", "q", 0)
    finally:
        if session.process.poll() is None:
            session.close()
    for case, key, expected in [("escape_256", "\x1b", 0), ("ctrl_c", "\x03", 130), ("sigterm", None, 143)]:
        session = start(case, color="256" if case == "escape_256" else "truecolor")
        try:
            session.edge("h", "help")
            session.send("wli")
            session.wait(.35)
            if case == "sigterm":
                session.events.append(dict(signal="SIGTERM", monotonic=time.monotonic()))
                session.process.send_signal(signal.SIGTERM)
            finish(session, case, key, expected)
            if case == "escape_256":
                assert b"\x1b[38;5;" in session.raw
        finally:
            if session.process.poll() is None:
                session.close()
    result = dict(passed=True, command=sys.argv, repo=str(repo), launcher=prefix, cwd=str(cwd),
                  checks=checks, lifecycle=cases,
                  limitations="Scripted keyboard input and real Linux PTY frames, not subjective human playtesting or physical-emulator screenshots. No Windows validation.")
    (output/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
