"""Independent finite-plane oracle and real city renderer regression checks."""
from dataclasses import replace
from html.parser import HTMLParser
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

from citywalk.appearance import FacadeAppearance
from citywalk.camera import Perspective
from citywalk.contracts import Building, Camera, Cell, City, Landmark, RayHit, Rect, Vec3, Viewport
from citywalk.rendering import CityRenderer, FOG_RGB, shade
from citywalk.spatial import CityGenerator, SpatialWorld
from tools.capture_renderer import generate, scenes, SIZES

ROOT = Path(__file__).resolve().parents[1]


def box(name="front", rect=Rect(-8, 10, 8, 14), height=30):
    return Building(name, rect, height, "amber-brick", 11)


def world(*buildings, landmarks=()):
    return SpatialWorld(City(11, Rect(-600, -600, 600, 600), buildings, landmarks,
                             Vec3(0, 0, 0), Vec3(0, 0, 0)))


class Recorder:
    def __init__(self):
        self.hits = []

    def sample(self, city, hit):
        self.hits.append(hit)
        return Cell("#", (210, 190, 90), (65, 45, 70))


def plane_oracle(city, eye, direction, near, far):
    # Enumerate each finite surface independently; no slab, DDA or renderer
    # helper. Crucially collect exits too before filtering the clip interval.
    hits = []
    o, d = (eye.x, eye.y, eye.z), (direction.x, direction.y, direction.z)
    if d[1]:
        t = -o[1]/d[1]
        r = city.bounds
        if near-1e-8 <= t <= far+1e-8 and r.xmin <= o[0]+t*d[0] <= r.xmax and r.zmin <= o[2]+t*d[2] <= r.zmax:
            hits.append((t, False, "", "ground"))
    for b in city.buildings:
        r = b.footprint
        low, high = (r.xmin, 0, r.zmin), (r.xmax, b.height, r.zmax)
        for axis, faces in enumerate((("west", "east"), ("ground", "roof"), ("south", "north"))):
            if not d[axis]:
                continue
            for plane, face in zip((low[axis], high[axis]), faces):
                t = (plane-o[axis])/d[axis]
                if near-1e-8 <= t <= far+1e-8 and all(low[k]-1e-9 <= o[k]+t*d[k] <= high[k]+1e-9 for k in range(3) if k != axis):
                    hits.append((t, True, b.id, face))
    return min(hits) if hits else None


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.projection = Perspective()
        self.renderer = CityRenderer(self.projection)
        self.camera = Camera(Vec3(0, 1.7, 0))
        self.viewport = Viewport(41, 21)

    def center(self, w, camera=None):
        a = Recorder()
        f = self.renderer.render(w, a, camera or self.camera, Viewport(1, 1))
        return f, a.hits

    def test_front_wall_occludes_rear_and_color_comes_from_nearest(self):
        front, rear = box(), box("rear", Rect(-8, 20, 8, 25), 90)
        f, hits = self.center(world(rear, front))
        self.assertEqual([(h.building_id, h.face) for h in hits], [("front", "south")])
        self.assertAlmostEqual(f.depth[0], 10)
        self.assertEqual(f.cells[0], shade(Cell("#", (210, 190, 90), (65, 45, 70)), hits[0]))
        self.assertEqual(self.center(world(front, rear))[0], f)

    def test_near_plane_inclusive_and_outside_skin_exposes_rear(self):
        c = replace(self.camera, near=10)
        f, hits = self.center(world(box()), c)
        self.assertEqual(hits[0].face, "south")
        self.assertAlmostEqual(f.depth[0], 10)
        skin = box("clipped", Rect(-8, 9, 8, 9.999999))
        f, hits = self.center(world(skin, box("rear", Rect(-8, 20, 8, 25))), c)
        self.assertEqual(hits[0].building_id, "rear")
        self.assertAlmostEqual(f.depth[0], 20)

    def test_near_inside_box_renders_exit_not_sky_or_cap(self):
        f, hits = self.center(world(box()), replace(self.camera, near=12))
        self.assertEqual(hits[0].face, "north")
        self.assertAlmostEqual(f.depth[0], 14)
        self.assertEqual(hits[0].point, Vec3(0, 1.7, 14))
        f, hits = self.center(world(box()), replace(self.camera, eye=Vec3(0, 1.7, 11)))
        self.assertEqual(hits[0].face, "north")
        self.assertAlmostEqual(f.depth[0], 3)

    def test_far_inclusive_off_axis_uses_forward_not_radial_depth(self):
        w = world(box(rect=Rect(-40, 20, 40, 25), height=50))
        c, v = replace(self.camera, far=20), Viewport(41, 1)
        f = self.renderer.render(w, Recorder(), c, v)
        for column, distance in enumerate(f.depth):
            ray = self.projection.ray(column, 0, c, v)
            self.assertAlmostEqual(distance, 20/ray.z)
        self.assertGreater(f.depth[0], c.far)
        f = self.renderer.render(w, Recorder(), replace(c, far=20-1e-6), v)
        self.assertTrue(all(math.isinf(d) for d in f.depth))

    def test_ground_horizon_sky_and_exact_ground_near(self):
        w, a = world(), Recorder()
        f = self.renderer.render(w, a, self.camera, Viewport(1, 3))
        self.assertTrue(math.isinf(f.depth[0]))
        self.assertTrue(math.isinf(f.depth[1]))
        self.assertTrue(math.isfinite(f.depth[2]))
        self.assertEqual(a.hits[0].face, "ground")
        c = replace(self.camera, pitch=-math.pi/4, near=1.7*math.sqrt(2))
        f, hits = self.center(w, c)
        self.assertEqual(hits[0].face, "ground")
        self.assertAlmostEqual(f.depth[0], c.near)

    def test_tower_fills_top_without_crown_projection_and_look_up_reveals_roofline(self):
        w = world(box(rect=Rect(-8, 20, 8, 30), height=100))
        v, a = Viewport(41, 21), Recorder()
        self.assertIsNone(self.projection.project(Vec3(0, 100, 20), self.camera, v))
        f = self.renderer.render(w, a, self.camera, v)
        self.assertTrue(math.isfinite(f.depth[20]))
        self.assertTrue(any(h.point.y > 10 for h in a.hits))
        up = replace(self.camera, pitch=math.pi/3)
        self.assertIsNotNone(self.projection.project(Vec3(0, 100, 20), up, v))
        raised = self.renderer.render(w, Recorder(), up, v)
        self.assertTrue(math.isinf(raised.depth[20]))
        self.assertTrue(math.isfinite(raised.depth[10*41+20]))
        self.assertNotEqual(f, raised)

    def test_planes_oracle_all_cells_clipping_pitch_corner_roof_and_overlap(self):
        w = world(box(), box("overlap", Rect(-4, 12, 12, 26), 12),
                  box("left", Rect(-20, 25, -10, 40), 50))
        for c in (self.camera, replace(self.camera, near=12),
                  replace(self.camera, yaw=-.4, pitch=.35, far=32),
                  replace(self.camera, eye=Vec3(0, 35, 0), pitch=-.5),
                  replace(self.camera, eye=Vec3(8, 1.7, 0))):
            a = Recorder()
            f = self.renderer.render(w, a, c, self.viewport)
            actual_hits = iter(a.hits)
            for i, distance in enumerate(f.depth):
                row, column = divmod(i, self.viewport.columns)
                d = self.projection.ray(column, row, c, self.viewport)
                # Independent forward-depth cosine from yaw/pitch.
                cosine = d.x*math.sin(c.yaw)*math.cos(c.pitch)+d.y*math.sin(c.pitch)+d.z*math.cos(c.yaw)*math.cos(c.pitch)
                expected = plane_oracle(w.city, c.eye, d, c.near/cosine, c.far/cosine)
                if expected is None:
                    self.assertTrue(math.isinf(distance), (c, row, column))
                else:
                    self.assertAlmostEqual(distance, expected[0], places=7)
                    hit = next(actual_hits)
                    self.assertEqual((hit.building_id or "", hit.face), expected[2:])
                    self.assertAlmostEqual(math.dist((c.eye.x, c.eye.y, c.eye.z),
                                                     (hit.point.x, hit.point.y, hit.point.z)), distance)
            self.assertIsNone(next(actual_hits, None))

    def test_tie_building_id_and_ground_precedence(self):
        f, hits = self.center(world(box("z"), box("a")))
        self.assertEqual(hits[0].building_id, "a")
        # Below-ground diagnostic ray: ground and box underside coincide.
        c = Camera(Vec3(0, -1, 9), pitch=math.pi/4)
        f, hits = self.center(world(box()), c)
        self.assertIsNone(hits[0].building_id)

    def test_distance_fog_lighting_and_emissive_contrast(self):
        cell = Cell("+", (255, 192, 99), (82, 47, 57))
        base = RayHit(12, Vec3(0, 8, 10), Vec3(0, 0, -1), "south", "b")
        near, far = shade(cell, base), shade(cell, replace(base, distance=400))
        self.assertLess(math.dist(far.bg, FOG_RGB), math.dist(near.bg, FOG_RGB))
        self.assertLess(math.dist(far.fg, FOG_RGB), math.dist(near.fg, FOG_RGB))
        west = shade(cell, replace(base, face="west"))
        self.assertLess(sum(west.bg), sum(near.bg))
        self.assertGreater(west.fg[0], 240)
        self.assertEqual(far.glyph, ".")

    def test_protocol_only_projection_adapter_matches_prepared_path(self):
        p = self.projection
        class MinimalProjection:
            def ray(self, column, row, camera, viewport):
                return p.ray(column, row, camera, viewport)
            def project(self, point, camera, viewport):
                return p.project(point, camera, viewport)
        renderer = CityRenderer(MinimalProjection())
        w, a = world(box()), FacadeAppearance()
        for c in (self.camera, replace(self.camera, yaw=-.2, pitch=.3)):
            f, g = renderer.render(w, a, c, self.viewport), self.renderer.render(w, a, c, self.viewport)
            self.assertEqual(f.cells, g.cells)
            for d, e in zip(f.depth, g.depth):
                if math.isfinite(d):
                    self.assertAlmostEqual(d, e)
                else:
                    self.assertEqual(d, e)
            self.assertEqual(renderer.sightings(w, c, self.viewport), ())

    def test_real_city_valid_cells_repeat_resize_pose_and_world_changes(self):
        a = FacadeAppearance()
        for seed in (11, 93, 2026):
            w = CityGenerator().generate(seed)
            for columns, rows in SIZES:
                v = Viewport(columns, rows)
                c = scenes(w)[0][2]
                f = self.renderer.render(w, a, c, v)
                self.assertEqual(f, self.renderer.render(w, a, c, v))
                self.assertEqual(len(f.cells), columns*rows)
                self.assertEqual(len(f.depth), columns*rows)
                self.assertGreater(len(set(cell.bg for cell in f.cells)), 30)
                for cell, depth in zip(f.cells, f.depth):
                    self.assertEqual(len(cell.glyph), 1)
                    self.assertTrue(32 <= ord(cell.glyph) < 127)
                    self.assertTrue(depth > 0)
                    for color in (cell.fg, cell.bg):
                        self.assertEqual(len(color), 3)
                        self.assertTrue(all(type(x) is int and 0 <= x <= 255 for x in color))
        empty = self.renderer.render(world(), a, c, v)
        self.assertNotEqual(empty, f)  # ray cache must never cache city/material results

    def test_renderer_perspective_shrinkage_and_lens_cache_invalidation(self):
        v = Viewport(81, 1)
        a = FacadeAppearance()
        near = world(box(rect=Rect(-4, 20, 4, 25)))
        far = world(box(rect=Rect(-4, 40, 4, 45)))
        f = self.renderer.render(near, a, self.camera, v)
        g = self.renderer.render(far, a, self.camera, v)
        front_width = sum(math.isfinite(d) for d in f.depth)
        back_width = sum(math.isfinite(d) for d in g.depth)
        self.assertLessEqual(abs(front_width-2*back_width), 2)
        for c in (replace(self.camera, hfov=.7), replace(self.camera, near=22),
                  replace(self.camera, far=19), replace(self.camera, yaw=.2, pitch=.1)):
            actual = self.renderer.render(near, a, c, v)
            fresh = CityRenderer(Perspective()).render(near, a, c, v)
            self.assertEqual(actual, fresh)
        # Changing cell aspect changes the physical image lens, even at same size.
        wide = Viewport(81, 9, .8)
        self.assertEqual(self.renderer.render(near, a, self.camera, wide),
                         CityRenderer(Perspective()).render(near, a, self.camera, wide))

    def test_invalid_camera_and_viewport_rejected(self):
        for v in (Viewport(0, 20), Viewport(80, -1), Viewport(80, 20, 0)):
            with self.assertRaises(ValueError):
                self.renderer.render(world(), Recorder(), self.camera, v)
        for c in (replace(self.camera, near=0), replace(self.camera, far=.01),
                  replace(self.camera, yaw=math.nan)):
            with self.assertRaises(ValueError):
                self.renderer.render(world(), Recorder(), c, self.viewport)


