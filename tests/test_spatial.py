"""Independent geometry oracles, generated-world invariants and clearance routes."""
from collections import deque
from dataclasses import asdict, replace
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import unittest

from citywalk.contracts import Building, City, Rect, Vec3
from citywalk.spatial import CityGenerator, SpatialWorld, PLAYER_RADIUS, EPS, path_length

SEEDS = (11, 93, 2026)


def fixture(*buildings, bounds=Rect(-100, -100, 100, 100)):
    return SpatialWorld(City(0, bounds, tuple(buildings), (), Vec3(-5, 0, -5), Vec3(-5, 0, -5)))


def box(id="b", rect=Rect(0, 0, 10, 10), height=20):
    return Building(id, rect, height, "test", 0)


def direction(a, b):
    distance = math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
    return Vec3((b.x-a.x)/distance, (b.y-a.y)/distance, (b.z-a.z)/distance), distance


def brute_walkable(city, p, radius):
    # Independent clamp-to-rectangle oracle, no spatial-index use.
    r, pad = city.bounds, radius+1e-6
    if not (p.y == 0 and r.xmin+pad < p.x < r.xmax-pad and r.zmin+pad < p.z < r.zmax-pad):
        return False
    for b in city.buildings:
        r = b.footprint
        x, z = min(max(p.x, r.xmin), r.xmax), min(max(p.z, r.zmin), r.zmax)
        if math.hypot(x-p.x, z-p.z) <= pad:
            return False
    return True


def brute_ray(city, origin, d, limit):
    # Independent six finite plane intersections, not the implementation slab algorithm.
    hits = []
    if d.y:
        t = -origin.y/d.y
        x, z = origin.x+t*d.x, origin.z+t*d.z
        r = city.bounds
        if 0 < t <= limit and r.xmin <= x <= r.xmax and r.zmin <= z <= r.zmax:
            hits.append((t, False, "", "ground"))
    for b in city.buildings:
        r = b.footprint
        low, high = (r.xmin, 0, r.zmin), (r.xmax, b.height, r.zmax)
        o, v = (origin.x, origin.y, origin.z), (d.x, d.y, d.z)
        for axis, faces in enumerate((("west", "east"), ("ground", "roof"), ("south", "north"))):
            if v[axis] == 0:
                continue
            for plane, face in zip((low[axis], high[axis]), faces):
                t = (plane-o[axis])/v[axis]
                if 0 < t <= limit and all(low[k]-1e-9 <= o[k]+t*v[k] <= high[k]+1e-9
                                          for k in range(3) if k != axis):
                    hits.append((t, True, b.id, face))
    return min(hits) if hits else None


