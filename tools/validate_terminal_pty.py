#!/usr/bin/env python3
"""Real Linux controlling PTY tests, captured bytes and exact termios readback.

IPC only schedules polls/exception; advertised keys travel through the real PTY.
The small VT state checker is not a GUI emulator or Windows runtime test.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import re
import select
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def child(fd):
    from citywalk.terminal import open_terminal, TerminalInterrupted
    from citywalk.contracts import Cell, Frame
    channel = socket.socket(fileno=fd).makefile("rw", buffering=1)
    def send(value):
        channel.write(json.dumps(value) + "\n")
        channel.flush()
    result = {"termination": "unexpected"}
    previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGTSTP)}
    try:
        with open_terminal() as term:
            frame = Frame(2, 2, (Cell("#", (255, 95, 0), (0, 0, 30)),)*4, (1.0,)*4)
            term.present(frame, ("PTY component probe - not a game",))
            send({"ready": True, "size": term.size()})
            for line in channel:
                command = json.loads(line)
                if command["op"] == "poll":
                    start = time.monotonic()
                    actions = term.poll(start)
                    send({"actions": asdict(actions), "poll_seconds": time.monotonic()-start})
                    if actions.quit:
                        result = {"termination": "quit"}
                        break
                elif command["op"] == "present":
                    term.present(frame, ("resize test",))
                    send({"size": term.size()})
                elif command["op"] == "wait":
                    start, cpu = time.monotonic(), time.process_time()
                    term.wait(.06)
                    send({"elapsed": time.monotonic()-start, "cpu": time.process_time()-cpu})
                elif command["op"] == "exception":
                    raise RuntimeError("injected PTY rendering exception")
    except TerminalInterrupted as exc:
        result = {"termination": "interrupt", "signal": exc.signum}
    except RuntimeError as exc:
        result = {"termination": "exception", "message": str(exc)}
    result["handlers_restored"] = previous == {s: signal.getsignal(s) for s in previous}
    send(result)


def vt_state(data, initially_visible=True):
    """Track exactly the display controls used here, separately from adapter."""
    visible, alternate, sgr = initially_visible, False, "0"
    saved = initially_visible
    entered = hidden = reset = left = False
    for match in re.finditer(rb"\x1b\[([?0-9;]*)([A-Za-z])", data):
        params, final = match.group(1).decode(), match.group(2).decode()
        if params == "?25":
            if final == "s": saved = visible
            if final == "l": visible, hidden = False, True
            if final == "h": visible = True
            if final == "r": visible = saved
        elif params == "?1049":
            if final == "h": alternate, entered = True, True
            if final == "l": alternate, left = False, True
        elif final == "m":
            sgr = params or "0"
            reset |= sgr == "0"
    assert entered and hidden and reset and left
    assert visible == initially_visible and not alternate and sgr == "0"
    return {"cursor_visible": visible, "alternate_screen": alternate, "sgr": sgr,
            "entry_hide_reset_exit_observed": True}


def run_case(case, output):
    import fcntl
    import pty
    import struct
    import termios
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 36, 100, 0, 0))
    before = termios.tcgetattr(slave)
    parent, worker = socket.socketpair()
    parent.settimeout(5)
    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--child", str(worker.fileno())],
                               stdin=slave, stdout=slave, stderr=slave, pass_fds=(worker.fileno(),),
                               preexec_fn=controlling_terminal,
                               env={**os.environ, "TERM": "xterm-256color"})
    worker.close()
    channel = parent.makefile("rw", buffering=1)
    events, captured = [], bytearray()
    def receive():
        line = channel.readline()
        if not line:
            raise AssertionError("child exited without evidence")
        value = json.loads(line)
        events.append({"received": value})
        return value
    def request(op):
        events.append({"command": op})
        channel.write(json.dumps({"op": op})+"\n")
        channel.flush()
        return receive()
    def inject(data):
        events.append({"injected_hex": data.hex(), "monotonic": time.monotonic()})
        os.write(master, data)
    try:
        assert receive() == {"ready": True, "size": [100, 36]}
        active = termios.tcgetattr(slave)
        assert active != before
        assert not active[3] & (termios.ICANON | termios.ECHO)
        assert active[3] & termios.ISIG
        idle = request("poll")
        assert not any(idle["actions"].values())
        assert idle["poll_seconds"] < .05
        waited = request("wait")
        assert .05 <= waited["elapsed"] < .5
        assert waited["cpu"] < .03
        if case == "normal":
            # Every ordinary advertised control, independently through os.read.
            mappings = {"w": ("forward", 1), "s": ("forward", -1), "a": ("strafe", -1),
                        "d": ("strafe", 1), "j": ("turn", -1), "l": ("turn", 1),
                        "i": ("look", 1), "k": ("look", -1), " ": ("shutter", True),
                        "e": ("interact", True), "p": ("pause", True), "h": ("help", True),
                        "?": ("help", True), "r": ("restart", True), "n": ("new_seed", True)}
            for key, (field, value) in mappings.items():
                inject(key.encode())
                assert request("poll")["actions"][field] == value, key
            for sequence, field, value in ((b"\x1b[D", "turn", -1), (b"\x1b[C", "turn", 1),
                                           (b"\x1b[A", "look", 1), (b"\x1b[B", "look", -1)):
                inject(sequence[:2])
                assert not request("poll")["actions"]["quit"]
                inject(sequence[2:])
                assert request("poll")["actions"][field] == value
            inject(b"\x1b[99~")
            assert not request("poll")["actions"]["quit"]
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 10, 40, 0, 0))
            assert request("present")["size"] == [40, 10]
            inject(b"w ")
            small = request("poll")["actions"]
            assert not small["forward"] and not small["shutter"]
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            assert request("present")["size"] == [80, 24]
            inject(b"q")
            assert request("poll")["actions"]["quit"]
            ending = receive()
            assert ending["termination"] == "quit"
        elif case == "escape":
            inject(b"\x1b")
            assert not request("poll")["actions"]["quit"]
            time.sleep(.06)  # deliberately cross the documented ESC deadline
            assert request("poll")["actions"]["quit"]
            ending = receive()
            assert ending["termination"] == "quit"
        elif case == "exception":
            ending = request("exception")
            assert ending["termination"] == "exception"
        elif case == "ctrl_c":
            inject(b"\x03")  # kernel ISIG -> foreground process SIGINT
            ending = receive()
            assert ending["signal"] == signal.SIGINT
        else:
            sig = {"sigterm": signal.SIGTERM, "sigquit": signal.SIGQUIT, "sigtstp": signal.SIGTSTP}[case]
            events.append({"sent_signal": signal.Signals(sig).name})
            process.send_signal(sig)
            ending = receive()
            assert ending["signal"] == sig
        assert ending["handlers_restored"]
        assert process.wait(timeout=5) == 0
        after = termios.tcgetattr(slave)
        assert before == after, "termios not exactly restored"
        while select.select([master], [], [], .05)[0]:
            captured.extend(os.read(master, 65536))
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{case}.ansi").write_bytes(captured)
        state = vt_state(captured)
        hidden_state = vt_state(captured, initially_visible=False)
        if case == "normal":
            assert b"Resize to 80x24" in captured
        def attrs(value):
            return [item if not isinstance(item, list) else
                    [v.hex() if isinstance(v, bytes) else v for v in item] for item in value]
        report = {"case": case, "passed": True, "exit_code": process.returncode,
                  "termios_before": attrs(before), "termios_active": attrs(active), "termios_after": attrs(after),
                  "termios_exactly_restored": before == after, "events": events,
                  "display_state_from_captured_VT": state,
                  "initially_hidden_cursor_VT_model": hidden_state,
                  "display_limit": "PTY captures real bytes, not a visual emulator. VT mode interpretation checked separately; no physical emulator query.",
                  "transcript": f"{case}.ansi"}
        (output / f"{case}.json").write_text(json.dumps(report, indent=2)+"\n")
        return {"case": case, "passed": True, "termios_exactly_restored": True,
                "termination": ending, "idle_poll_seconds": idle["poll_seconds"], "idle_wait": waited}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        channel.close()
        parent.close()
        os.close(master)
        os.close(slave)


def run_probe(case, output):
    """Exercise the shipped interactive probe itself, including full-width rows."""
    import fcntl
    import pty
    import struct
    import termios
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    before = termios.tcgetattr(slave)
    report_path = output / f"probe_{case}.json"
    command = [sys.executable, str(ROOT / "tools/probe_terminal.py"), "--output", str(report_path)]
    if case == "exception":
        command += ["--raise-after", "0.12"]
    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                               preexec_fn=controlling_terminal,
                               env={**os.environ, "TERM": "xterm-256color"})
    data, injected = bytearray(), False
    deadline = time.monotonic()+5
    try:
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise AssertionError("interactive probe timed out")
            if select.select([master], [], [], .1)[0]:
                data.extend(os.read(master, 65536))
            if case == "normal" and not injected and b"\x1b[?25l" in data:
                os.write(master, b"w\x1b[D q")
                injected = True
        while select.select([master], [], [], .05)[0]:
            data.extend(os.read(master, 65536))
        assert process.returncode == 0, data.decode(errors="replace")
        assert termios.tcgetattr(slave) == before
        report = json.loads(report_path.read_text())
        assert report["modes_exactly_restored"]
        assert report["termination"] == ("normal_quit" if case == "normal" else "exception")
        vt_state(data)
        (output / f"probe_{case}.ansi").write_bytes(data)
        return {"case": "probe_"+case, "passed": True, "exit_code": process.returncode,
                "termios_exactly_restored": True, "command": command}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", type=int)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/terminal-pty")
    args = parser.parse_args()
    if args.child is not None:
        child(args.child)
        return
    if sys.platform != "linux":
        parser.error("Real Linux PTY validation requires Linux (not a Windows mock).")
    summary = {"platform": platform.platform(), "python": sys.version,
               "cases": [run_case(case, args.output) for case in ("normal", "escape", "exception", "ctrl_c", "sigterm", "sigquit", "sigtstp")],
               "interactive_probe_cases": [run_probe(case, args.output) for case in ("normal", "exception")],
               "native_windows_validated": False}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
