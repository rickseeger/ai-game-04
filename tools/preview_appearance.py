"""Deterministic material atlas, NOT a camera renderer or finished 3D city."""
import argparse
from dataclasses import asdict
import hashlib
import html
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from citywalk.appearance import FacadeAppearance, PALETTES
from citywalk.contracts import RayHit, Vec3
from citywalk.spatial import CityGenerator

LABEL = "COMPONENT PREVIEW ONLY - unprojected material samples, not a finished 3D city"


def generate(seed=11):
    city = CityGenerator().generate(seed).city
    appearance = FacadeAppearance()
    landmarks = {l.building_id: l for l in city.landmarks}
    cells, lookup, panels = [], {}, []

    def panel(name, building, face, origin, du, dv, columns, rows):
        normal = {"south": Vec3(0, 0, -1), "roof": Vec3(0, 1, 0),
                  "ground": Vec3(0, 1, 0)}[face]
        data = []
        for row in range(rows):
            line = []
            for column in range(columns):
                p = Vec3(*(a+column*b+row*c for a, b, c in zip(
                    (origin.x, origin.y, origin.z), (du.x, du.y, du.z), (dv.x, dv.y, dv.z))))
                cell = appearance.sample(city, RayHit(1, p, normal, face, building.id if building else None))
                if cell not in lookup:
                    lookup[cell] = len(cells)
                    cells.append(cell)
                line.append(lookup[cell])
            data.append(line)
        panels.append({"name": name, "building": asdict(building) if building else None,
                       "landmark": asdict(landmarks[building.id]) if building and building.id in landmarks else None,
                       "face": face, "origin": asdict(origin), "column_step": asdict(du),
                       "row_step": asdict(dv), "columns": columns, "rows": rows, "cells": data})

    for style in PALETTES:
        selected = [next(b for b in city.buildings if b.style == style and b.id not in landmarks),
                    next(b for b in city.buildings if b.style == style and b.id in landmarks)]
        for b in selected:
            r = b.footprint
            name = landmarks[b.id].name if b.id in landmarks else b.id
            # Full elevation plus higher resolution street-level detail.
            panel(name+" / full south elevation", b, "south", Vec3(r.xmin+.25, b.height-.9, r.zmin),
                  Vec3(.5, 0, 0), Vec3(0, -1, 0), math.ceil((r.xmax-r.xmin)/.5), math.ceil(b.height))
            panel(name+" / entry detail", b, "south", Vec3((r.xmin+r.xmax)/2-4, 5.875, r.zmin),
                  Vec3(.25, 0, 0), Vec3(0, -.25, 0), 32, 24)
            panel(name+" / roofline detail", b, "south", Vec3(r.xmin+.25, b.height-.125, r.zmin),
                  Vec3(.5, 0, 0), Vec3(0, -.25, 0), math.ceil((r.xmax-r.xmin)/.5), 24)
            panel(name+" / roof plan", b, "roof", Vec3(r.xmin+.25, b.height, r.zmin+.25),
                  Vec3(.5, 0, 0), Vec3(0, 0, .5), math.ceil((r.xmax-r.xmin)/.5), math.ceil((r.zmax-r.zmin)/.5))
            if b.id in landmarks:
                panel(name+" / emblem detail", b, "south", Vec3((r.xmin+r.xmax)/2-4.875, b.height/2+3.875, r.zmin),
                      Vec3(.25, 0, 0), Vec3(0, -.25, 0), 40, 32)
    panel("Ground at depot", None, "ground", Vec3(-6, 0, -3),
          Vec3(.5, 0, 0), Vec3(0, 0, .5), 24, 12)
    panel("Ground boundary material (flat stripe, not a geometric rail)", None, "ground",
          Vec3(237, 0, -3), Vec3(.25, 0, 0), Vec3(0, 0, .5), 12, 12)
    data = {"version": 1, "label": LABEL, "seed": seed,
            "coordinates": "metres; point=origin+column*column_step+row*row_step; no projection or lighting",
            "palettes": {key: asdict(value) for key, value in PALETTES.items()},
            "cell_table": [asdict(cell) for cell in cells], "panels": panels}
    text = [LABEL, "Seed: "+str(seed), "Exact world coordinates and RGB in atlas.json; color preview in atlas.html."]
    page = ["<!doctype html><html lang=en><meta charset=utf-8><title>Appearance component atlas</title>",
            "<style>body{background:#0c1026;color:#d8dae5;font:14px monospace}pre{font:12px/14px monospace;white-space:pre}section{display:inline-block;vertical-align:top;margin:12px}h2{font-size:14px}p{max-width:75ch}</style>",
            "<h1>"+LABEL+"</h1><p>Seed "+str(seed)+". Orthographic facade/roof swatches only. No camera, perspective, lighting, fog, movement or gameplay. Physical sample spacing varies by labeled panel; see atlas.json for coordinates. Glyphs remain printable ASCII.</p>"]
    page.append("<style>"+"".join(".c"+str(i)+"{color:rgb"+str(c.fg)+";background:rgb"+str(c.bg)+"}" for i, c in enumerate(cells))+"</style>")
    page.append("<h2>District palette: wall / trim / window / dark / accent</h2>")
    for key, palette in PALETTES.items():
        swatches = []
        for role in ("wall", "trim", "window", "dark", "accent"):
            rgb = getattr(palette, role)
            swatches.append("<span style='background:rgb"+str(rgb)+";color:white'> "+role+" </span>")
        page.append("<p>"+palette.district+" ("+key+") "+" ".join(swatches)+"</p>")
    for p in panels:
        text.extend(["", p["name"], "origin="+str(p["origin"])+" column_step="+str(p["column_step"])+" row_step="+str(p["row_step"])])
        page.append("<section><h2>"+html.escape(p["name"])+"</h2><pre>")
        for line in p["cells"]:
            text.append("".join(cells[i].glyph for i in line))
            runs = []
            for i in line:
                if runs and runs[-1][0] == i:
                    runs[-1][1] += cells[i].glyph
                else:
                    runs.append([i, cells[i].glyph])
            page.append("".join("<span class=c"+str(i)+">"+html.escape(glyphs)+"</span>" for i, glyphs in runs)+"\n")
        page.append("</pre></section>")
    page.append("</html>\n")
    return {"atlas.json": json.dumps(data, sort_keys=True, separators=(",", ":"))+"\n",
            "atlas.txt": "\n".join(text)+"\n", "atlas.html": "".join(page)}


def main():
    parser = argparse.ArgumentParser(description=LABEL)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--output", type=Path, default=ROOT/"docs"/"appearance-fixtures")
    parser.add_argument("--check", action="store_true", help="compare existing fixtures without writing")
    args = parser.parse_args()
    artifacts = generate(args.seed)
    if not args.check:
        args.output.mkdir(parents=True, exist_ok=True)
    for name, text in artifacts.items():
        path, raw = args.output/name, text.encode("utf-8")
        if args.check:
            if not path.exists() or path.read_bytes() != raw:
                raise SystemExit("fixture mismatch: "+str(path))
        else:
            path.write_bytes(raw)
        print(name+" bytes="+str(len(raw))+" sha256="+hashlib.sha256(raw).hexdigest())
    data = json.loads(artifacts["atlas.json"])
    print("panels="+str(len(data["panels"]))+" sampled_cells="+str(sum(p["rows"]*p["columns"] for p in data["panels"])))
    print(LABEL)


if __name__ == "__main__":
    main()
