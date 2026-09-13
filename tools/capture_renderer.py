"""Generate real headless renderer frames, optionally benchmark; stdlib only."""
import argparse
from dataclasses import asdict, replace
import hashlib
import html
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from citywalk.appearance import FacadeAppearance
from citywalk.camera import Perspective
from citywalk.contracts import Camera, Vec3, Viewport
from citywalk.rendering import CityRenderer
from citywalk.spatial import CityGenerator

LABEL = "Actual city renderer frames - no input, HUD or gameplay"
SIZES = ((80, 20), (100, 32), (120, 40))


def scenes(world):
    clock = world.city.landmarks[2]
    # City metadata is used only to choose safe diagnostic poses, never to
    # bypass the Renderer/Spatial/Appearance contracts in scene rendering.
    lanes = sorted((s for s in world.public_spaces if s.kind == "lane" and
                    s.id.startswith("lane-x")),
                   key=lambda s: (abs((s.rect.xmin+s.rect.xmax)/2)+
                                  abs((s.rect.zmin+s.rect.zmax)/2), s.id))
    lane = lanes[0]
    r = lane.rect
    eye = Vec3((r.xmin+r.xmax)/2, 1.7, (r.zmin+r.zmax)/2)
    result = [
        ("broad_vista", "Open Civic plaza, oblique northward vista",
         Camera(clock.viewpoint, yaw=-.28, pitch=.30)),
        ("avenue_east", "Depot avenue facing east; converging pavement and corners",
         Camera(Vec3(world.city.depot.x, 1.7, world.city.depot.z), math.pi/2, .12)),
        ("narrow_street", "6 m through-lane "+lane.id+", northward", Camera(eye, pitch=.12)),
        ("narrow_reverse", "Same 6 m lane, opposite heading and higher gaze",
         Camera(eye, math.pi, .35)),
    ]
    for landmark in world.city.landmarks:
        result.append(("landmark_"+landmark.id, landmark.name+" from validated viewpoint",
                       Camera(landmark.viewpoint, landmark.view_yaw, landmark.view_pitch)))
    for _, _, camera in result:
        if camera.eye.y != 1.7 or not world.walkable(Vec3(camera.eye.x, 0, camera.eye.z), .3):
            raise ValueError("unsafe or non-street-level capture pose")
    return tuple(result)


def frame_data(frame):
    table, indices, lookup = [], [], {}
    for cell in frame.cells:
        if cell not in lookup:
            lookup[cell] = len(table)
            table.append(asdict(cell))
        indices.append(lookup[cell])
    return {"columns": frame.columns, "rows": frame.rows, "cell_table": table,
            "cells": indices, "depth_m": [d if math.isfinite(d) else None for d in frame.depth]}


def generate(seed=11):
    world, renderer, appearance = CityGenerator().generate(seed), CityRenderer(Perspective()), FacadeAppearance()
    panels, text = [], [LABEL, "RGB and original-eye ray depths in frames.json. Sky depth is null."]
    page = ["<!doctype html><html lang=en><meta charset=utf-8><title>Renderer captures</title>",
            "<style>body{background:#090c1e;color:#dedfeb;font:14px monospace}section{margin:28px 0}h2{font-size:16px}.frame{white-space:pre;font:14px/16px monospace}.cell{display:inline-block;width:8px;height:16px;text-align:center;overflow:hidden;vertical-align:top}p{max-width:100ch}</style>",
            "<h1>"+LABEL+"</h1><p>Seed "+str(seed)+". Each cell is an actual CityRenderer.render result. Fixed 8x16 CSS cells reproduce the 0.5 physical aspect. No illustrated skyline, post-render retouching, external assets or JavaScript. These are component captures, not a terminal playtest.</p>"]
    for columns, rows in SIZES:
        viewport = Viewport(columns, rows)
        for name, description, camera in scenes(world):
            frame = renderer.render(world, appearance, camera, viewport)
            panel = {"name": name, "description": description, "camera": asdict(camera),
                     "viewport": asdict(viewport), "frame": frame_data(frame),
                     "sightings": [asdict(s) for s in renderer.sightings(world, camera, viewport)]}
            panels.append(panel)
            title = f"{name} / {columns}x{rows} scene ({columns}x{rows+4} terminal)"
            text.extend(["", title, description, "camera="+json.dumps(asdict(camera), sort_keys=True)])
            page.append("<section><h2>"+html.escape(title)+"</h2><p>"+html.escape(description)+"</p><div class=frame>")
            for row in range(rows):
                cells = frame.cells[row*columns:(row+1)*columns]
                text.append("".join(c.glyph for c in cells))
                page.append("".join("<span class=cell style=\"color:rgb"+str(c.fg)+";background:rgb"+str(c.bg)+"\">"+html.escape(c.glyph)+"</span>" for c in cells)+"\n")
            page.append("</div></section>")
    page.append("</html>\n")
    sources = ("citywalk/contracts.py", "citywalk/spatial.py", "citywalk/appearance.py",
               "citywalk/camera.py", "citywalk/rendering.py", "tools/capture_renderer.py")
    data = {"version": 1, "label": LABEL, "seed": seed,
            "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
            "depth_convention": "original-eye normalized-ray metres; null = sky", "panels": panels}
    return {"frames.json": json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n",
            "frames.txt": "\n".join(text)+"\n", "frames.html": "".join(page)}


