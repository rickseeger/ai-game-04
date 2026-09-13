"""Reproducible numeric projection fixtures, NOT rendered city screenshots."""
import argparse
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from citywalk.camera import Perspective, camera_from_player
from citywalk.contracts import Building, Camera, Player, Rect, Vec3, Viewport
from citywalk.spatial import CityGenerator


def generate():
    perspective = Perspective()
    camera = camera_from_player(Player(Vec3(0, 0, 0)))
    viewport = Viewport(100, 32)
    p = perspective.prepare(camera, viewport)

    def probe(prepared, point):
        clipped = prepared.project(point)
        raw = prepared.project_unclipped(point)
        return {"point": asdict(point), "project": asdict(clipped) if clipped else None,
                "screen_unclipped": asdict(raw) if raw else None}

    building = Building("projection-tower", Rect(-6, 20, 6, 40), 100,
                        "amber-brick", 11)
    poses = []
    for yaw, pitch in ((0, 0), (-.2, 0), (.2, 0), (0, math.pi/3)):
        c = replace(camera, yaw=yaw, pitch=pitch)
        prepared = perspective.prepare(c, viewport)
        poses.append({"camera": asdict(c), "basis": {name: asdict(getattr(prepared, name))
                                                    for name in ("right", "up", "forward")},
                      "base": probe(prepared, Vec3(0, 0, 20)),
                      "crown": probe(prepared, Vec3(0, 100, 20)),
                      "corners": [probe(prepared, Vec3(x, y, z))
                                  for x in (-6, 6) for y in (0, 100) for z in (20, 40)]})
    rays = []
    for col, row in ((0, 0), (0, 15), (49, 15), (50, 16), (99, 31)):
        d = p.ray(col, row)
        t = 20/d.z
        wall = Vec3(camera.eye.x+t*d.x, camera.eye.y+t*d.y, 20)
        rays.append({"column": col, "row": row, "unit_direction": asdict(d),
                     "ray_clip_distances_m": list(p.ray_clip_range(col, row)),
                     "wall_ray_distance_m": t, "wall_probe": probe(p, wall)})
    landmarks = []
    for seed in (11, 93, 2026):
        spatial = CityGenerator().generate(seed)
        by_id = {b.id: b for b in spatial.city.buildings}
        for l in spatial.city.landmarks:
            c = Camera(l.viewpoint, l.view_yaw, l.view_pitch)
            prepared = perspective.prepare(c, viewport)
            b = by_id[l.building_id]
            crown = Vec3((b.footprint.xmin+b.footprint.xmax)/2, b.height-1,
                         (b.footprint.zmin+b.footprint.zmax)/2)
            d = Vec3(l.target.x-c.eye.x, l.target.y-c.eye.y, l.target.z-c.eye.z)
            distance = math.hypot(d.x, d.y, d.z)
            hit = spatial.raycast(c.eye, Vec3(d.x/distance, d.y/distance, d.z/distance), distance+.05)
            landmarks.append({"seed": seed, "id": l.id, "building": asdict(b),
                              "camera": asdict(c), "target": probe(prepared, l.target),
                              "crown": probe(prepared, crown), "target_hit": asdict(hit)})
    return {"label": "NUMERIC PROJECTION ONLY: no city rendering, beauty or gameplay claim",
                     "units": "metres and radians; screen coordinates in character cells",
                     "camera": asdict(camera), "viewport": asdict(viewport),
                     "focal_columns": p.focal_columns, "focal_rows": p.focal_rows,
                     "vertical_fov_radians": p.vfov,
                     "probes": [probe(p, q) for q in (Vec3(2, 3.7, 20), Vec3(2, 3.7, 40),
                                                      Vec3(0, 1.7, .1), Vec3(0, 1.7, .099),
                                                      Vec3(0, 1.7, 0), Vec3(0, 1.7, -10),
                                                      Vec3(100, 1.7, 500), Vec3(0, 1.7, 500.001),
                                                      Vec3(0, 100, 200))],
                     "tower": asdict(building), "tower_poses": poses, "rays": rays,
                     "landmarks": landmarks}


def equivalent(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if type(a) is float:
        return type(b) in (float, int) and math.isclose(a, b, rel_tol=0, abs_tol=1e-8)
    return type(a) is type(b) and a == b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/projection-fixtures.json")
    parser.add_argument("--check", action="store_true", help="read-only numeric comparison, tolerance 1e-8")
    args = parser.parse_args()
    data = generate()
    if args.check:
        try:
            if not equivalent(data, json.loads(args.output.read_text())):
                parser.exit(1, "Projection fixture mismatch\n")
        except (OSError, ValueError) as exc:
            parser.exit(1, f"Cannot read projection fixture: {exc}\n")
        print(f"Projection fixtures match (absolute tolerance 1e-8): {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+"\n")
        print(f"Wrote numeric projection fixtures: {args.output}")
    print("Tower poses: {}; real landmark targets: {}; rays: {}".format(
        len(data["tower_poses"]), len(data["landmarks"]), len(data["rays"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