class StaticQueries(unittest.TestCase):
    def test_walkable_disc_edges_corners_bounds_and_height(self):
        w = fixture(box())
        for p, expected in ((Vec3(-0.3, 0, 5), False), (Vec3(-0.3000005, 0, 5), False),
                            (Vec3(-0.300002, 0, 5), True), (Vec3(-0.22, 0, -0.22), True),
                            (Vec3(-0.2, 0, -0.2), False), (Vec3(5, 0, 5), False),
                            (Vec3(-99.7, 0, -5), False), (Vec3(-99.699, 0, -5), True),
                            (Vec3(-5, 1.7, -5), False)):
            with self.subTest(p=p):
                self.assertEqual(w.walkable(p, .3), expected)
        self.assertFalse(w.walkable(Vec3(0, 0, 5), 0))
        self.assertTrue(w.walkable(Vec3(-1, 0, 5), 0))

    def test_closed_nearby_sorted_deduplicated_and_far_bounds(self):
        w = fixture(box("z", Rect(0, 0, 48, 48)), box("a", Rect(-48, 0, 0, 48)))
        self.assertEqual(tuple(b.id for b in w.nearby(Rect(0, 48, 0, 48))), ("a", "z"))
        self.assertEqual(w.nearby(Rect(49, 49, 51, 51)), ())
        self.assertEqual(tuple(b.id for b in w.nearby(Rect(-1e20, -1e20, 1e20, 1e20))), ("a", "z"))
        self.assertEqual(w.nearby(Rect(200, 0, 300, 10)), ())

    def test_exact_swept_disc_not_point_connectivity(self):
        # Positive point passage but insufficient 0.6 m player width.
        w = fixture(box("left", Rect(-10, -10, -.25, 10)),
                    box("right", Rect(.25, -10, 10, 10)))
        a, b = Vec3(0, 0, -20), Vec3(0, 0, 20)
        self.assertTrue(w.segment_clear(a, b, 0))
        self.assertFalse(w.segment_clear(a, b, .3))
        self.assertTrue(w.walkable(a, .3))
        self.assertTrue(w.walkable(b, .3))
        w = fixture(box())
        self.assertFalse(w.segment_clear(Vec3(-5, 0, 5), Vec3(15, 0, 5)))
        self.assertFalse(w.segment_clear(Vec3(-5, 0, -.3), Vec3(15, 0, -.3)))
        self.assertTrue(w.segment_clear(Vec3(-5, 0, -.30001), Vec3(15, 0, -.30001)))
        # Rounded corner: expanded-square broad phase must not act as narrow phase.
        p = Vec3(-.22, 0, -.22)
        self.assertTrue(w.segment_clear(p, p))
        self.assertFalse(w.segment_clear(Vec3(-5, 0, 5), Vec3(101, 0, 5)))
        self.assertFalse(w.segment_clear(Vec3(-5, 0, 5), Vec3(-5, 1, 5)))

    def test_swept_disc_against_independent_convex_distance_oracle(self):
        w = fixture(box("a", Rect(-12, -8, -3, 14)),
                    box("b", Rect(4, -16, 10, -2)), box("c", Rect(8, 5, 22, 19)))
        rng = random.Random(241)
        for _ in range(500):
            a = Vec3(rng.uniform(-30, 30), 0, rng.uniform(-30, 30))
            b = Vec3(rng.uniform(-30, 30), 0, rng.uniform(-30, 30))
            radius = rng.choice((0, .3, 1, 3))
            clear = True
            for building in w.city.buildings:
                r = building.footprint
                def distance(t):
                    x, z = a.x+(b.x-a.x)*t, a.z+(b.z-a.z)*t
                    return math.hypot(x-min(max(x, r.xmin), r.xmax),
                                      z-min(max(z, r.zmin), r.zmax))
                # Distance to a convex rectangle along a line is convex. This
                # numerical oracle shares neither slab nor corner-distance code.
                lo, hi = 0.0, 1.0
                for _ in range(72):
                    left, right = (2*lo+hi)/3, (lo+2*hi)/3
                    if distance(left) < distance(right):
                        hi = right
                    else:
                        lo = left
                minimum = min(distance(0), distance(1), distance((lo+hi)/2))
                if minimum <= radius+1e-6:
                    clear = False
            self.assertEqual(w.segment_clear(a, b, radius), clear)
            self.assertEqual(w.segment_clear(b, a, radius), clear)

    def test_six_box_faces_ground_sky_and_distance_limit(self):
        w = fixture(box())
        cases = ((Vec3(-5, 5, 5), Vec3(1, 0, 0), "west", Vec3(-1, 0, 0), 5),
                 (Vec3(15, 5, 5), Vec3(-1, 0, 0), "east", Vec3(1, 0, 0), 5),
                 (Vec3(5, 5, -5), Vec3(0, 0, 1), "south", Vec3(0, 0, -1), 5),
                 (Vec3(5, 5, 15), Vec3(0, 0, -1), "north", Vec3(0, 0, 1), 5),
                 (Vec3(5, 25, 5), Vec3(0, -1, 0), "roof", Vec3(0, 1, 0), 5))
        for origin, d, face, normal, distance in cases:
            with self.subTest(face=face):
                hit = w.raycast(origin, d, distance)
                self.assertEqual((hit.building_id, hit.face, hit.normal, hit.distance),
                                 ("b", face, normal, distance))
                self.assertIsNone(w.raycast(origin, d, distance-.001))
        ground = w.raycast(Vec3(-5, 1.7, -5), Vec3(0, -1, 0), 20)
        self.assertEqual((ground.face, ground.building_id, ground.distance), ("ground", None, 1.7))
        self.assertIsNone(w.raycast(Vec3(-5, 1.7, -5), Vec3(0, 1, 0), 500))
        self.assertIsNone(w.raycast(Vec3(-5, 1.7, -5), Vec3(-1, 0, 0), 500))
        self.assertIsNone(w.raycast(Vec3(101, 5, 5), Vec3(0, -1, 0), 500))
        # Ground wins a tie against a building underside (origin below ground).
        hit = w.raycast(Vec3(5, -5, 5), Vec3(0, 1, 0), 10)
        self.assertEqual((hit.face, hit.building_id), ("ground", None))

    def test_inside_surface_parallel_grid_boundaries_and_ties(self):
        w = fixture(box("z"), box("a"))
        self.assertEqual(w.raycast(Vec3(5, 5, 5), Vec3(1, 0, 0), 20).building_id, "a")
        self.assertIsNone(w.raycast(Vec3(0, 5, 5), Vec3(-1, 0, 0), 20))
        self.assertEqual(w.raycast(Vec3(0, 5, 5), Vec3(1, 0, 0), 20).face, "east")
        d, length = direction(Vec3(-5, 5, -5), Vec3(0, 5, 0))
        self.assertEqual(w.raycast(Vec3(-5, 5, -5), d, 20).face, "south")
        w = fixture(box("edge", Rect(0, 24, 24, 48)))
        self.assertEqual(w.raycast(Vec3(24, 5, -50), Vec3(0, 0, 1), 100).distance, 74)
        self.assertEqual(w.raycast(Vec3(150, 5, 30), Vec3(-1, 0, 0), 200).distance, 126)
        for origin in (Vec3(-48, 5, -48), Vec3(72, 5, 72)):
            d, distance = direction(origin, Vec3(24, 5, 24))
            self.assertEqual(w.raycast(origin, d, 200).building_id, "edge")
        w = fixture(box("touch", Rect(24, 24, 48, 48)))
        self.assertEqual(w.raycast(Vec3(0, 5, 24), Vec3(1, 0, 0), 24).distance, 24)

    def test_invalid_query_and_city_inputs(self):
        w = fixture(box())
        for radius in (-1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                w.walkable(Vec3(-5, 0, -5), radius)
        with self.assertRaises(ValueError):
            w.nearby(Rect(1, 0, 0, 1))
        with self.assertRaises(ValueError):
            w.walkable(Vec3(math.nan, 0, 0), .3)
        for d, distance in ((Vec3(0, 0, 0), 10), (Vec3(2, 0, 0), 10),
                            (Vec3(1, 0, 0), 0), (Vec3(1, 0, 0), math.inf),
                            (Vec3(math.nan, 0, 1), 10)):
            with self.assertRaises(ValueError):
                w.raycast(Vec3(0, 1, 0), d, distance)
        for b in (box(height=-1), box(rect=Rect(2, 0, 1, 1)),
                  box(rect=Rect(0, 0, 1000, 10)), box(height=math.inf)):
            with self.assertRaises(ValueError):
                fixture(b)
        with self.assertRaises(ValueError):
            fixture(box(), box())
        with self.assertRaises(AttributeError):
            w.city = w.city

    def test_random_rays_disc_and_nearby_against_independent_oracles(self):
        rng = random.Random(7002)
        for seed in SEEDS:
            w = CityGenerator().generate(seed)
            for _ in range(600):
                p = Vec3(rng.uniform(-280, 280), 0, rng.uniform(-280, 280))
                radius = rng.choice((0, .3, 1, 4))
                self.assertEqual(w.walkable(p, radius), brute_walkable(w.city, p, radius))
                r = Rect(p.x-10, p.z-10, p.x+10, p.z+10)
                expected = tuple(b for b in w.city.buildings if
                                 b.footprint.xmin <= r.xmax and b.footprint.xmax >= r.xmin and
                                 b.footprint.zmin <= r.zmax and b.footprint.zmax >= r.zmin)
                self.assertEqual(w.nearby(r), expected)
                origin = Vec3(p.x, rng.uniform(-10, 160), p.z)
                target = Vec3(rng.uniform(-240, 240), rng.uniform(0, 140), rng.uniform(-240, 240))
                d, _ = direction(origin, target)
                expected = brute_ray(w.city, origin, d, 800)
                actual = w.raycast(origin, d, 800)
                if expected is None:
                    self.assertIsNone(actual)
                else:
                    self.assertIsNotNone(actual)
                    self.assertAlmostEqual(actual.distance, expected[0], places=7)
                    self.assertEqual((actual.building_id or "", actual.face), expected[2:])


class Generation(unittest.TestCase):
    def test_determinism_across_process_hash_seeds_and_seed_variation(self):
        code = ("import hashlib,json; from dataclasses import asdict; "
                "from citywalk.spatial import CityGenerator; "
                "print(json.dumps([hashlib.sha256(json.dumps(asdict(CityGenerator().generate(s).city),"
                "sort_keys=True,separators=(chr(44),chr(58))).encode()).hexdigest() "
                "for s in (11,93,2026)]))")
        outputs = []
        for hashseed in ("1", "917"):
            run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                 env=dict(os.environ, PYTHONHASHSEED=hashseed), timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            outputs.append(json.loads(run.stdout))
        self.assertEqual(outputs[0], outputs[1])
        # Observed v1 geometry hashes pin accidental seed-algorithm drift.
        self.assertEqual(outputs[0], ['47b25ee7fc39b0fa800404adac2d5b4f93fd8b73947b3e6959fc19fe188f7f11', '736b945021f0783449ba160ec988bbb64bd9720018f7213b88c0f6fa4496a1e4', 'c7fd00b8ee7d275966883c5f440cdcc8ef71d15270bb7af78016bbdfeb2c71e2'])
        self.assertEqual(len(set(outputs[0])), 3)
        for seed in SEEDS:
            a, b = CityGenerator().generate(seed), CityGenerator().generate(seed)
            self.assertEqual(a.city, b.city)
            self.assertEqual(a.public_spaces, b.public_spaces)
            self.assertEqual(a.navigation_points, b.navigation_points)
            self.assertEqual(a.navigation_edges, b.navigation_edges)
            self.assertEqual(a.survey_route(), b.survey_route())
        a, b = (CityGenerator().generate(seed).city for seed in (11, 93))
        self.assertNotEqual(a.buildings, b.buildings)
        self.assertNotEqual(tuple(b.footprint for b in a.buildings), tuple(b.footprint for b in b.buildings))
        for seed in ("11", True, 11.0, None):
            with self.assertRaises(ValueError):
                CityGenerator().generate(seed)

    def test_bounds_human_scale_variety_nonoverlap_public_spaces(self):
        for seed in SEEDS + (0, -1, 2**63):
            with self.subTest(seed=seed):
                w = CityGenerator().generate(seed)
                city = w.city
                self.assertEqual(city.bounds, Rect(-240, -240, 240, 240))
                self.assertGreaterEqual(len(city.buildings), 120)
                self.assertEqual(len({b.id for b in city.buildings}), len(city.buildings))
                sizes, bands = set(), set()
                for i, b in enumerate(city.buildings):
                    r = b.footprint
                    self.assertTrue(-240 < r.xmin < r.xmax < 240)
                    self.assertTrue(-240 < r.zmin < r.zmax < 240)
                    self.assertGreaterEqual(min(r.xmax-r.xmin, r.zmax-r.zmin), 9)
                    self.assertTrue(12 <= b.height <= 140)
                    sizes.add((r.xmax-r.xmin, r.zmax-r.zmin))
                    bands.add(int(b.height//30))
                    for other in city.buildings[i+1:]:
                        s = other.footprint
                        self.assertFalse(r.xmin <= s.xmax and r.xmax >= s.xmin and
                                         r.zmin <= s.zmax and r.zmax >= s.zmin)
                self.assertGreaterEqual(len(sizes), 10)
                self.assertGreaterEqual(len(bands), 3)
                self.assertEqual(len({b.style for b in city.buildings}), 5)
                self.assertGreaterEqual(sum(s.kind == "plaza" for s in w.public_spaces), 5)
                for space in w.public_spaces:
                    r = space.rect
                    for building in w.nearby(r):
                        s = building.footprint
                        self.assertFalse(r.xmin < s.xmax and r.xmax > s.xmin and
                                         r.zmin < s.zmax and r.zmax > s.zmin, space.id)
                    self.assertTrue(w.walkable(Vec3((r.xmin+r.xmax)/2, 0, (r.zmin+r.zmax)/2), .3))
                self.assertTrue(brute_walkable(city, city.spawn, .3))
                self.assertTrue(brute_walkable(city, city.depot, 3.0))

    def test_all_streets_continuous_disc_clearance_and_long_sightlines(self):
        for seed in SEEDS:
            w = CityGenerator().generate(seed)
            for a, b in w.navigation_edges:
                self.assertTrue(w.segment_clear(w.navigation_points[a], w.navigation_points[b], .3))
                # Wider than player: verifies roads, not a lucky point path.
                self.assertTrue(w.segment_clear(w.navigation_points[a], w.navigation_points[b], 1.0))
            for space in w.public_spaces:
                r = space.rect
                if space.kind == "lane":
                    if r.xmax-r.xmin < r.zmax-r.zmin:
                        a = Vec3((r.xmin+r.xmax)/2, 0, r.zmin-.5)
                        b = Vec3(a.x, 0, r.zmax+.5)
                    else:
                        a = Vec3(r.xmin-.5, 0, (r.zmin+r.zmax)/2)
                        b = Vec3(r.xmax+.5, 0, a.z)
                    self.assertTrue(w.segment_clear(a, b, 2.9))
                if space.kind not in ("street", "avenue", "promenade"):
                    continue
                if r.xmax-r.xmin < r.zmax-r.zmin:
                    a, b = Vec3((r.xmin+r.xmax)/2, 0, -239), Vec3((r.xmin+r.xmax)/2, 0, 239)
                else:
                    a, b = Vec3(-239, 0, (r.zmin+r.zmax)/2), Vec3(239, 0, (r.zmin+r.zmax)/2)
                self.assertTrue(w.segment_clear(a, b, .3))
                eye_a, eye_b = replace(a, y=1.7), replace(b, y=1.7)
                d, distance = direction(eye_a, eye_b)
                self.assertIsNone(w.raycast(eye_a, d, distance))

    def test_all_destinations_visible_reachable_and_three_photo_geometric_replay(self):
        for seed in SEEDS:
            w = CityGenerator().generate(seed)
            self.assertEqual(len(w.city.landmarks), 5)
            self.assertEqual(len({l.district for l in w.city.landmarks}), 5)
            for landmark in w.city.landmarks:
                b = next(b for b in w.city.buildings if b.id == landmark.building_id)
                self.assertEqual(landmark.target.y, b.height/2)
                self.assertEqual(landmark.viewpoint.y, 1.7)
                path = w.path_to(landmark.id)
                self.assertEqual(path[0], w.city.depot)
                self.assertEqual(path[-1], replace(landmark.viewpoint, y=0))
                self.assertTrue(brute_walkable(w.city, path[-1], .3))
                self.assertTrue(all(w.segment_clear(a, b) for a, b in zip(path, path[1:])))
                horizontal = math.hypot(landmark.target.x-landmark.viewpoint.x,
                                        landmark.target.z-landmark.viewpoint.z)
                self.assertTrue(18 <= horizontal <= 65)
                self.assertLess(abs(landmark.view_pitch), math.pi/3)
                d, length = direction(landmark.viewpoint, landmark.target)
                hit = w.raycast(landmark.viewpoint, d, length+.05)
                self.assertEqual(hit.building_id, landmark.building_id)
                self.assertAlmostEqual(hit.distance, length)
                self.assertAlmostEqual(math.atan2(d.x, d.z), landmark.view_yaw)
                self.assertAlmostEqual(math.asin(d.y), landmark.view_pitch)
                crown = Vec3((b.footprint.xmin+b.footprint.xmax)/2, b.height-1,
                             (b.footprint.zmin+b.footprint.zmax)/2)
                d, length = direction(landmark.viewpoint, crown)
                self.assertEqual(w.raycast(landmark.viewpoint, d, length).building_id, b.id)
            route = w.survey_route()
            self.assertEqual(route.points[0], w.city.depot)
            self.assertEqual(route.points[-1], w.city.depot)
            self.assertEqual(len(set(route.landmark_ids)), 3)
            self.assertAlmostEqual(route.distance_m, path_length(route.points))
            self.assertLessEqual(route.distance_m, 1680)
            self.assertLessEqual(route.walking_seconds+route.positioning_seconds, 420)
            # Geometry replay at <=0.1 m. Not Walker, Renderer or SurveyRules simulation.
            for a, b in zip(route.points, route.points[1:]):
                self.assertTrue(w.segment_clear(a, b))
                steps = max(1, math.ceil(math.hypot(b.x-a.x, b.z-a.z)/.1))
                for i in range(steps+1):
                    p = Vec3(a.x+(b.x-a.x)*i/steps, 0, a.z+(b.z-a.z)*i/steps)
                    self.assertTrue(w.walkable(p, .3))
            for id in route.landmark_ids:
                landmark = next(l for l in w.city.landmarks if l.id == id)
                self.assertIn(replace(landmark.viewpoint, y=0), route.points)

    def test_clearance_flood_entire_exploration_area(self):
        # Full 2 m lattice, not just designated street centers. Every edge checked
        # as a continuous disc sweep: occupancy alone does not prove an edge safe.
        for seed in SEEDS:
            w = CityGenerator().generate(seed)
            free = {(x, z) for x in range(-238, 239, 2) for z in range(-238, 239, 2)
                    if w.walkable(Vec3(x, 0, z), .3)}
            seen, queue = {(0, 0)}, deque([(0, 0)])
            while queue:
                x, z = queue.popleft()
                for dx, dz in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    n = x+dx, z+dz
                    if n not in free or n in seen:
                        continue
                    if w.segment_clear(Vec3(x, 0, z), Vec3(n[0], 0, n[1]), .3):
                        seen.add(n)
                        queue.append(n)
            self.assertEqual(len(seen), len(free), f"seed={seed}: isolated clearance samples")
            self.assertGreater(len(free), 25000)


if __name__ == "__main__":
    unittest.main()