class SightingTests(unittest.TestCase):
    def setUp(self):
        self.r = CityRenderer(Perspective())
        self.v = Viewport(100, 32)

    def test_all_actual_landmark_viewpoints_range_bearing_and_crowns(self):
        for seed in (11, 93, 2026):
            w = CityGenerator().generate(seed)
            for lm in w.city.landmarks:
                c = Camera(lm.viewpoint, lm.view_yaw, lm.view_pitch)
                sightings = self.r.sightings(w, c, self.v)
                self.assertEqual([s.landmark_id for s in sightings], sorted(l.id for l in w.city.landmarks))
                s = next(s for s in sightings if s.landmark_id == lm.id)
                self.assertTrue(s.visible)
                self.assertTrue(s.crown_visible)
                self.assertTrue(18 <= s.range_m <= 65)
                self.assertAlmostEqual(s.bearing_error, 0)

    def test_occluded_offscreen_behind_clip_and_internal_target(self):
        b = box("landmark", Rect(-8, 20, 8, 30), 25)
        lm = Landmark("s", b.id, "Test", "District", Vec3(0, 12, 20), Vec3(0, 1.7, 0), 0, .3)
        c = Camera(lm.viewpoint, pitch=.3)
        w = world(b, landmarks=(lm,))
        self.assertTrue(self.r.sightings(w, c, self.v)[0].visible)
        blocked = world(b, box("occluder", Rect(-8, 10, 8, 14), 50), landmarks=(lm,))
        self.assertFalse(self.r.sightings(blocked, c, self.v)[0].visible)
        self.assertFalse(self.r.sightings(blocked, c, self.v)[0].crown_visible)
        for altered in (replace(c, yaw=math.pi), replace(c, yaw=1.2),
                        replace(c, near=40), replace(c, far=10)):
            self.assertFalse(self.r.sightings(w, altered, self.v)[0].visible)
        internal = replace(lm, target=Vec3(0, 12, 25))
        self.assertFalse(self.r.sightings(world(b, landmarks=(internal,)), c, self.v)[0].visible)
        # A target 4 cm behind the surface is allowed by the explicit 5 cm rule.
        close = replace(lm, target=Vec3(0, 12, 20.04))
        self.assertTrue(self.r.sightings(world(b, landmarks=(close,)), c, self.v)[0].visible)
        # Foreground before rendering near remains a photography occluder.
        self.assertFalse(self.r.sightings(blocked, replace(c, near=16), self.v)[0].visible)

    def test_bearing_wrap_horizontal_range_and_crown_blocked_separately(self):
        b = box("landmark", Rect(-8, 20, 8, 30), 25)
        lm = Landmark("s", b.id, "Test", "District", Vec3(0, 4, 20), Vec3(0, 1.7, 0), 0, 0)
        w = world(b, landmarks=(lm,))
        s = self.r.sightings(w, Camera(lm.viewpoint, yaw=math.tau-.1), self.v)[0]
        self.assertAlmostEqual(s.bearing_error, .1)
        self.assertEqual(s.range_m, 20)
        self.assertTrue(s.visible)
        self.assertFalse(s.crown_visible)  # crown above level frame, target visible
        self.assertTrue(self.r.sightings(w, Camera(lm.viewpoint, pitch=.5), self.v)[0].crown_visible)


