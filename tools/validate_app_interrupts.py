"""Actual application PTY cleanup on Escape, Ctrl-C, SIGTERM and render failure."""
import json
from pathlib import Path
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.validate_app_pty import Session

# Fault injection replaces only rendering on the fourth call. Everything else,
# including the real app main/context manager, is the shipped application.
FAULT = """
from citywalk.app import Application, main
original = Application.render
calls = 0
def failing(self, size):
    global calls
    calls += 1
    if calls == 4:
        raise RuntimeError("deliberate application render failure")
    return original(self, size)
Application.render = failing
raise SystemExit(main())
"""


def main():
    output=ROOT/"docs/app-lifecycle"
    results=[]
    for case in ("escape_256","ctrl_c","sigterm","render_exception"):
        session=Session(output/case,color="256" if case=="escape_256" else "truecolor",
                        launch_code=FAULT if case=="render_exception" else None)
        if case=="render_exception":
            deadline=time.monotonic()+10
            while session.process.poll() is None and time.monotonic()<deadline:
                session.drain()
            report=session.close(key=None)
            assert report["exit_code"]==1
            assert b"deliberate application render failure" in session.raw
        elif case=="sigterm":
            session.wait(.25)
            session.events.append({"signal":"SIGTERM","monotonic":time.monotonic()})
            session.process.send_signal(signal.SIGTERM)
            report=session.close(key=None)
            assert report["exit_code"]==143
        else:
            session.wait(.25)
            report=session.close(key="\x1b" if case=="escape_256" else "\x03")
            assert report["exit_code"]==(0 if case=="escape_256" else 130)
        results.append({"case":case,"passed":True,"exit_code":report["exit_code"],
                        "termios_exactly_restored":report["termios_exactly_restored"],
                        "transcript_sha256":report["raw_transcript_sha256"]})
    (output/"summary.json").write_text(json.dumps(results,indent=2)+"\n")
    print(json.dumps(results,indent=2))


if __name__=="__main__":
    main()
