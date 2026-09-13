"""Appearance contract checks, metre-scale probes and actual spatial integration."""
from dataclasses import replace
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

from citywalk.appearance import FacadeAppearance, PALETTES, NEUTRAL
from citywalk.contracts import Appearance, Building, Cell, City, Landmark, RayHit, Rect, Vec3
from citywalk.spatial import CityGenerator, SpatialWorld
from tools.preview_appearance import generate

ROOT = Path(__file__).resolve().parents[1]
NORMALS = {"south": Vec3(0, 0, -1), "north": Vec3(0, 0, 1), "west": Vec3(-1, 0, 0),
           "east": Vec3(1, 0, 0), "roof": Vec3(0, 1, 0), "ground": Vec3(0, 1, 0)}


def fixture(style="amber-brick", seed=11, height=30, landmark=False, span=12):
    b = Building("custom", Rect(-24, -24, -24+span, -24+span), height, style, seed)
    sight = Landmark("sight", b.id, "Custom sight", "Custom district", Vec3(-18, height/2, -24),
                     Vec3(-18, 1.7, -50), 0, 0)
    city = City(0, Rect(-100, -100, 100, 100), (b,), (sight,) if landmark else (),
                Vec3(0, 0, 0), Vec3(0, 0, 0))
    return city, b


