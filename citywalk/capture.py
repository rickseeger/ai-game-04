"""Opt-in evidence sink. Observes application frames; never supplies game state."""
from dataclasses import asdict
import gzip
import hashlib
import html
import json
import math
from pathlib import Path
import platform
import subprocess
import sys


class Capture:
    def __init__(self, path, args):
        path.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.trace = (path / "trace.jsonl").open("w", buffering=1)
        self.frames = gzip.open(path / "frames.jsonl.gz", "wt", encoding="utf-8")
        self.ansi = gzip.open(path / "checkpoints.ansi.gz", "wb")
        self.plain = (path / "frames.txt").open("w")
        self.html = (path / "frames.html").open("w")
        self.html.write("<!doctype html><meta charset=utf-8><title>Actual Lantern Survey frames</title><body style=background:#090c1e;color:#eee><p>Actual application checkpoints; not independent beauty or fun validation.</p>")
        self.last_key, self.seen, self.last_ansi = None, set(), ""
        self.timings = []
        root = Path(__file__).resolve().parent
        def git(*args):
            try:
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
            except (OSError, subprocess.CalledProcessError):
                return None
        self.meta = {"schema": 1, "source_sha": git("rev-parse", "HEAD"),
                     "dirty": bool(git("status", "--porcelain")),
                     "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))},
                     "platform": platform.platform(), "python": sys.version,
                     "cpu": platform.processor(), "argv": sys.argv, "seed": args.seed,
                     "source_directory": str(root), "executable": sys.executable,
                     "sys_path": sys.path,
                     "distribution": json.loads((root.parent / "BUILD.json").read_text())
                         if (root.parent / "BUILD.json").is_file() else None,
                     "cell_aspect": args.cell_aspect, "color": args.color,
                     "clock": "time.monotonic; real elapsed, movement capped at 0.10s; no accelerated clock",
                     "limitations": "Scripted PTY execution is not an independent aesthetic/enjoyment assessment or Windows runtime verification."}
        (path / "metadata.json").write_text(json.dumps(self.meta, indent=2)+"\n")

    def attach(self, terminal):
        sink, original = self, terminal.backend.output
        class Tee:
            def write(self, text):
                sink.last_ansi += text
                return original.write(text)
            def flush(self):
                return original.flush()
            def fileno(self):
                return original.fileno()
            def isatty(self):
                return original.isatty()
        terminal.backend.output = Tee()

    def event(self, record):
        self.trace.write(json.dumps(record, allow_nan=False)+"\n")

    def record(self, index, now, dt, actions, size, app, frame, hud, render_ms, present_ms):
        record = {"frame": index, "monotonic": now, "dt_s": dt, "size": size,
                  "actions": asdict(actions), "seed": app.world.city.seed,
                  "player": asdict(app.player), "state": asdict(app.state),
                  "paused": app.paused, "help_page": app.help_page, "small": app.small,
                  "blocked": app.blocked, "messages": app.messages, "hud": hud,
                  "sightings": [asdict(s) for s in app.sightings],
                  "render_ms": render_ms, "present_ms": present_ms}
        key = (size, app.world.city.seed, app.paused, app.help_page, app.state.phase, app.state.photos)
        labels = []
        if key != self.last_key:
            labels.append("state-change")
        for label, active in (("walking", actions.forward or actions.strafe), ("turning", actions.turn),
                              ("looking", actions.look), ("collision", app.blocked),
                              ("restart", actions.restart), ("submission", actions.interact)):
            if active and label not in self.seen:
                labels.append(label)
                self.seen.add(label)
        if labels:
            record["checkpoint"] = labels
            full = {**record, "camera": asdict(__import__("citywalk.camera", fromlist=["camera_from_player"]).camera_from_player(app.player)),
                    "viewport": {"columns": frame.columns, "rows": frame.rows, "cell_aspect": app.cell_aspect},
                    "cells": [[c.glyph, c.fg, c.bg] for c in frame.cells],
                    "depth": [d if math.isfinite(d) else None for d in frame.depth]}
            self.frames.write(json.dumps(full, allow_nan=False)+"\n")
            self.ansi.write(self.last_ansi.encode("utf-8"))
            title = f"Frame {index}: {labels}, {size}, seed {app.world.city.seed}"
            self.plain.write(title+"\n")
            self.html.write("<h2>"+html.escape(title)+"</h2><pre style='font:14px/28px monospace;white-space:pre'>")
            for row in range(frame.rows):
                cells = frame.cells[row*frame.columns:(row+1)*frame.columns]
                self.plain.write("".join(c.glyph for c in cells)+"\n")
                for c in cells:
                    self.html.write(f"<span style='color:rgb{c.fg};background:rgb{c.bg}'>{html.escape(c.glyph)}</span>")
                self.html.write("\n")
            self.plain.write("\n".join(hud)+"\n\n")
            self.html.write(html.escape("\n".join(hud))+"</pre>")
        self.last_ansi = ""
        self.last_key = key
        self.timings.append((size, render_ms, present_ms))
        self.event(record)  # flushed after actual present/checkpoint writes

    def close(self):
        self.trace.close()
        self.frames.close()
        self.ansi.close()
        self.plain.close()
        self.html.write("</body>")
        self.html.close()
        groups = {}
        for size, render, present in self.timings:
            groups.setdefault(f"{size[0]}x{size[1]}", []).append((render,present))
        import statistics
        report = {}
        for size, pairs in groups.items():
            report[size] = {"frames": len(pairs)}
            for j, name in enumerate(("render", "present")):
                samples = sorted(p[j] for p in pairs)
                report[size][name+"_median_ms"] = statistics.median(samples)
                report[size][name+"_p95_ms"] = samples[math.ceil(.95*len(samples))-1]
                report[size][name+"_max_ms"] = max(samples)
        (self.path / "timing.json").write_text(json.dumps({"all_frames_including_cold_and_paused": report,
            "raw_samples": "trace.jsonl", "present_includes": "HUD/ANSI encode, output write and flush; PTY reader drains concurrently; capture IO excluded"}, indent=2)+"\n")
