"""Application integration regressions; PTY execution is separate real evidence."""
from dataclasses import replace
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from citywalk.app import Application, main, run
from citywalk.capture import Capture
from citywalk.contracts import Actions
from citywalk.terminal import TerminalAdapter, LEAVE_DISPLAY
from test_terminal import FakeBackend


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.app = Application(11)
        self.size = (80,24)

    def begin(self):
        self.app.tick(Actions(help=True), 20, self.size)

    def test_onboarding_and_all_cards_pause_and_ascii_four_rows(self):
        app = self.app
        player, state = app.player, app.state
        for page in range(7):
            self.assertEqual(app.help_page, page)
            hud = app.hud(self.size)
            self.assertEqual(len(hud), 4)
            self.assertTrue(all(len(line)<=80 and line.isascii() for line in hud))
            app.tick(Actions(shutter=True, forward=1, turn=1), 50, self.size)
            self.assertEqual((app.player,app.state), (player,state))
        self.assertEqual(app.help_page, 0)

    def test_motion_full_elapsed_for_rules_capped_for_walk(self):
        self.begin()
        before = self.app.player
        self.app.tick(Actions(forward=1), 2.0, self.size)
        self.assertAlmostEqual(self.app.player.feet.z-before.feet.z, .4)
        self.assertEqual(self.app.state.remaining_s, 598)
        self.assertEqual(len(self.app.sightings), 5)

    def test_pause_help_resize_do_not_charge_inactive_elapsed_or_move(self):
        self.begin()
        app = self.app
        app.tick(Actions(pause=True), .1, self.size)
        player, state = app.player, app.state
        app.tick(Actions(forward=1, shutter=True), 90, self.size)
        self.assertEqual((app.player,app.state), (player,state))
        app.tick(Actions(pause=True), 90, self.size)
        self.assertEqual((app.player,app.state), (player,state))
        app.tick(Actions(help=True), .1, self.size)
        app.tick(Actions(forward=1), 90, self.size)
        app.tick(Actions(help=True), 90, self.size)
        self.assertEqual((app.player,app.state), (player,state))
        app.tick(Actions(forward=1), 90, (70,20))
        app.tick(Actions(forward=1), 90, self.size)
        self.assertEqual((app.player,app.state), (player,state))
        app.tick(Actions(forward=1), .1, self.size)
        self.assertLess(app.state.remaining_s, state.remaining_s)

    def test_quit_precedes_restart_new_seed_and_ui_even_small(self):
        old = self.app.world.city
        self.app.tick(Actions(quit=True,restart=True,new_seed=True,help=True), 50, (1,1))
        self.assertTrue(self.app.quit)
        self.assertIs(self.app.world.city, old)

    def test_reset_and_new_seed_clear_every_state_and_validate_spawn(self):
        self.begin()
        app = self.app
        app.tick(Actions(forward=1,turn=1), .1, self.size)
        app.tick(Actions(pause=True), .1, self.size)
        original = Application(11)
        app.tick(Actions(restart=True), 500, self.size)
        self.assertEqual(app.player, original.player)
        self.assertEqual(app.state, original.state)
        self.assertEqual(app.world.city, original.world.city)
        self.assertFalse(app.paused)
        self.assertIsNone(app.help_page)
        app.tick(Actions(new_seed=True), 500, self.size)
        self.assertEqual(app.world.city.seed,12)
        self.assertEqual(app.state.remaining_s,600)
        self.assertTrue(app.world.walkable(app.player.feet,.3))

    def test_exact_deadline_loss_and_inert_terminal_phase(self):
        self.begin()
        app = self.app
        app.tick(Actions(interact=True), 600, self.size)
        self.assertEqual(app.state.phase,"lost")
        before = app.state,app.player
        app.tick(Actions(forward=1,turn=1,shutter=True), 100, self.size)
        self.assertEqual((app.state,app.player),before)
        self.assertIn("LOST",app.hud(self.size)[1])
        app.tick(Actions(restart=True), .1, self.size)
        self.assertEqual(app.state.phase,"playing")

    def test_actual_photo_interface_and_ready_navigation(self):
        self.begin()
        app = self.app
        # Explicit pose fixture tests wiring, NOT claimed as interactive route.
        for landmark in app.world.city.landmarks[:3]:
            app.player = replace(app.player,feet=replace(landmark.viewpoint,y=0),
                                 yaw=landmark.view_yaw,pitch=landmark.view_pitch)
            app.tick(Actions(shutter=True), .1, self.size)
        self.assertEqual(len(app.state.photos),3)
        self.assertEqual(app.state.score,420)
        app.message_age = 9
        hud = app.hud(self.size)
        self.assertIn("Survey ready",hud[3])
        self.assertIn("Depot",hud[1])
        app.player = replace(app.player, feet=app.world.city.depot)
        app.tick(Actions(interact=True), .1, self.size)
        self.assertEqual(app.state.phase,"won")
        self.assertIn("WON",app.hud(self.size)[1])

    def test_scene_occupies_all_but_four_rows_at_both_sizes_and_resize(self):
        for size in ((80,24),(100,36)):
            app=self.app
            frame=app.render(size)
            self.assertEqual((frame.columns,frame.rows),(size[0],size[1]-4))
            self.assertEqual(len(frame.cells),frame.columns*frame.rows)
            self.assertEqual(frame.cells[(frame.rows//2)*frame.columns+frame.columns//2].glyph,"+")
            self.assertEqual(len(app.hud(size)),4)
            self.assertTrue(any(c.fg!=c.bg for c in frame.cells))

    def test_invalid_time_and_cli_options(self):
        for dt in (-1,float("nan"),float("inf")):
            with self.assertRaises(ValueError):
                self.app.tick(Actions(),dt,self.size)
        for options in (("--cell-aspect","0"),("--cell-aspect","nan"),("--frames","0")):
            with self.assertRaises(SystemExit) as exc, patch("sys.stderr",new=io.StringIO()):
                main(options)
            self.assertEqual(exc.exception.code,2)

    def test_run_loop_exception_restores_actual_adapter_context(self):
        backend=FakeBackend()
        with self.assertRaisesRegex(RuntimeError,"render regression"):
            with TerminalAdapter(backend) as term:
                with patch.object(self.app,"render",side_effect=RuntimeError("render regression")):
                    run(term,self.app,frames=1)
        self.assertTrue(backend.closed)
        self.assertTrue(backend.output.getvalue().endswith(LEAVE_DISPLAY))

    def test_capture_records_presented_frame_and_clean_frame_limit(self):
        backend=FakeBackend()
        with tempfile.TemporaryDirectory() as temp:
            args=SimpleNamespace(seed=11,cell_aspect=.5,color="truecolor")
            capture=Capture(Path(temp),args)
            with TerminalAdapter(backend) as term:
                capture.attach(term)
                self.assertEqual(run(term,self.app,capture,frames=2,sleep=lambda _:None),0)
            capture.close()
            trace=[json.loads(line) for line in (Path(temp)/"trace.jsonl").read_text().splitlines()]
            self.assertEqual(len(trace),2)
            self.assertEqual(trace[0]["size"],[80,24])
            self.assertEqual(trace[0]["state"]["remaining_s"],600)
            import gzip
            frames=[json.loads(line) for line in gzip.decompress((Path(temp)/"frames.jsonl.gz").read_bytes()).decode().splitlines()]
            self.assertEqual(len(frames),1)
            self.assertEqual(len(frames[0]["cells"]),1600)
            self.assertEqual(len(frames[0]["depth"]),1600)
            ansi=gzip.decompress((Path(temp)/"checkpoints.ansi.gz").read_bytes())
            self.assertIn(b"LANTERN SURVEY",ansi)
            self.assertTrue(backend.closed)


if __name__ == "__main__":
    unittest.main()
