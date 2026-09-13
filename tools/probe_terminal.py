#!/usr/bin/env python3
"""Interactive component probe on the host OS, not a complete city/game.

Writes genuine input and mode snapshots, never manufactures passed controls.
Windows evidence is native only when this actually runs in a Windows console.
"""
import argparse
from dataclasses import asdict
import json
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from citywalk.contracts import Actions, Cell, Frame
from citywalk.terminal import open_terminal, TerminalInterrupted, TerminalUnavailable, WindowsConsole


def snapshot():
    if os.name == "nt":
        console = WindowsConsole(sys.stdin, sys.stdout)
        cursor = console.get_cursor()
        return {"input_mode": console.get_mode(False), "output_mode": console.get_mode(True),
                "cursor": {"size": cursor.size, "visible": bool(cursor.visible)},
                "attributes": console.info().attributes}
    import termios
    value = termios.tcgetattr(sys.stdin.fileno())
    return [item if not isinstance(item, list) else
            [v.hex() if isinstance(v, bytes) else v for v in item] for item in value]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raise-after", type=float, default=0, help="inject exception after this many seconds")
    parser.add_argument("--color", choices=("truecolor", "256"), default="truecolor")
    args = parser.parse_args()
    report = {"platform": platform.platform(), "python": sys.version, "native_windows": os.name == "nt",
              "events": [], "sizes": [], "scope": "terminal component, NOT game/delivery approval"}
    report["source_sha"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report["source_dirty"] = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout)
    report["source_sha256"] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                               for name in ("citywalk/terminal.py", "citywalk/contracts.py", "tools/probe_terminal.py")}
    report["source_note"] = "source_sha is checkout HEAD; hashes identify executed working files when dirty. Output inside checkout itself may make it dirty."
    start = time.monotonic()
    last_actions = Actions()
    code = 0
    try:
        # Factory validates redirected/unsupported terminals before these reads.
        terminal = open_terminal(color=args.color)
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise TerminalUnavailable("Run this probe interactively in a real terminal, not a pipe.")
        report["before"] = snapshot()
        with terminal as term:
            report["active"] = snapshot()
            original_read = term.backend.read
            def recorded_read():
                data = original_read()
                if data:
                    report["events"].append({"elapsed": time.monotonic()-start,
                                             "raw_hex" if isinstance(data, bytes) else "windows_chars": data.hex() if isinstance(data, bytes) else data})
                return data
            term.backend.read = recorded_read
            while True:
                now = time.monotonic()
                actions = term.poll(now)
                if actions != last_actions:
                    report["events"].append({"elapsed": now-start, "actions": asdict(actions)})
                    last_actions = actions
                dimensions = term.size()
                if not report["sizes"] or report["sizes"][-1]["size"] != list(dimensions):
                    report["sizes"].append({"elapsed": now-start, "size": list(dimensions)})
                cols, rows = dimensions
                scene_cols, scene_rows = max(1, cols), max(1, rows-4)
                cells = tuple(Cell("#" if col % 8 == 0 or row % 4 == 0 else ".",
                                   (255, 175, 50), (10, 10, 45))
                              for row in range(scene_rows) for col in range(scene_cols))
                frame = Frame(scene_cols, scene_rows, cells, (1.0,)*len(cells))
                hud = ("COMPONENT PROBE (not the city/game). Exercise every key then Q/Esc; Ctrl-C separate run.",
                       "W/S walk A/D strafe J/L or Left/Right turn I/K or Up/Down look",
                       "Space shutter E submit P pause H/? help R restart N new seed; resize below/above 80x24",
                       str({key: value for key, value in asdict(actions).items() if value}))
                term.present(frame, hud)
                if actions.quit:
                    report["termination"] = "normal_quit"
                    break
                if args.raise_after and now-start >= args.raise_after:
                    raise RuntimeError("injected component exception")
                # Fixed frame cadence avoids an idle busy loop on either OS.
                time.sleep(max(0, .02-(time.monotonic()-now)))
    except TerminalInterrupted as exc:
        report["termination"], report["signal"] = "interrupted", exc.signum
    except RuntimeError as exc:
        report["termination"], report["error"] = "exception", str(exc)
        code = 0 if str(exc) == "injected component exception" else 1
    except Exception as exc:
        report["termination"], report["error"] = "os_error", str(exc)
        code = 1
    finally:
        if "before" in report:
            try:
                report["after"] = snapshot()
                report["modes_exactly_restored"] = report["before"] == report["after"]
                if not report["modes_exactly_restored"]:
                    code = 1
            except Exception as exc:
                report["snapshot_error"] = str(exc)
                code = 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+"\n")
    if "error" in report:
        print(report["error"])
    print(f"Component evidence: {args.output.resolve()} (exit {code}); inspect events for actual control coverage.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
