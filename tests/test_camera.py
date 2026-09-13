"""Independent numeric geometry checks, plus real City/RayHit consumption."""
from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path
import random
import unittest

from citywalk.camera import Perspective, camera_from_player
from citywalk.contracts import Camera, Player, Projection, Vec3, Viewport
from citywalk.spatial import CityGenerator


def xyz(v):
    return v.x, v.y, v.z


def along(eye, d, length):
    return Vec3(eye.x+d.x*length, eye.y+d.y*length, eye.z+d.z*length)


def rotate(v, yaw, pitch=0):
    # Independent sequential rotations: positive pitch tilts +z toward +y,
    # then yaw rotates +z toward +x. Not using the implementation basis.
    x = v.x
    y = v.y*math.cos(pitch) + v.z*math.sin(pitch)
    z = -v.y*math.sin(pitch) + v.z*math.cos(pitch)
    return Vec3(x*math.cos(yaw)+z*math.sin(yaw), y,
                -x*math.sin(yaw)+z*math.cos(yaw))


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.projection: Projection = Perspective()
        self.camera = camera_from_player(Player(Vec3(0, 0, 0)))
        self.viewport = Viewport(100, 32)
        self.p = self.projection.prepare(self.camera, self.viewport)

    def assertVector(self, a, b, places=10):
        for actual, expected in zip(xyz(a), xyz(b)):
            self.assertAlmostEqual(actual, expected, places=places)

    def test_eye_height_defaults_pose_normalization_and_no_mutation(self):
        player = Player(Vec3(-13, 0, 21), -math.pi/2, 2)
        camera = camera_from_player(player)
        self.assertEqual(camera.eye, Vec3(-13, 1.7, 21))
        self.assertEqual(camera.yaw, 3*math.pi/2)
        self.assertEqual(camera.pitch, math.pi/3)
        self.assertEqual(player.pitch, 2)
        self.assertEqual((camera.hfov, camera.near, camera.far), (math.radians(80), .1, 500))
        other = camera_from_player(replace(player, pitch=-2), hfov=1, near=.2, far=200)
        self.assertEqual((other.pitch, other.hfov, other.near, other.far), (-math.pi/3, 1, .2, 200))
        with self.assertRaises(FrozenInstanceError):
            camera.eye = Vec3(0, 4, 0)
        with self.assertRaises(FrozenInstanceError):
            self.p.vfov = 1

    def test_default_and_cardinal_heading_basis(self):
        self.assertVector(self.p.forward, Vec3(0, 0, 1))
        self.assertVector(self.p.right, Vec3(1, 0, 0))
        self.assertVector(self.p.up, Vec3(0, 1, 0))
        for yaw, f in ((0, Vec3(0, 0, 1)), (math.pi/2, Vec3(1, 0, 0)),
                       (math.pi, Vec3(0, 0, -1)), (3*math.pi/2, Vec3(-1, 0, 0))):
            p = self.projection.prepare(replace(self.camera, yaw=yaw), self.viewport)
            self.assertVector(p.forward, f)
            center = p.project(along(self.camera.eye, f, 20))
            self.assertAlmostEqual(center.column, 50)
            self.assertAlmostEqual(center.row, 16)
            right = p.project(along(along(self.camera.eye, f, 20), p.right, 2))
            self.assertGreater(right.column, center.column)

    def test_pitch_orthonormal_basis_and_clamp_for_direct_camera(self):
        for yaw in (0, -5e-324, .37, math.pi/2, 5.2, -math.tau, 10*math.tau+.3):
            for pitch in (-10, -math.pi/3, -.4, 0, .6, math.pi/3, 10):
                p = self.projection.prepare(replace(self.camera, yaw=yaw, pitch=pitch), self.viewport)
                self.assertTrue(0 <= p.camera.yaw < math.tau)
                self.assertTrue(-math.pi/3 <= p.camera.pitch <= math.pi/3)
                basis = (p.right, p.up, p.forward)
                for i, a in enumerate(basis):
                    for j, b in enumerate(basis):
                        self.assertAlmostEqual(sum(x*y for x, y in zip(xyz(a), xyz(b))), int(i == j))
                self.assertVector(p.forward, rotate(Vec3(0, 0, 1), yaw, p.camera.pitch))
        look_up = self.projection.prepare(replace(self.camera, pitch=.4), self.viewport)
        self.assertGreater(look_up.project(Vec3(0, 1.7, 20)).row, 16)
        self.assertGreater(look_up.ray(50, 16).y, 0)

    def test_fov_physical_aspect_and_known_numeric_projection(self):
        self.assertAlmostEqual(self.p.focal_columns, 59.5876796297105)
        self.assertAlmostEqual(self.p.focal_rows, 29.79383981485525)
        a = 100*.5/32
        self.assertAlmostEqual(self.p.vfov, 2*math.atan(math.tan(math.radians(40))/a))
        q = self.p.project(Vec3(2, 3.7, 20))
        self.assertAlmostEqual(q.column, 55.95876796297105)
        self.assertAlmostEqual(q.row, 13.020616018514476)
        self.assertEqual(q.depth, 20)
        for fov in (30, 60, 80, 120):
            p = self.projection.prepare(replace(self.camera, hfov=math.radians(fov)), self.viewport)
            edge = 10*math.tan(math.radians(fov/2))
            self.assertAlmostEqual(p.project_unclipped(Vec3(edge, 1.7, 10)).column, 100)
            self.assertIsNotNone(p.project(Vec3(edge*(1-1e-8), 1.7, 10)))
            self.assertIsNone(p.project(Vec3(edge*(1+1e-8), 1.7, 10)))
        narrow = self.projection.prepare(replace(self.camera, hfov=.7), self.viewport)
        self.assertGreater(narrow.project_unclipped(Vec3(2, 1.7, 20)).column, q.column)

    def test_square_world_proportions_cell_aspect_resize_and_scene_only_rows(self):
        for viewport in (Viewport(100, 32, .5), Viewport(100, 32, 1),
                         Viewport(80, 20, .4), Viewport(1, 1, .5), Viewport(200, 64, .5)):
            p = self.projection.prepare(self.camera, viewport)
            a = p.project_unclipped(Vec3(0, 1.7, 20))
            b = p.project_unclipped(Vec3(2, 3.7, 20))
            self.assertAlmostEqual((b.column-a.column)*viewport.cell_aspect, a.row-b.row)
            self.assertEqual(a.row, viewport.rows/2)  # no hidden HUD subtraction
        square = self.projection.prepare(self.camera, Viewport(100, 32, 1))
        self.assertEqual(square.focal_columns, self.p.focal_columns)
        self.assertEqual(square.focal_rows, 2*self.p.focal_rows)
        self.assertLess(square.vfov, self.p.vfov)
        resized = self.projection.prepare(self.camera, Viewport(200, 64))
        self.assertEqual(resized.vfov, self.p.vfov)
        old, new = self.p.project(Vec3(2, 3.7, 20)), resized.project(Vec3(2, 3.7, 20))
        self.assertEqual((new.column, new.row), (old.column*2, old.row*2))

    def test_near_far_inclusive_behind_eye_and_just_outside(self):
        for depth in (.1, 500):
            self.assertEqual(self.p.project(Vec3(0, 1.7, depth)).depth, depth)
        for depth in (math.nextafter(.1, 0), math.nextafter(500, math.inf), 0, -.1, -50):
            self.assertIsNone(self.p.project(Vec3(0, 1.7, depth)))
            self.assertIsNone(self.p.project_unclipped(Vec3(0, 1.7, depth)))
        # Forward clip, not radial: an off-axis point >500 m away remains valid.
        self.assertIsNotNone(self.p.project(Vec3(100, 1.7, 500)))
        self.assertGreater(math.hypot(100, 500), 500)
        self.assertIsNone(self.p.project(Vec3(100, 1.7, .09)))

    def test_screen_half_open_boundaries_no_clamping(self):
        depth = self.p.focal_columns
        # Reuse focal depth to make exact boundary coordinates, avoiding tan roundoff.
        for point, col, row, inside in ((Vec3(-50, 1.7, depth), 0, 16, True),
                                       (Vec3(50, 1.7, depth), 100, 16, False),
                                       (Vec3(0, 33.7, depth), 50, 0, True),
                                       (Vec3(0, -30.3, depth), 50, 32, False)):
            q = self.p.project_unclipped(point)
            self.assertAlmostEqual(q.column, col)
            self.assertAlmostEqual(q.row, row)
            self.assertEqual(self.p.project(point) is not None, inside)

    def test_perspective_shrinkage_and_depth_ordering_inputs(self):
        a, b = (self.p.project(Vec3(2, 3.7, z)) for z in (20, 40))
        self.assertAlmostEqual(a.column-50, 2*(b.column-50))
        self.assertAlmostEqual(16-a.row, 2*(16-b.row))
        self.assertEqual((a.depth, b.depth), (20, 40))
        # Collinear points have identical screen positions but retain depth.
        d = self.p.ray(83, 11)
        near, far = (self.p.project(along(self.camera.eye, d, t)) for t in (30, 60))
        self.assertAlmostEqual(near.column, far.column)
        self.assertAlmostEqual(near.row, far.row)
        self.assertAlmostEqual(far.depth, near.depth*2)
        self.assertLess(near.depth, 30)  # Projected.depth is NOT Frame.depth.

    def test_all_cell_center_roundtrips_and_unit_rays_multiple_poses(self):
        for viewport in (Viewport(1, 1), Viewport(7, 5), Viewport(80, 20), Viewport(100, 32)):
            for yaw, pitch in ((0, 0), (.73, .4), (math.pi/2, -math.pi/3), (5.9, math.pi/3)):
                camera = replace(self.camera, eye=Vec3(-97, 1.7, 125), yaw=yaw, pitch=pitch)
                p = self.projection.prepare(camera, viewport)
                for row in range(viewport.rows):
                    for col in range(viewport.columns):
                        d = p.ray(col, row)
                        self.assertAlmostEqual(math.hypot(*xyz(d)), 1)
                        q = p.project(along(camera.eye, d, 50))
                        self.assertAlmostEqual(q.column, col+.5, places=9)
                        self.assertAlmostEqual(q.row, row+.5, places=9)
        d = self.projection.ray(3, 2, self.camera, Viewport(7, 5))
        self.assertVector(d, Vec3(0, 0, 1))
        # Even dimensions have four central samples, not one special center cell.
        self.assertLess(self.p.ray(49, 15).x, 0)
        self.assertGreater(self.p.ray(50, 16).x, 0)

    def test_ray_clipping_distances_and_no_fisheye_on_flat_wall(self):
        for col in (0, 12, 49, 50, 87, 99):
            d = self.p.ray(col, 15)
            lo, hi = self.p.ray_clip_range(col, 15)
            self.assertAlmostEqual(lo*d.z, .1)
            self.assertAlmostEqual(hi*d.z, 500)
            wall_distance = 20/d.z
            q = self.p.project(along(self.camera.eye, d, wall_distance))
            self.assertAlmostEqual(q.depth, 20)  # Flat depth, longer edge rays.
            self.assertAlmostEqual(q.column, col+.5)
        self.assertGreater(self.p.ray_clip_range(0, 0)[1], self.p.ray_clip_range(49, 15)[1])
        for yaw, pitch in ((.7, .6), (4.9, -math.pi/3)):
            p = self.projection.prepare(replace(self.camera, yaw=yaw, pitch=pitch), self.viewport)
            for col, row in ((0, 0), (50, 16), (99, 31)):
                d = p.ray(col, row)
                lo, hi = p.ray_clip_range(col, row)
                cosine = sum(x*y for x, y in zip(xyz(d), xyz(p.forward)))
                self.assertAlmostEqual(lo*cosine, .1)
                self.assertAlmostEqual(hi*cosine, 500)
                for distance, visible in ((lo*(1-1e-8), False), (lo*(1+1e-8), True),
                                          (hi*(1-1e-8), True), (hi*(1+1e-8), False)):
                    self.assertEqual(p.project(along(self.camera.eye, d, distance)) is not None, visible)
        # Rectilinear rays: camera-space x/z changes linearly across columns.
        ratios = [self.p.ray(col, 15).x/self.p.ray(col, 15).z for col in (0, 25, 50, 75)]
        for a, b in zip(ratios, ratios[1:]):
            self.assertAlmostEqual(b-a, 25/self.p.focal_columns)

    def test_rotation_translation_covariance_and_straight_edges(self):
        rng = random.Random(4)
        for _ in range(100):
            yaw, pitch = rng.uniform(-6, 6), rng.uniform(-1, 1)
            eye = Vec3(rng.uniform(-240, 240), 1.7, rng.uniform(-240, 240))
            p = self.projection.prepare(replace(self.camera, eye=eye, yaw=yaw, pitch=pitch), self.viewport)
            for local in (Vec3(-3, -1, 20), Vec3(0, 0, 30), Vec3(5, 4, 40)):
                q = p.project(along(eye, rotate(local, yaw, pitch), 1))
                expected = self.p.project(along(self.camera.eye, local, 1))
                for key in ("column", "row", "depth"):
                    self.assertAlmostEqual(getattr(q, key), getattr(expected, key), places=9)
        # Looking around a fixed facade moves the whole geometry, without bending lines.
        for yaw in (-.2, 0, .2):
            p = self.projection.prepare(replace(self.camera, yaw=yaw, pitch=.25), self.viewport)
            a, b, c = (p.project_unclipped(Vec3(x, 8, 30)) for x in (-6, 0, 6))
            cross = (b.column-a.column)*(c.row-a.row)-(b.row-a.row)*(c.column-a.column)
            self.assertAlmostEqual(cross, 0)
        fixed = Vec3(0, 1.7, 20)
        cols = [self.projection.project(fixed, replace(self.camera, yaw=yaw), self.viewport).column
                for yaw in (-.2, 0, .2)]
        self.assertGreater(cols[0], cols[1])
        self.assertGreater(cols[1], cols[2])

    def test_human_scale_near_tower_above_frame_look_up_reveals_crown(self):
        base, top = Vec3(0, 0, 20), Vec3(0, 100, 20)
        self.assertGreater(self.p.project(base).row, 16)
        self.assertLess(self.p.project_unclipped(top).row, 0)
        self.assertIsNone(self.p.project(top))
        up = self.projection.prepare(replace(self.camera, pitch=math.pi/3), self.viewport)
        self.assertIsNotNone(up.project(top))
        self.assertIsNone(up.project(base))
        # Same 100 m tower fits vertically from 200 m, without scaling its height.
        self.assertIsNotNone(self.p.project(Vec3(0, 100, 200)))

    def test_real_city_landmark_targets_projection_and_rayhit_depth(self):
        for seed in (11, 93, 2026):
            w = CityGenerator().generate(seed)
            for l in w.city.landmarks:
                camera = Camera(l.viewpoint, l.view_yaw, l.view_pitch)
                p = self.projection.prepare(camera, Viewport(101, 33))
                target = p.project(l.target)
                self.assertAlmostEqual(target.column, 50.5)
                self.assertAlmostEqual(target.row, 16.5)
                ray = p.ray(50, 16)
                hit = w.raycast(camera.eye, ray, p.ray_clip_range(50, 16)[1])
                self.assertEqual(hit.building_id, l.building_id)
                self.assertVector(hit.point, l.target)
                self.assertAlmostEqual(p.project(hit.point).depth, hit.distance)
                self.assertEqual(camera.eye.y, 1.7)
                b = next(b for b in w.city.buildings if b.id == l.building_id)
                level = self.projection.prepare(replace(camera, pitch=0), self.viewport)
                facade_top = Vec3(l.target.x, b.height, l.target.z)
                self.assertLess(level.project_unclipped(facade_top).row, 0)
                self.assertIsNone(level.project(facade_top))

    def test_invalid_poses_settings_dimensions_and_points(self):
        for name in ("yaw", "pitch", "hfov", "near", "far"):
            for bad in (math.nan, math.inf, -math.inf, True, "1"):
                with self.subTest(name=name, bad=bad), self.assertRaises(ValueError):
                    self.projection.prepare(replace(self.camera, **{name: bad}), self.viewport)
        for changes in ({"hfov": 0}, {"hfov": math.pi}, {"hfov": -1},
                        {"near": 0}, {"near": -1}, {"far": .1}, {"far": .01}):
            with self.assertRaises(ValueError):
                self.projection.prepare(replace(self.camera, **changes), self.viewport)
        for name in ("columns", "rows"):
            for bad in (0, -1, 1.5, True, math.inf, 10**400):
                with self.assertRaises(ValueError):
                    self.projection.prepare(self.camera, replace(self.viewport, **{name: bad}))
        for bad in (0, -1, math.nan, math.inf, True, "0.5"):
            with self.assertRaises(ValueError):
                self.projection.prepare(self.camera, replace(self.viewport, cell_aspect=bad))
        for axis in ("x", "y", "z"):
            for bad in (math.nan, math.inf, -math.inf):
                point = replace(self.camera.eye, **{axis: bad})
                with self.assertRaises(ValueError):
                    self.p.project(point)
                with self.assertRaises(ValueError):
                    self.projection.prepare(replace(self.camera, eye=point), self.viewport)
                with self.assertRaises(ValueError):
                    camera_from_player(Player(point))
        with self.assertRaises(ValueError):
            camera_from_player(Player(Vec3(0, .1, 0)))

    def test_invalid_ray_indices_and_unrepresentable_scales(self):
        for col, row in ((-1, 0), (100, 0), (0, -1), (0, 32), (.5, 0), (0, True), (math.nan, 0)):
            for method in (self.p.ray, self.p.ray_clip_range):
                with self.assertRaises(ValueError):
                    method(col, row)
        for camera, viewport in ((replace(self.camera, hfov=5e-324), self.viewport),
                                 (self.camera, replace(self.viewport, cell_aspect=5e-324)),
                                 (self.camera, replace(self.viewport, cell_aspect=1e308)),
                                 (replace(self.camera, far=1e308, hfov=3.14), self.viewport)):
            with self.assertRaises(ValueError):
                self.projection.prepare(camera, viewport)
        p = self.projection.prepare(replace(self.camera, eye=Vec3(-1e308, 0, 0)), self.viewport)
        with self.assertRaises(ValueError):
            p.project(Vec3(1e308, 0, 1))

    def test_reproducible_numeric_fixtures(self):
        from tools.measure_projection import generate
        expected = json.loads((Path(__file__).resolve().parents[1]/"docs/projection-fixtures.json").read_text())
        actual = generate()
        # Float trig fixtures: tolerance check allows different libm
        # final bits on Windows, unlike falsely requiring identical floating bytes.
        def check(a, b):
            if isinstance(a, dict):
                self.assertEqual(a.keys(), b.keys())
                for key in a:
                    check(a[key], b[key])
            elif isinstance(a, list):
                self.assertEqual(len(a), len(b))
                for x, y in zip(a, b):
                    check(x, y)
            elif type(a) is float:
                self.assertAlmostEqual(a, b, delta=1e-8)
            else:
                self.assertEqual(a, b)
        check(actual, expected)
        # Replay the serialized inputs themselves, not only the generation code.
        viewport = Viewport(**expected["viewport"])
        def replay(camera_data, probes):
            camera = Camera(**dict(camera_data, eye=Vec3(**camera_data["eye"])))
            p = self.projection.prepare(camera, viewport)
            for probe in probes:
                point = Vec3(**probe["point"])
                for key, method in (("project", p.project), ("screen_unclipped", p.project_unclipped)):
                    result = method(point)
                    if probe[key] is None:
                        self.assertIsNone(result)
                    else:
                        self.assertIsNotNone(result)
                        for axis, value in probe[key].items():
                            self.assertAlmostEqual(getattr(result, axis), value, delta=1e-8)
        replay(expected["camera"], expected["probes"])
        for pose in expected["tower_poses"]:
            replay(pose["camera"], pose["corners"] + [pose["base"], pose["crown"]])
        for landmark in expected["landmarks"]:
            replay(landmark["camera"], [landmark["target"], landmark["crown"]])


if __name__ == "__main__":
    unittest.main()
