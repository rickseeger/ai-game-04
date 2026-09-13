"""Rules fixtures exercise adversarial transitions; real routes are separate."""
from dataclasses import replace
from itertools import permutations
import math
import unittest

from citywalk.contracts import (Actions, City, Gameplay, Landmark, Player, Rect,
                                Sighting, SurveyState, Vec3)
from citywalk.gameplay import SurveyRules


def fixture(seed=11):
    origin = Vec3(0, 0, 0)
    landmarks = tuple(Landmark(key, key, name, "district", Vec3(0, 40, 30),
                      Vec3(0, 1.7, 0), 0, .5)
                      for key, name in zip("abcde", ("Amber", "Beacon", "Clock", "Rose", "Emerald")))
    return City(seed, Rect(-240, -240, 240, 240), (), landmarks, origin, origin)


def sight(key="a", **changes):
    return replace(Sighting(key, True, 30, 0, False), **changes)


class GameplayTests(unittest.TestCase):
    def setUp(self):
        self.rules: Gameplay = SurveyRules()
        self.city = fixture()
        self.player = Player(self.city.spawn)
        self.initial = self.rules.start(self.city)

    def step(self, state=None, actions=None, sightings=(), dt=0, player=None):
        return self.rules.step(self.city, state or self.initial, player or self.player,
                               actions or Actions(), sightings, dt)

    def collect(self, keys="abc", crown=False):
        state = self.initial
        for key in keys:
            state = self.step(state, Actions(shutter=True),
                              (sight(key, crown_visible=crown),), .5).state
        return state

    def test_start_idle_countdown_and_immutable_inputs(self):
        self.assertEqual(self.initial, SurveyState("playing", 600, (), 0))
        result = self.step(dt=12.5)
        self.assertEqual(result.state, SurveyState("playing", 587.5, (), 0))
        self.assertEqual(result.messages, ())
        self.assertEqual(self.initial.remaining_s, 600)
        self.assertEqual(self.step().state, self.initial)

    def test_success_requires_third_photo_and_explicit_submission(self):
        state = self.collect("ab")
        result = self.step(state, Actions(shutter=True), (sight("c"),), .5)
        self.assertEqual(result.state.phase, "playing")
        self.assertEqual(result.state.score, 300)
        self.assertIn("Survey ready", " ".join(result.messages))
        result = self.step(result.state, Actions(interact=True), dt=.5)
        self.assertEqual(result.state.phase, "won")
        self.assertEqual(result.state.remaining_s, 598)
        self.assertIn("300 points", " ".join(result.messages))

    def test_shutter_before_submission_same_tick(self):
        result = self.step(self.collect("ab"), Actions(shutter=True, interact=True),
                           (sight("c", crown_visible=True),), 1)
        self.assertEqual(result.state.phase, "won")
        self.assertEqual(result.state.score, 340)
        self.assertEqual(len(result.messages), 3)

    def test_exact_deadline_and_overshoot_lose_before_photo_or_submission(self):
        state = replace(self.collect("ab"), remaining_s=1)
        for dt in (1, 2, 600, 1e308):
            result = self.step(state, Actions(shutter=True, interact=True), (sight("c"),), dt)
            self.assertEqual(result.state, replace(state, phase="lost", remaining_s=0))
            self.assertIn("time expired", result.messages[0])
        ready = replace(self.collect(), remaining_s=1)
        self.assertEqual(self.step(ready, Actions(interact=True), dt=1).state.phase, "lost")
        before = self.step(ready, Actions(interact=True), dt=math.nextafter(1, 0))
        self.assertEqual(before.state.phase, "won")
        self.assertGreater(before.state.remaining_s, 0)
        self.assertEqual(self.step(replace(ready, remaining_s=0)).state.phase, "lost")

    def test_misses_and_failed_submissions_still_consume_full_active_time(self):
        result = self.step(actions=Actions(shutter=True, interact=True), dt=137)
        self.assertEqual(result.state.remaining_s, 463)
        self.assertEqual(result.state.photos, ())
        self.assertEqual(len(result.messages), 2)

    def test_premature_and_distant_submission_and_inclusive_depot_boundary(self):
        for keys in ("", "a", "ab"):
            result = self.step(self.collect(keys), Actions(interact=True), dt=.1)
            self.assertEqual(result.state.phase, "playing")
            self.assertIn("distinct landmarks", result.messages[0])
        state = self.collect()
        for feet, phase in ((Vec3(3, 0, 0), "won"), (Vec3(0, 0, -3), "won"),
                             (Vec3(math.nextafter(3, math.inf), 0, 0), "playing"),
                             (Vec3(3, 0, 3), "playing"), (Vec3(100, 0, 0), "playing")):
            result = self.step(state, Actions(interact=True), player=Player(feet))
            self.assertEqual(result.state.phase, phase)
        # Submission is relative to city depot, not world origin or spawn.
        city = replace(self.city, depot=Vec3(20, 0, 20))
        result = self.rules.step(city, state, self.player, Actions(interact=True), (), 0)
        self.assertEqual(result.state.phase, "playing")
        result = self.rules.step(city, state, Player(city.depot), Actions(interact=True), (), 0)
        self.assertEqual(result.state.phase, "won")

    def test_photo_gates_and_rejection_feedback(self):
        cases = (((), "no valid"), ((sight("unknown"),), "no valid"),
                 ((sight(visible=False, crown_visible=True),), "occluded or outside"),
                 ((sight(range_m=17.999),), "too near"),
                 ((sight(range_m=65.001),), "too far"),
                 ((sight(bearing_error=math.radians(12.001)),), "off-center"),
                 ((sight(bearing_error=-math.radians(12.001)),), "off-center"))
        for sightings, message in cases:
            with self.subTest(sightings=sightings):
                result = self.step(actions=Actions(shutter=True), sightings=sightings)
                self.assertEqual(result.state.photos, ())
                self.assertIn(message, result.messages[0])
        for distance in (18, 65):
            for error in (-math.radians(12), math.radians(12)):
                result = self.step(actions=Actions(shutter=True),
                                   sightings=(sight(range_m=distance, bearing_error=error),))
                self.assertEqual(result.state.score, 100)
        self.assertEqual(self.step(sightings=(sight(),)).state.score, 0)

    def test_nonfinite_sighting_geometry_cannot_bypass_gates(self):
        for field in ("range_m", "bearing_error"):
            for value in (math.nan, math.inf, -math.inf, True, "30", 10**400):
                with self.subTest(field=field, value=value):
                    result = self.step(actions=Actions(shutter=True),
                        sightings=(sight(**{field: value}),))
                    self.assertEqual(result.state.score, 0)

    def test_candidate_order_is_absolute_bearing_then_id_not_range_or_bonus(self):
        cases = ((sight("b", bearing_error=-.01), sight("a", bearing_error=.02)),
                 (sight("b", bearing_error=-.02, crown_visible=True),
                  sight("a", bearing_error=.02, range_m=65)))
        for candidates, expected in zip(cases, ("b", "a")):
            for ordering in permutations(candidates):
                result = self.step(actions=Actions(shutter=True), sightings=ordering)
                self.assertEqual(result.state.photos, ((expected, 100),))
        # Unknown/occluded closest candidates cannot displace eligible ones.
        result = self.step(actions=Actions(shutter=True), sightings=(
            sight("unknown"), sight("a", visible=False), sight("c", bearing_error=.1)))
        self.assertEqual(result.state.photos, (("c", 100),))

    def test_duplicate_photo_farming_and_delta_only_bonus_upgrade(self):
        state = self.collect("a")
        for _ in range(20):
            state = self.step(state, Actions(shutter=True), (sight(),)).state
        self.assertEqual(state.photos, (("a", 100),))
        upgraded = self.step(state, Actions(shutter=True), (sight(crown_visible=True),))
        self.assertEqual(upgraded.state.score, 140)
        self.assertIn("+40", upgraded.messages[0])
        for crown in (True, False, True, False):
            again = self.step(upgraded.state, Actions(shutter=True), (sight(crown_visible=crown),))
            self.assertEqual(again.state, upgraded.state)
            self.assertIn("no additional points", again.messages[0])
        for ordering in permutations((sight(), sight(crown_visible=True), sight())):
            result = self.step(actions=Actions(shutter=True), sightings=ordering)
            self.assertEqual(result.state.photos, (("a", 140),))
        self.assertEqual(self.step(upgraded.state, Actions(interact=True)).state.phase, "playing")

    def test_selected_existing_photo_does_not_fall_through_to_second_target(self):
        state = self.collect("a")
        result = self.step(state, Actions(shutter=True),
                           (sight("b", bearing_error=.1), sight("a")))
        self.assertEqual(result.state, state)

    def test_optional_fourth_fifth_progression_and_maximum_score(self):
        state = self.collect("edcba", crown=True)
        self.assertEqual(state.photos, tuple((key, 140) for key in "abcde"))
        self.assertEqual(state.score, 700)
        result = self.step(state, Actions(interact=True))
        self.assertEqual(result.state.phase, "won")
        self.assertIn("5 landmarks", result.messages[0])

    def test_corrupt_or_foreign_photo_records_fail_closed(self):
        states = (SurveyState("playing", 600, (("unknown", 100),), 100),
                  SurveyState("playing", 600, (("a", 100),)*3, 300),
                  SurveyState("playing", 600, (("a", 1000),), 1000),
                  SurveyState("playing", 600, (("a", 100),), 700),
                  SurveyState("playing", 600, (), 300),
                  SurveyState("playing", math.nan, (), 0),
                  SurveyState("playing", 601, (), 0),
                  SurveyState("paused", 600, (), 0))
        for state in states:
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.step(state, Actions(shutter=True, interact=True), (sight("b"),))
        with self.assertRaises(ValueError):
            self.rules.start(replace(self.city, landmarks=self.city.landmarks*2))

    def test_won_lost_are_inert_for_every_action_and_valid_elapsed_time(self):
        won = self.step(self.collect(), Actions(interact=True)).state
        lost = self.step(dt=600).state
        actions = Actions(forward=1, turn=1, shutter=True, interact=True, restart=True,
                          new_seed=True, pause=True, help=True, quit=True)
        for state in (won, lost):
            for dt in (0, .1, 600, 1e308):
                result = self.step(state, actions, (sight("d", crown_visible=True),), dt)
                self.assertIs(result.state, state)
                self.assertEqual(result.messages, ())

    def test_clean_reset_same_or_new_city_no_hidden_rewards_and_replay_determinism(self):
        states = (self.collect(), self.step(self.collect(), Actions(interact=True)).state,
                  self.step(dt=600).state)
        for state in states:
            for city in (self.city, fixture(12)):
                fresh = self.rules.start(city)
                self.assertEqual(fresh, SurveyState("playing", 600, (), 0))
                result = self.rules.step(city, fresh, Player(city.spawn), Actions(shutter=True),
                                         (sight(),), .5)
                self.assertEqual(result.state.photos, (("a", 100),))
            self.assertNotEqual(state, self.initial)
        self.assertEqual(self.collect("abc", True), self.collect("abc", True))
        self.assertEqual(self.rules.start(self.city), SurveyRules().start(self.city))

    def test_ui_flags_are_not_rule_level_pause_or_reset(self):
        flags = Actions(pause=True, help=True, restart=True, new_seed=True, quit=True)
        state = self.collect("a")
        self.assertEqual(self.step(state, flags, dt=7), self.step(state, dt=7))
        # A paused app MUST skip calling rules; dt=0 still processes shutter/E.
        self.assertEqual(self.step(actions=Actions(shutter=True), sightings=(sight(),), dt=0).state.score, 100)

    def test_invalid_elapsed_time_raises_without_mutation_in_all_phases(self):
        for phase in ("playing", "won", "lost"):
            state = replace(self.initial, phase=phase)
            for dt in (-1, math.nan, math.inf, -math.inf, True, False, "1", None, 10**400):
                with self.subTest(phase=phase, dt=dt), self.assertRaises(ValueError):
                    self.step(state, Actions(shutter=True, interact=True), (sight(),), dt)
            self.assertEqual(state.photos, ())
        for value in (math.nan, math.inf):
            with self.assertRaises(ValueError):
                self.step(self.collect(), Actions(interact=True), player=Player(Vec3(value, 0, 0)))


if __name__ == "__main__":
    unittest.main()
