"""Rules with actual world, collision, projection and renderer-produced sightings."""
from dataclasses import replace
import math
import unittest

from citywalk.camera import Perspective, camera_from_player
from citywalk.contracts import Actions, Player, Vec3, Viewport
from citywalk.gameplay import SurveyRules
from citywalk.rendering import CityRenderer
from citywalk.spatial import CityGenerator
from tools.simulate_survey import simulate, replay


class GameplayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = CityGenerator().generate(11)

    def test_complete_seeded_collision_checked_route_and_action_only_reset_replay(self):
        record = simulate(11)
        summary = replay(record)
        self.assertEqual(summary["final_state"]["phase"], "won")
        self.assertEqual(summary["final_state"]["score"], 420)
        self.assertEqual(len(summary["final_state"]["photos"]), 3)
        self.assertLessEqual(summary["elapsed_s"], 420)
        self.assertGreater(summary["distance_m"], 800)
        self.assertEqual(summary["blocked_steps"], 0)
        self.assertLessEqual(summary["depot_distance_m"], 3)
        self.assertEqual(len(summary["events"]), 4)
        self.assertTrue(all(0 < dt <= .1 for dt, _ in record["tape"]))

    def test_all_five_real_viewpoints_work_at_minimum_and_recommended_scene_sizes(self):
        renderer = CityRenderer(Perspective())
        rules = SurveyRules()
        for viewport in (Viewport(80, 20), Viewport(100, 32)):
            for landmark in self.world.city.landmarks:
                # Explicit pose fixture, NOT the route-reachability proof above.
                player = Player(replace(landmark.viewpoint, y=0), landmark.view_yaw, landmark.view_pitch)
                self.assertTrue(self.world.walkable(player.feet, .3))
                sightings = renderer.sightings(self.world, camera_from_player(player), viewport)
                result = rules.step(self.world.city, rules.start(self.world.city), player,
                                     Actions(shutter=True), sightings, .1)
                self.assertEqual(result.state.photos, ((landmark.id, 140),))

    def test_real_projection_rejection_and_crown_upgrade_from_framing(self):
        projection = Perspective()
        renderer = CityRenderer(projection)
        rules = SurveyRules()
        viewport = Viewport(100, 32)
        landmark = self.world.city.landmarks[2]
        feet = replace(landmark.viewpoint, y=0)
        state = rules.start(self.world.city)
        # Find a real low composition: facade inside frame, crown outside it.
        low = None
        for degree in range(61):
            player = Player(feet, 0, math.radians(degree))
            sightings = renderer.sightings(self.world, camera_from_player(player), viewport)
            target = next(s for s in sightings if s.landmark_id == landmark.id)
            if target.visible and not target.crown_visible:
                low = player, sightings
                break
        self.assertIsNotNone(low, "generator/renderer no longer has tested composition tradeoff")
        player, sightings = low
        base = rules.step(self.world.city, state, player, Actions(shutter=True), sightings, .1)
        self.assertEqual(base.state.photos, ((landmark.id, 100),))
        player = Player(feet, 0, landmark.view_pitch)
        sightings = renderer.sightings(self.world, camera_from_player(player), viewport)
        upgraded = rules.step(self.world.city, base.state, player, Actions(shutter=True), sightings, .1)
        self.assertEqual(upgraded.state.photos, ((landmark.id, 140),))
        self.assertIn("+40", upgraded.messages[0])
        # Target geometry is unchanged but looking down clips its projection.
        player = replace(player, pitch=-math.pi/3)
        camera = camera_from_player(player)
        self.assertIsNone(projection.project(landmark.target, camera, viewport))
        sightings = renderer.sightings(self.world, camera, viewport)
        target = next(s for s in sightings if s.landmark_id == landmark.id)
        self.assertFalse(target.visible)
        self.assertLessEqual(abs(target.bearing_error), math.radians(12))
        self.assertTrue(18 <= target.range_m <= 65)
        missed = rules.step(self.world.city, state, player, Actions(shutter=True), sightings, .1)
        self.assertEqual(missed.state.score, 0)
        self.assertIn("occluded or outside", missed.messages[0])


if __name__ == "__main__":
    unittest.main()