class CaptureTests(unittest.TestCase):
    def test_committed_frames_regenerate_exactly_and_are_safe_street_level(self):
        generated = generate(11)
        for name, content in generated.items():
            self.assertEqual((ROOT/"docs"/"renderer-frames"/name).read_bytes(), content.encode())
        data = json.loads(generated["frames.json"])
        w = CityGenerator().generate(11)
        self.assertEqual(len(data["panels"]), len(SIZES)*len(scenes(w)))
        for p in data["panels"]:
            eye = p["camera"]["eye"]
            self.assertEqual(eye["y"], 1.7)
            self.assertTrue(w.walkable(Vec3(eye["x"], 0, eye["z"]), .3))
            f = p["frame"]
            self.assertEqual(len(f["cells"]), f["columns"]*f["rows"])
            self.assertEqual(len(f["depth_m"]), len(f["cells"]))
        # Parse HTML rather than claiming an unobserved browser screenshot.
        class Cells(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.styles, self.glyphs = [], []
                self.active = False
            def handle_starttag(self, tag, attrs):
                if tag == "span":
                    self.styles.append(dict(attrs)["style"])
                    self.active = True
            def handle_endtag(self, tag):
                if tag == "span":
                    self.active = False
            def handle_data(self, text):
                if self.active:
                    self.glyphs.append(text)
        parser = Cells()
        parser.feed(generated["frames.html"])
        expected = [p["frame"]["cell_table"][i] for p in data["panels"] for i in p["frame"]["cells"]]
        self.assertEqual(parser.glyphs, [c["glyph"] for c in expected])
        self.assertEqual(parser.styles, ["color:rgb"+str(tuple(c["fg"]))+";background:rgb"+str(tuple(c["bg"])) for c in expected])

    def test_hash_seed_independence_fresh_processes(self):
        code = "from tools.capture_renderer import generate; import hashlib; print(hashlib.sha256(generate(11)[\"frames.json\"].encode()).hexdigest())"
        hashes = []
        for seed in ("1", "917"):
            p = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                               env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr)
            hashes.append(p.stdout.strip())
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(hashes[0], hashlib.sha256((ROOT/"docs/renderer-frames/frames.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