def benchmark(seed, count):
    if count < 1:
        raise ValueError("benchmark count must be positive")
    world, renderer, appearance = CityGenerator().generate(seed), CityRenderer(Perspective()), FacadeAppearance()
    selected = tuple(s for s in scenes(world) if s[0] in ("broad_vista", "narrow_street", "landmark_sight-2"))
    results = []
    for columns, rows in SIZES:
        viewport = Viewport(columns, rows)
        for _ in range(3):
            for _, _, camera in selected:
                renderer.render(world, appearance, camera, viewport)
        timings, by_scene = [], {name: [] for name, _, _ in selected}
        for i in range(count):
            name, _, camera = selected[i % len(selected)]
            # Cycle distinct poses so every measured frame rebuilds the ray
            # geometry: not a cached-frame or stationary-camera speed claim.
            start = time.perf_counter_ns()
            frame = renderer.render(world, appearance, camera, viewport)
            ms = (time.perf_counter_ns()-start)/1e6
            timings.append(ms)
            by_scene[name].append(ms)
            assert len(frame.cells) == columns*rows
        def stats(values):
            return {"count": len(values), "median_ms": statistics.median(values),
                    "p95_ms": sorted(values)[math.ceil(.95*len(values))-1], "max_ms": max(values)}
        results.append({"viewport": asdict(viewport), **stats(timings),
                        "per_scene": {name: stats(values) for name, values in by_scene.items() if values},
                        "samples_ms": timings})
    cpu = "unavailable"
    path = Path("/proc/cpuinfo")
    if path.exists():
        cpu = next((line.split(":", 1)[1].strip() for line in path.read_text().splitlines()
                    if line.startswith("model name")), cpu)
    return {"seed": seed, "python": sys.version, "platform": platform.platform(),
            "cpu": cpu, "logical_cpus": os.cpu_count(), "timer": "perf_counter_ns",
            "method": "9 warmups per size, cycling 3 poses; full render including geometry rebuild, spatial queries, materials, lighting, Frame allocation; excludes generation, sightings, encoding and terminal I/O",
            "target_100x32": {"median_ms_max": 50, "p95_ms_max": 100}, "results": results}


def main():
    parser = argparse.ArgumentParser(description=LABEL)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--output", type=Path, default=ROOT/"docs"/"renderer-frames")
    parser.add_argument("--check", action="store_true", help="byte-compare frames without writing")
    parser.add_argument("--benchmark", type=int, metavar="FRAMES_PER_SIZE")
    args = parser.parse_args()
    if args.check and args.benchmark is not None:
        parser.error("--check is read-only; omit --benchmark")
    if args.benchmark is not None and args.benchmark < 1:
        parser.error("--benchmark must be positive")
    artifacts = generate(args.seed)
    if not args.check:
        args.output.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        path, raw = args.output/name, content.encode("utf-8")
        if args.check:
            if not path.exists() or path.read_bytes() != raw:
                raise SystemExit("fixture mismatch: "+str(path))
        else:
            path.write_bytes(raw)
        print(name+" bytes="+str(len(raw))+" sha256="+hashlib.sha256(raw).hexdigest())
    print("actual_frames="+str(len(json.loads(artifacts["frames.json"])["panels"])))
    if args.benchmark is not None:
        data = benchmark(args.seed, args.benchmark)
        (args.output/"performance.json").write_text(json.dumps(data, indent=2)+"\n")
        for result in data["results"]:
            print(json.dumps({k: result[k] for k in ("viewport", "count", "median_ms", "p95_ms", "max_ms")}))


if __name__ == "__main__":
    main()
