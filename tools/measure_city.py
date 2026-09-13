"""Headless reproducible world measurements; no renderer or simulated game output."""
from collections import Counter, deque
from dataclasses import asdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from citywalk.contracts import Vec3
from citywalk.spatial import CityGenerator


def measure(seed):
    world = CityGenerator().generate(seed)
    city, route = world.city, world.survey_route()
    buildings = city.buildings
    sizes = {(b.footprint.xmax-b.footprint.xmin, b.footprint.zmax-b.footprint.zmin) for b in buildings}
    area = sum((b.footprint.xmax-b.footprint.xmin)*(b.footprint.zmax-b.footprint.zmin) for b in buildings)
    free = {(x, z) for x in range(-238, 239, 2) for z in range(-238, 239, 2)
            if world.walkable(Vec3(x, 0, z), .3)}
    seen, queue = {(0, 0)}, deque([(0, 0)])
    while queue:
        x, z = queue.popleft()
        for dx, dz in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            n = x+dx, z+dz
            if n in free and n not in seen and world.segment_clear(Vec3(x, 0, z), Vec3(n[0], 0, n[1])):
                seen.add(n)
                queue.append(n)
    landmarks = []
    for landmark in city.landmarks:
        eye, target = landmark.viewpoint, landmark.target
        distance = math.dist((eye.x, eye.y, eye.z), (target.x, target.y, target.z))
        d = Vec3((target.x-eye.x)/distance, (target.y-eye.y)/distance, (target.z-eye.z)/distance)
        hit = world.raycast(eye, d, distance+.05)
        path = world.path_to(landmark.id)
        landmarks.append(dict(asdict(landmark),
                              horizontal_range_m=math.hypot(target.x-eye.x, target.z-eye.z),
                              first_hit_building=hit.building_id if hit else None,
                              target_distance_error_m=abs(hit.distance-distance) if hit else None,
                              path_clear=all(world.segment_clear(a, b) for a, b in zip(path, path[1:])),
                              depot_path=[asdict(p) for p in path]))
    return {
        "seed": seed,
        "generation_version": 1,
        "city_sha256": hashlib.sha256(json.dumps(asdict(city), sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "bounds_m": asdict(city.bounds),
        "area_m2": 480*480,
        "building_count": len(buildings),
        "building_footprint_area_m2": area,
        "open_ground_area_m2": 480*480-area,
        "height_range_m": [min(b.height for b in buildings), max(b.height for b in buildings)],
        "ordinary_height_range_m": [min(b.height for b in buildings if b.id.startswith("block-")),
                                    max(b.height for b in buildings if b.id.startswith("block-"))],
        "distinct_heights": len({b.height for b in buildings}),
        "distinct_footprint_dimensions": len(sizes),
        "footprint_side_range_m": [min(min(s) for s in sizes), max(max(s) for s in sizes)],
        "style_counts": dict(sorted(Counter(b.style for b in buildings).items())),
        "public_space_counts": dict(sorted(Counter(s.kind for s in world.public_spaces).items())),
        "road_clear_widths_m": sorted({min(s.rect.xmax-s.rect.xmin, s.rect.zmax-s.rect.zmin)
                                       for s in world.public_spaces if s.kind in ("street", "avenue", "promenade")}),
        "navigation_nodes": len(world.navigation_points),
        "navigation_edges": len(world.navigation_edges),
        "all_graph_edges_disc_clear": all(world.segment_clear(world.navigation_points[a], world.navigation_points[b])
                                           for a, b in world.navigation_edges),
        "clearance_lattice_spacing_m": 2,
        "clearance_lattice_free_points": len(free),
        "clearance_lattice_reachable_points": len(seen),
        "spawn": asdict(city.spawn),
        "spawn_clear_radius_m": .3,
        "spawn_safe": world.walkable(city.spawn, .3),
        "depot_submission_disc_safe": world.walkable(city.depot, 3),
        "landmarks": landmarks,
        "three_destination_route": asdict(route),
        "route_plus_positioning_seconds": route.walking_seconds+route.positioning_seconds,
        "scope": "Static geometry and clearance evidence only; not movement, projection or game-rule execution."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[11, 93, 2026])
    args = parser.parse_args()
    print(json.dumps([measure(seed) for seed in args.seeds], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