def wall_hit(b, u, y, face="south", distance=1):
    r = b.footprint
    point = {"south": Vec3(r.xmin+u, y, r.zmin), "north": Vec3(r.xmin+u, y, r.zmax),
             "west": Vec3(r.xmin, y, r.zmin+u), "east": Vec3(r.xmax, y, r.zmin+u)}[face]
    return RayHit(distance, point, NORMALS[face], face, b.id)


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.appearance: Appearance = FacadeAppearance()

    def assertValid(self, cell):
        self.assertIsInstance(cell, Cell)
        self.assertEqual(len(cell.glyph), 1)
        self.assertTrue(32 <= ord(cell.glyph) <= 126)
        for rgb in (cell.fg, cell.bg):
            self.assertIsInstance(rgb, tuple)
            self.assertEqual(len(rgb), 3)
            self.assertTrue(all(type(c) is int and 0 <= c <= 255 for c in rgb))

    def test_valid_output_for_every_generated_building_all_faces_and_seeds(self):
        styles, glyphs, colors = set(), set(), set()
        for seed in (11, 93, 2026, -1):
            city = CityGenerator().generate(seed).city
            for b in city.buildings:
                styles.add(b.style)
                r = b.footprint
                for face in ("south", "north", "east", "west"):
                    span = r.xmax-r.xmin if face in ("north", "south") else r.zmax-r.zmin
                    for u in (.1, 1.5, span/2, span-.1):
                        for y in (.1, 1.7, 2.1, 2.65, 3.1, 4.2, b.height/2, b.height-3, b.height-.1):
                            cell = self.appearance.sample(city, wall_hit(b, u, y, face))
                            self.assertValid(cell)
                            glyphs.add(cell.glyph)
                            colors.add(cell.bg)
                for face in ("roof", "ground"):
                    cell = self.appearance.sample(city, RayHit(1, Vec3(r.xmin+.25, b.height if face == "roof" else 0, r.zmin+.25),
                                                               NORMALS[face], face, b.id))
                    self.assertValid(cell)
        self.assertEqual(styles, set(PALETTES))
        self.assertGreaterEqual(len(glyphs), 14)
        self.assertGreaterEqual(len(colors), 20)

    def test_stable_under_distance_order_new_instance_and_subpixel_movement(self):
        city, b = fixture()
        hits = [wall_hit(b, u, y, face) for face in ("south", "north", "east", "west")
                for u in (1.3, 4.3, 7.3, 10.3) for y in (4.2, 7.2, 10.2)]
        expected = [self.appearance.sample(city, hit) for hit in hits]
        for i in reversed(range(len(hits))):
            hit = hits[i]
            self.assertEqual(self.appearance.sample(city, replace(hit, distance=499)), expected[i])
            self.assertEqual(FacadeAppearance().sample(city, hit), expected[i])
            p = replace(hit.point, y=hit.point.y+.000001)
            self.assertEqual(self.appearance.sample(city, replace(hit, point=p)), expected[i])

    def test_window_rhythm_in_metres_not_building_height_or_width(self):
        for span in (9, 12, 19, 34):
            for height in (12, 30, 99, 120):
                city, b = fixture(span=span, height=height)
                palette = PALETTES[b.style]
                # Detect physical glazing intervals without using implementation bay math.
                glazed = []
                for i in range(int(span*100)):
                    u = (i+.5)/100
                    cell = self.appearance.sample(city, wall_hit(b, u, 4.2))
                    if cell.bg == palette.dark:
                        glazed.append(u)
                starts = [u for i, u in enumerate(glazed) if i == 0 or u-glazed[i-1] > .011]
                ends = [u for i, u in enumerate(glazed) if i == len(glazed)-1 or glazed[i+1]-u > .011]
                self.assertGreaterEqual(len(starts), 2)
                centers = [(a+z)/2 for a, z in zip(starts, ends)]
                for a, z in zip(centers, centers[1:]):
                    self.assertTrue(1.99 <= z-a <= 4.01)
                u = centers[0]
                for floor in range(1, int(height/3)-1):
                    self.assertEqual(self.appearance.sample(city, wall_hit(b, u, floor*3+.79)).bg,
                                     self.appearance.sample(city, wall_hit(b, u, floor*3+2.36)).bg)
                    for y in (floor*3+.81, floor*3+1.5, floor*3+2.34):
                        self.assertEqual(self.appearance.sample(city, wall_hit(b, u, y)).bg, palette.dark)
                    self.assertEqual(self.appearance.sample(city, wall_hit(b, u, floor*3+.1)).glyph, "-")

    def test_human_door_lintel_sign_corners_roof_and_height_independence(self):
        for height in (12, 99, 120):
            city, b = fixture(height=height)
            for face in ("south", "north", "east", "west"):
                for y in (.1, 1.7, 2.099):
                    self.assertEqual(self.appearance.sample(city, wall_hit(b, 6.3, y, face)).glyph, "#")
                self.assertEqual(self.appearance.sample(city, wall_hit(b, 6.3, 2.1, face)).glyph, "=")
                self.assertEqual(self.appearance.sample(city, wall_hit(b, 6.3, 2.65, face)).fg, (104, 218, 225))
                self.assertEqual(self.appearance.sample(city, wall_hit(b, .1, 4.2, face)).glyph, "|")
                self.assertEqual(self.appearance.sample(city, wall_hit(b, 6.3, height-.1, face)).glyph, "=")
            roof = RayHit(1, Vec3(-23.9, height, -20), NORMALS["roof"], "roof", b.id)
            self.assertEqual(self.appearance.sample(city, roof).glyph, "=")
            self.assertEqual(self.appearance.sample(city, replace(roof, point=Vec3(-20.5, height, -20.5))).glyph, ".")

    def test_panes_have_one_occupancy_and_sparse_lighting(self):
        city, b = fixture(height=99, span=30)
        p = PALETTES[b.style]
        windows = []
        for floor in range(1, 30):
            for i in range(300):
                u = (i+.5)/10
                cell = self.appearance.sample(city, wall_hit(b, u, floor*3+1.2))
                if cell.bg == p.dark:
                    windows.append(cell.fg == p.window)
                    self.assertEqual(cell, self.appearance.sample(city, wall_hit(b, u, floor*3+2.2)))
        self.assertTrue(.2 < sum(windows)/len(windows) < .65)

    def test_building_variation_district_cohesion_and_floor_corner_continuity(self):
        signatures = set()
        for seed in range(12):
            city, b = fixture(seed=seed)
            samples = tuple(self.appearance.sample(city, wall_hit(b, u, y))
                            for y in (4.2, 7.2, 10.2) for u in (1, 1.5, 2, 2.5, 3, 4, 5))
            signatures.add(samples)
            p = PALETTES[b.style]
            for sample in samples:
                if sample.bg != p.dark:
                    self.assertTrue(all(abs(a-z) <= 8 for a, z in zip(sample.bg, p.wall)))
            bands = [self.appearance.sample(city, wall_hit(b, 1, 6.1, f))
                     for f in ("south", "north", "east", "west")]
            self.assertEqual(len(set(bands)), 1)
        self.assertGreaterEqual(len(signatures), 8)
        self.assertEqual(len({p.wall for p in PALETTES.values()}), 5)
        with self.assertRaises(TypeError):
            PALETTES["new"] = NEUTRAL

    def test_landmarks_distinct_and_driven_by_membership_not_id(self):
        glyph_signatures = set()
        for style in PALETTES:
            city, b = fixture(style=style, height=90, landmark=True)
            # Same custom id across all; none has the generated landmark-N naming.
            crown = tuple(self.appearance.sample(city, wall_hit(b, u/4, 86)).glyph for u in range(48))
            glyph_signatures.add(crown)
            ordinary = replace(city, landmarks=())
            self.assertNotEqual(self.appearance.sample(city, wall_hit(b, 1.1, 86)),
                                self.appearance.sample(ordinary, wall_hit(b, 1.1, 86)))
        self.assertEqual(len(glyph_signatures), 5)
        city, b = fixture(style="violet-artdeco", height=90, landmark=True)
        for u, y, glyph in ((8.5, 45, "O"), (6, 46, "|"), (7, 45, "-")):
            self.assertEqual(self.appearance.sample(city, wall_hit(b, u, y)).glyph, glyph)

    def test_cache_uses_city_identity_not_seed_or_building_id(self):
        a, b = fixture()
        other, c = fixture(style="cyan-glass")
        self.assertEqual(a.seed, other.seed)
        self.assertEqual(b.id, c.id)
        hit = wall_hit(b, 2, 4.2)
        before = self.appearance.sample(a, hit)
        self.assertNotEqual(before, self.appearance.sample(other, hit))
        self.assertEqual(before, self.appearance.sample(a, hit))
        self.assertEqual(before, self.appearance.sample(replace(a, buildings=tuple(reversed(a.buildings))), hit))

    def test_translation_and_negative_coordinates_preserve_facade(self):
        city, b = fixture()
        r = b.footprint
        moved = replace(b, footprint=Rect(r.xmin+48, r.zmin+24, r.xmax+48, r.zmax+24))
        other = replace(city, buildings=(moved,))
        for u in (.1, 1.2, 2.2, 6.3, 10.4):
            for y in (1.7, 4.2, 7.2, 29.9):
                for face in ("north", "south", "east", "west"):
                    self.assertEqual(self.appearance.sample(city, wall_hit(b, u, y, face)),
                                     self.appearance.sample(other, wall_hit(moved, u, y, face)))

    def test_ground_paving_scale_boundary_and_fallback_material(self):
        city, b = fixture(style="custom-unknown")
        sample = self.appearance.sample(city, wall_hit(b, 2, 4.2))
        self.assertValid(sample)
        def ground(x, z):
            return self.appearance.sample(city, RayHit(1, Vec3(x, 0, z), NORMALS["ground"], "ground", None))
        self.assertEqual(ground(-5.7, -5.6), ground(.3, .4))
        self.assertEqual(ground(2.01, 1.5).glyph, "+")
        self.assertEqual(ground(2.10, 1.5).glyph, ".")
        for p in ((99.8, 0), (-99.8, 0), (0, 99.8), (0, -99.8)):
            self.assertEqual(ground(*p).glyph, "=")

    def test_invalid_hits_fail_clearly(self):
        city, b = fixture()
        hit = wall_hit(b, 2, 4.2)
        for invalid in (replace(hit, building_id="absent"), replace(hit, building_id=None),
                        replace(hit, face="sky"), replace(hit, point=Vec3(math.nan, 0, 0)),
                        replace(hit, point=Vec3(0, math.inf, 0))):
            with self.assertRaises(ValueError):
                self.appearance.sample(city, invalid)

    def test_real_spatial_hits_all_faces_ground_and_landmark_viewpoints(self):
        city, b = fixture()
        world = SpatialWorld(city)
        for eye, d, expected in ((Vec3(-18, 5, -30), Vec3(0, 0, 1), "south"),
                                 (Vec3(-18, 5, -6), Vec3(0, 0, -1), "north"),
                                 (Vec3(-30, 5, -18), Vec3(1, 0, 0), "west"),
                                 (Vec3(-6, 5, -18), Vec3(-1, 0, 0), "east"),
                                 (Vec3(-18, 40, -18), Vec3(0, -1, 0), "roof"),
                                 (Vec3(0, 1.7, 0), Vec3(0, -1, 0), "ground")):
            hit = world.raycast(eye, d, 100)
            self.assertEqual(hit.face, expected)
            self.assertValid(self.appearance.sample(world.city, hit))
        for seed in (11, 93, 2026):
            world = CityGenerator().generate(seed)
            for landmark in world.city.landmarks:
                a, z = landmark.viewpoint, landmark.target
                length = math.dist((a.x, a.y, a.z), (z.x, z.y, z.z))
                d = Vec3((z.x-a.x)/length, (z.y-a.y)/length, (z.z-a.z)/length)
                hit = world.raycast(a, d, length+.05)
                self.assertEqual(hit.building_id, landmark.building_id)
                self.assertValid(self.appearance.sample(world.city, hit))

    def test_fixture_regeneration_and_every_serialized_cell_valid(self):
        artifacts = generate(11)
        for name, content in artifacts.items():
            self.assertEqual((ROOT/"docs"/"appearance-fixtures"/name).read_bytes(), content.encode())
        data = json.loads(artifacts["atlas.json"])
        self.assertIn("COMPONENT PREVIEW ONLY", data["label"])
        for c in data["cell_table"]:
            self.assertValid(Cell(c["glyph"], tuple(c["fg"]), tuple(c["bg"])))
        for p in data["panels"]:
            self.assertEqual(len(p["cells"]), p["rows"])
            self.assertTrue(all(len(line) == p["columns"] for line in p["cells"]))
            self.assertTrue(all(0 <= i < len(data["cell_table"]) for line in p["cells"] for i in line))
        self.assertEqual(hashlib.sha256(artifacts["atlas.json"].encode()).hexdigest(),
                         "42caa8811d2a2cde524c615efb03f6994e4617a8e30eb2d30dcf826cc360734c")

    def test_html_preview_contains_exact_sampled_glyphs_and_rgb(self):
        artifacts = generate(11)
        data = json.loads(artifacts["atlas.json"])
        class AtlasParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.panels, self.active = [], False
            def handle_starttag(self, tag, attrs):
                if tag == "pre":
                    self.panels.append("")
                    self.active = True
            def handle_endtag(self, tag):
                if tag == "pre":
                    self.active = False
            def handle_data(self, text):
                if self.active:
                    self.panels[-1] += text
        parser = AtlasParser()
        parser.feed(artifacts["atlas.html"])
        expected = ["".join("".join(data["cell_table"][i]["glyph"] for i in row)+"\n" for row in p["cells"])
                    for p in data["panels"]]
        self.assertEqual(parser.panels, expected)
        for i, cell in enumerate(data["cell_table"]):
            css = ".c"+str(i)+"{color:rgb"+str(tuple(cell["fg"]))+";background:rgb"+str(tuple(cell["bg"]))+"}"
            self.assertIn(css, artifacts["atlas.html"])

    def test_process_hash_independence_and_seed_variation(self):
        code = 'import hashlib; from tools.preview_appearance import generate; print(hashlib.sha256(generate(11)["atlas.json"].encode()).hexdigest())'
        outputs = []
        for seed in ("1", "917"):
            run = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                                 env=dict(os.environ, PYTHONHASHSEED=seed), timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            outputs.append(run.stdout.strip())
        self.assertEqual(outputs, ["42caa8811d2a2cde524c615efb03f6994e4617a8e30eb2d30dcf826cc360734c"]*2)
        # Strip metadata: require actual sampled materials, not merely a different seed label.
        a, b = (json.loads(generate(seed)["atlas.json"]) for seed in (11, 93))
        self.assertNotEqual(a["cell_table"], b["cell_table"])


if __name__ == "__main__":
    unittest.main()
