"""Injected-action movement tests: real city queries, no keyboard or terminal."""
from dataclasses import replace
import math
import random
import unittest

from citywalk.camera import camera_from_player
from citywalk.contracts import Actions, Building, City, Movement, Player, Rect, Vec3
from citywalk.movement import Walker
from citywalk.spatial import CityGenerator, SpatialWorld

SEEDS = (11, 93, 2026)
PADDING = 0.300001


def fixture(*rects, spawn=Vec3(-2, 0, -2), bounds=Rect(-100, -100, 100, 100)):
    buildings = tuple(Building(str(i), r, 10, "amber-brick", i)
                      for i, r in enumerate(rects))
    return SpatialWorld(City(0, bounds, buildings, (), spawn, spawn))


def independently_clear(city, a, b):
    # Only axis sweeps: interval-to-rectangle distance, independently of the
    # production general segment/corner algorithm and spatial index.
    if a.x != b.x and a.z != b.z:
        raise AssertionError("expected an axis-aligned movement sweep")
    xmin, xmax = sorted((a.x, b.x))
    zmin, zmax = sorted((a.z, b.z))
    bounds = city.bounds
    if not (a.y == b.y == 0 and bounds.xmin+PADDING < xmin and
            xmax < bounds.xmax-PADDING and bounds.zmin+PADDING < zmin and
            zmax < bounds.zmax-PADDING):
        return False
    for building in city.buildings:
        r = building.footprint
        dx = max(r.xmin-xmax, xmin-r.xmax, 0)
        dz = max(r.zmin-zmax, zmin-r.zmax, 0)
        if math.hypot(dx, dz) <= PADDING:
            return False
    return True


class AuditedSpatial:
    """Only shared protocol members; no concrete-world shortcuts for Walker."""
    def __init__(self, world):
        self._world = world
        self.city = world.city
        self.accepted = []

    def walkable(self, feet, radius):
        return self._world.walkable(feet, radius)

    def segment_clear(self, a, b, radius):
        if radius != 0.30:
            raise AssertionError("wrong player footprint")
        if math.hypot(b.x-a.x, b.z-a.z) > 0.100000000001:
            raise AssertionError("movement sweep exceeds design substep bound")
        result = self._world.segment_clear(a, b, radius)
        if result:
            self.accepted.append((a, b))
        return result

    def nearby(self, rect):
        return self._world.nearby(rect)

    def raycast(self, origin, direction, max_distance):
        return self._world.raycast(origin, direction, max_distance)


class MovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worlds = tuple(CityGenerator().generate(seed) for seed in SEEDS)

    def setUp(self):
        self.walker: Movement = Walker()
        self.world = self.worlds[0]

    def assertFeet(self, actual, expected, delta=1e-8):
        for name in ("x", "y", "z"):
            self.assertAlmostEqual(getattr(actual, name), getattr(expected, name), delta=delta)

    def advance(self, world, player, actions, dt, count=1):
        for _ in range(count):
            player = self.walker.step(world, player, actions, dt).player
        return player

    def test_safe_generated_spawns_depots_and_viewpoints_eye_height(self):
        for world in self.worlds:
            self.assertEqual(self.walker.spawn(world), Player(world.city.spawn))
            points = (world.city.spawn, world.city.depot) + tuple(
                replace(l.viewpoint, y=0) for l in world.city.landmarks)
            for feet in points:
                self.assertTrue(independently_clear(world.city, feet, feet))
                result = self.walker.step(world, Player(feet), Actions(), 0)
                self.assertFalse(result.blocked)
                self.assertEqual(camera_from_player(result.player).eye.y, 1.7)

    def test_invalid_spawn_and_invalid_existing_pose_fail_without_teleport(self):
        r = self.world.city.buildings[0].footprint
        for feet in (Vec3(r.xmin+1, 0, r.zmin+1), Vec3(r.xmin-.3, 0, r.zmin+1),
                     Vec3(240, 0, 0), Vec3(239.7, 0, 0), Vec3(0, 1.7, 0)):
            with self.assertRaises(ValueError):
                self.walker.spawn(SpatialWorld(replace(self.world.city, spawn=feet)))
            with self.assertRaises(ValueError):
                self.walker.step(self.world, Player(feet), Actions(forward=1), 0)

    def test_unobstructed_forward_backward_and_strafe_design_speed(self):
        for actions, end in ((Actions(forward=1), Vec3(0, 0, 4)),
                             (Actions(forward=-1), Vec3(0, 0, -4)),
                             (Actions(strafe=1), Vec3(4, 0, 0)),
                             (Actions(strafe=-1), Vec3(-4, 0, 0))):
            result = self.walker.step(self.world, self.walker.spawn(self.world), actions, 1)
            self.assertFalse(result.blocked)
            self.assertFeet(result.player.feet, end)
            self.assertFeet(self.advance(self.world, result.player,
                replace(actions, forward=-actions.forward, strafe=-actions.strafe), 1).feet,
                self.world.city.spawn)

    def test_cardinal_yaw_relative_forward_and_right(self):
        for yaw, f, r in ((0, (0, 4), (4, 0)), (math.pi/2, (4, 0), (0, -4)),
                           (math.pi, (0, -4), (-4, 0)), (3*math.pi/2, (-4, 0), (0, 4))):
            player = Player(self.world.city.spawn, yaw)
            for action, pair in ((Actions(forward=1), f), (Actions(strafe=1), r)):
                self.assertFeet(self.advance(self.world, player, action, 1).feet,
                                Vec3(pair[0], 0, pair[1]))

    def test_arbitrary_yaw_and_pitch_do_not_change_ground_speed(self):
        yaw = .713
        for pitch in (-math.pi/3, 0, math.pi/3):
            result = self.advance(self.world, Player(self.world.city.spawn, yaw, pitch),
                                  Actions(forward=1), 1)
            self.assertFeet(result.feet, Vec3(4*math.sin(yaw), 0, 4*math.cos(yaw)))
            self.assertEqual(camera_from_player(result).eye.y, 1.7)

    def test_normalized_diagonals_and_unsaturated_analog_input(self):
        for f, s in ((1, 1), (1, -1), (-1, 1), (-1, -1), (.3, .4), (.1, 0)):
            result = self.advance(self.world, Player(self.world.city.spawn),
                                  Actions(forward=f, strafe=s), 1)
            scale = max(1, math.hypot(f, s))
            self.assertFeet(result.feet, Vec3(4*s/scale, 0, 4*f/scale))
            self.assertAlmostEqual(math.hypot(result.feet.x, result.feet.z),
                                   4*min(1, math.hypot(f, s)))

    def test_stable_speed_at_20_60_120_hz_and_irregular_frames(self):
        initial = Player(self.world.city.spawn)
        for hz in (20, 60, 120):
            p = self.advance(self.world, initial, Actions(forward=1), 1/hz, 2*hz)
            self.assertFeet(p.feet, Vec3(0, 0, 8))
        p = initial
        for dt in (.01, .03, .16, .4, .1, .7, .6):
            p = self.advance(self.world, p, Actions(forward=1), dt)
        self.assertFeet(p.feet, Vec3(0, 0, 8))

    def test_turn_look_rates_wrap_clamp_and_reverse_at_limit(self):
        initial = Player(self.world.city.spawn)
        p = self.advance(self.world, initial, Actions(turn=1, look=1), .5)
        self.assertEqual(p.yaw, math.pi/4)
        self.assertEqual(p.pitch, math.pi/6)
        self.assertEqual(p.feet, initial.feet)
        p = self.advance(self.world, p, Actions(turn=-1, look=1), 5)
        self.assertTrue(0 <= p.yaw < math.tau)
        self.assertEqual(p.pitch, math.pi/3)
        p = self.advance(self.world, p, Actions(look=-1), .25)
        self.assertAlmostEqual(p.pitch, math.pi/4)
        p = self.advance(self.world, p, Actions(look=-1), 10)
        self.assertEqual(p.pitch, -math.pi/3)
        for yaw in (-5e-324, -1, 200*math.tau+.4):
            p = self.advance(self.world, Player(initial.feet, yaw, 2), Actions(), 0)
            self.assertTrue(0 <= p.yaw < math.tau)
            self.assertEqual(p.pitch, math.pi/3)

    def test_simultaneous_turn_walk_exact_arc_and_frame_rate_consistency(self):
        actions = Actions(forward=1, turn=1, look=.2)
        initial = Player(self.world.city.spawn)
        expected = Vec3(8/math.pi, 0, 8/math.pi)
        for hz in (1, 20, 60, 120):
            p = self.advance(self.world, initial, actions, 1/hz, hz)
            self.assertFeet(p.feet, expected)
            self.assertAlmostEqual(p.yaw, math.pi/2)
            self.assertAlmostEqual(p.pitch, math.pi/15)
        # General constant local diagonal velocity, including negative turn and
        # tiny angular rates: compare one long step against fine partitions.
        for turn in (-1, -.3, 1e-12):
            a = Actions(forward=.8, strafe=-.7, turn=turn)
            one = self.advance(self.world, replace(initial, yaw=.4), a, 1)
            many = self.advance(self.world, replace(initial, yaw=.4), a, 1/120, 120)
            self.assertFeet(one.feet, many.feet)
            self.assertAlmostEqual(one.yaw, many.yaw)

    def test_zero_dt_idle_immutability_and_unrelated_actions_are_not_ui_gates(self):
        player = Player(self.world.city.spawn, .2, .1)
        actions = Actions(forward=1, turn=1, look=1)
        self.assertEqual(self.walker.step(self.world, player, actions, 0).player, player)
        self.assertEqual(self.walker.step(self.world, player, Actions(), 120).player, player)
        flags = Actions(forward=1, shutter=True, interact=True, pause=True, help=True,
                        restart=True, new_seed=True, quit=True)
        self.assertEqual(self.walker.step(self.world, player, flags, .1),
                         self.walker.step(self.world, player, Actions(forward=1), .1))
        self.assertEqual(player, Player(self.world.city.spawn, .2, .1))
        self.assertEqual(actions, Actions(forward=1, turn=1, look=1))

    def test_invalid_dt_axes_and_nonfinite_pose(self):
        player = self.walker.spawn(self.world)
        for dt in (-1, math.nan, math.inf, -math.inf, True, "1", 10**400):
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                self.walker.step(self.world, player, Actions(), dt)
        for axis in ("forward", "strafe", "turn", "look"):
            for value in (-1.01, 1.01, math.nan, math.inf, True, "1", 10**400):
                with self.subTest(axis=axis, value=value), self.assertRaises(ValueError):
                    self.walker.step(self.world, player, replace(Actions(), **{axis: value}), .1)
        for value in (math.nan, math.inf, -math.inf, True, "1", 10**400):
            for axis in ("yaw", "pitch"):
                with self.assertRaises(ValueError):
                    self.walker.step(self.world, replace(player, **{axis: value}), Actions(), .1)
            for axis in ("x", "y", "z"):
                with self.assertRaises(ValueError):
                    self.walker.step(self.world, replace(player, feet=replace(player.feet,
                                     **{axis: value})), Actions(), .1)
        with self.assertRaises(ValueError):
            self.walker.step(self.world, player, Actions(forward=1), 1e308)

    def test_generated_building_entry_blocked_on_all_four_faces(self):
        for world in self.worlds:
            r = world.city.buildings[0].footprint
            mx, mz = (r.xmin+r.xmax)/2, (r.zmin+r.zmax)/2
            cases = ((Vec3(r.xmin-1, 0, mz), Actions(strafe=1), "x", r.xmin-PADDING),
                     (Vec3(r.xmax+1, 0, mz), Actions(strafe=-1), "x", r.xmax+PADDING),
                     (Vec3(mx, 0, r.zmin-1), Actions(forward=1), "z", r.zmin-PADDING),
                     (Vec3(mx, 0, r.zmax+1), Actions(forward=-1), "z", r.zmax+PADDING))
            for feet, action, axis, contact in cases:
                p = Player(feet)
                for _ in range(3):
                    result = self.walker.step(world, p, action, 1)
                    self.assertTrue(result.blocked)
                    self.assertAlmostEqual(getattr(result.player.feet, axis), contact, delta=1e-8)
                    self.assertTrue(independently_clear(world.city, result.player.feet, result.player.feet))
                    p = result.player

    def test_predictable_generated_wall_slide_preserves_tangent_not_full_speed(self):
        for world in self.worlds:
            r = world.city.buildings[0].footprint
            feet = Vec3(r.xmin-.5, 0, (r.zmin+r.zmax)/2)
            expected = Vec3(r.xmin-PADDING, 0, feet.z+4/math.sqrt(2))
            for hz in (1, 20, 60, 120):
                p = self.advance(world, Player(feet), Actions(forward=1, strafe=1), 1/hz, hz)
                self.assertFeet(p.feet, expected)
                self.assertTrue(world.walkable(p.feet, .3))
            back = self.advance(world, p, Actions(strafe=-1), .1)
            self.assertAlmostEqual(back.feet.x, p.feet.x-.4)

    def test_turn_and_look_continue_when_translation_is_blocked(self):
        r = self.world.city.buildings[0].footprint
        player = Player(Vec3(r.xmin-PADDING-1e-8, 0, (r.zmin+r.zmax)/2))
        result = self.walker.step(self.world, player, Actions(strafe=1, turn=1, look=1), .1)
        self.assertTrue(result.blocked)
        self.assertAlmostEqual(result.player.yaw, math.pi/20)
        self.assertAlmostEqual(result.player.pitch, math.pi/30)
        self.assertTrue(self.world.walkable(result.player.feet, .3))

    def test_generated_convex_corner_stops_repeatably_until_player_steers_away(self):
        for world in self.worlds:
            r = world.city.buildings[0].footprint
            p = Player(Vec3(r.xmin-1, 0, r.zmin-1))
            a = Actions(forward=1, strafe=1)
            result = self.walker.step(world, p, a, 1)
            self.assertEqual(result, self.walker.step(world, p, a, 1))
            self.assertTrue(result.blocked)
            # Axis-only sliding cannot roll around a rounded disc/box corner
            # while both requested axes point into it. Stop on the round corner;
            # a cardinal input away from it must release immediately.
            self.assertLess(result.player.feet.x, r.xmin)
            self.assertLess(result.player.feet.z, r.zmin)
            self.assertGreater(result.player.feet.x, p.feet.x)
            self.assertGreater(result.player.feet.z, p.feet.z)
            self.assertAlmostEqual(math.hypot(result.player.feet.x-r.xmin,
                                             result.player.feet.z-r.zmin), PADDING, delta=1e-8)
            self.assertTrue(independently_clear(world.city, result.player.feet, result.player.feet))
            escape = self.walker.step(world, result.player, Actions(forward=-1), .5)
            self.assertFalse(escape.blocked)
            self.assertAlmostEqual(escape.player.feet.z, result.player.feet.z-2)

    def test_disc_can_round_corner_where_square_footprint_would_block(self):
        world = fixture(Rect(0, 0, 5, 5))
        player = Player(Vec3(-.4, 0, -.22))
        result = self.walker.step(world, player, Actions(strafe=1), .045)
        self.assertFalse(result.blocked)
        self.assertFeet(result.player.feet, Vec3(-.22, 0, -.22))
        self.assertTrue(world.walkable(result.player.feet, .3))

    def test_concave_corner_stops_both_axes_without_jitter_or_penetration(self):
        world = fixture(Rect(0, -10, 5, 5), Rect(-10, 0, 0, 5))
        p = Player(Vec3(-1, 0, -1))
        a = Actions(forward=1, strafe=1)
        result = self.walker.step(world, p, a, 1)
        self.assertTrue(result.blocked)
        self.assertFeet(result.player.feet, Vec3(-PADDING, 0, -PADDING))
        held = self.advance(world, result.player, a, .05, 100)
        self.assertFeet(held.feet, result.player.feet, delta=1e-9)
        self.assertTrue(independently_clear(world.city, held.feet, held.feet))
        self.assertFalse(self.walker.step(world, held, Actions(forward=-1, strafe=-1), .1).blocked)

    def test_generated_world_boundaries_and_boundary_corner_slide(self):
        for start, a, end in ((Vec3(239, 0, 0), Actions(strafe=1), Vec3(240-PADDING, 0, 0)),
                              (Vec3(-239, 0, 0), Actions(strafe=-1), Vec3(-240+PADDING, 0, 0)),
                              (Vec3(0, 0, 239), Actions(forward=1), Vec3(0, 0, 240-PADDING)),
                              (Vec3(0, 0, -239), Actions(forward=-1), Vec3(0, 0, -240+PADDING)),
                              (Vec3(239, 0, 239), Actions(forward=1, strafe=1),
                               Vec3(240-PADDING, 0, 240-PADDING))):
            result = self.walker.step(self.world, Player(start), a, 1)
            self.assertTrue(result.blocked)
            self.assertFeet(result.player.feet, end)
            self.assertTrue(self.world.walkable(result.player.feet, .3))
        p = Player(Vec3(239, 0, 0))
        result = self.walker.step(self.world, p, Actions(forward=1, strafe=1), 1)
        self.assertFeet(result.player.feet, Vec3(240-PADDING, 0, 4/math.sqrt(2)))

    def test_one_second_and_long_frames_cannot_tunnel_through_generated_buildings(self):
        for world in self.worlds:
            r = world.city.buildings[0].footprint
            p = Player(Vec3(r.xmin-1, 0, (r.zmin+r.zmax)/2))
            # 20 s requests 80 m, enough to cross this actual generated block.
            for dt in (1, 5, 20):
                result = self.walker.step(world, p, Actions(strafe=1), dt)
                self.assertTrue(result.blocked)
                self.assertAlmostEqual(result.player.feet.x, r.xmin-PADDING, delta=1e-8)
                self.assertTrue(independently_clear(world.city, p.feet, result.player.feet))

    def test_long_open_street_uses_full_elapsed_time_then_blocks_at_bounds(self):
        p = self.walker.spawn(self.world)
        result = self.walker.step(self.world, p, Actions(forward=1), 30)
        self.assertFalse(result.blocked)
        self.assertFeet(result.player.feet, Vec3(0, 0, 120))
        result = self.walker.step(self.world, p, Actions(forward=1), 120)
        self.assertTrue(result.blocked)
        self.assertFeet(result.player.feet, Vec3(0, 0, 240-PADDING))

    def test_swept_disc_blocks_thin_obstacle_even_when_substep_endpoints_are_safe(self):
        world = fixture(Rect(0, 0, .001, 1))
        p = Player(Vec3(-.05, 0, -.29999))
        target = Vec3(.05, 0, -.29999)
        self.assertTrue(world.walkable(p.feet, .3))
        self.assertTrue(world.walkable(target, .3))
        self.assertFalse(world.segment_clear(p.feet, target, .3))
        result = self.walker.step(world, p, Actions(strafe=1), .025)
        self.assertTrue(result.blocked)
        self.assertLess(result.player.feet.x, 0)
        self.assertTrue(independently_clear(world.city, p.feet, result.player.feet))

    def test_finite_footprint_cannot_enter_point_passable_narrow_gap(self):
        world = fixture(Rect(-5, 0, -.25, 5), Rect(.25, 0, 5, 5))
        self.assertTrue(world.walkable(Vec3(0, 0, 1), 0))
        self.assertFalse(world.walkable(Vec3(0, 0, 1), .3))
        result = self.walker.step(world, Player(Vec3(0, 0, -1)), Actions(forward=1), 2)
        self.assertTrue(result.blocked)
        self.assertLess(result.player.feet.z, 0)
        self.assertTrue(world.walkable(result.player.feet, .3))

    def test_protocol_only_adapter_bounded_substeps_and_independent_sweep_oracle(self):
        for world in self.worlds:
            audited = AuditedSpatial(world)
            r = world.city.buildings[0].footprint
            p = Player(Vec3(r.xmin-1, 0, r.zmin-1))
            for a, dt in ((Actions(forward=1, strafe=1), 1),
                          (Actions(strafe=1, turn=.5), .4),
                          (Actions(forward=-1, strafe=-1), .2)):
                p = self.advance(audited, p, a, dt)
            self.assertGreater(len(audited.accepted), 50)
            for a, b in audited.accepted:
                self.assertTrue(independently_clear(world.city, a, b), (a, b))

    def test_seeded_action_fuzz_against_actual_city_geometry_is_deterministic(self):
        rng = random.Random(98)
        tape = [(Actions(forward=rng.choice((-1, 0, .5, 1)),
                         strafe=rng.choice((-1, 0, .5, 1)),
                         turn=rng.choice((-1, 0, .5, 1)), look=rng.choice((-1, 0, 1))),
                 rng.choice((0, .01, .025, .05, .2, 1))) for _ in range(200)]
        for world in self.worlds:
            r = world.city.buildings[0].footprint
            initial = Player(Vec3(r.xmin-1, 0, r.zmin-1))
            outcomes = []
            for _ in range(2):
                p = initial
                for a, dt in tape:
                    result = self.walker.step(world, p, a, dt)
                    p = result.player
                    self.assertTrue(independently_clear(world.city, p.feet, p.feet))
                    self.assertTrue(0 <= p.yaw < math.tau)
                    self.assertTrue(-math.pi/3 <= p.pitch <= math.pi/3)
                outcomes.append(p)
            self.assertEqual(outcomes[0], outcomes[1])


if __name__ == "__main__":
    unittest.main()
