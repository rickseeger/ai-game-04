"""Playable Lantern Survey: application clock, UI gates and concrete assembly."""
import argparse
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import sys
import textwrap
import time

from . import __version__
from .appearance import FacadeAppearance, PALETTES
from .camera import Perspective, camera_from_player
from .contracts import Actions, Cell, Frame, Viewport
from .gameplay import SurveyRules, _rejection
from .movement import Walker
from .rendering import CityRenderer
from .spatial import CityGenerator
from .terminal import MIN_SIZE, TerminalInterrupted, TerminalUnavailable, open_terminal


def ascii_text(value):
    return value.replace("—", "-").encode("ascii", "replace").decode()


def bearing(player, point):
    dx, dz = point.x-player.feet.x, point.z-player.feet.z
    angle = math.degrees(math.atan2(dx, dz)) % 360
    compass = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[round(angle/45) % 8]
    return f"{compass} {angle:03.0f}deg {math.hypot(dx, dz):.0f}m"


class Application:
    def __init__(self, seed=11, cell_aspect=.5):
        self.generator, self.walker = CityGenerator(), Walker()
        self.renderer, self.appearance = CityRenderer(Perspective()), FacadeAppearance()
        self.rules = SurveyRules()
        self.cell_aspect = cell_aspect
        self.reset(seed, onboarding=True)

    def reset(self, seed, onboarding=False):
        self.world = self.generator.generate(seed)
        self.player = self.walker.spawn(self.world)  # validates actual disc clearance
        self.state = self.rules.start(self.world.city)
        self.paused, self.help_page = False, (0 if onboarding else None)
        self.small, self.blocked, self.quit = False, False, False
        self.messages, self.message_age = ("Photograph three landmarks, then return here and press E.",), 0.0
        self.sightings = ()

    def tick(self, actions, dt, size):
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("elapsed time must be finite and nonnegative")
        if actions.quit:
            self.quit = True
            return
        small = size[0] < MIN_SIZE[0] or size[1] < MIN_SIZE[1]
        was_inactive = self.small or self.paused or self.help_page is not None
        self.small = small
        self.blocked = False
        if not small and (actions.restart or actions.new_seed):
            self.reset(self.world.city.seed + int(actions.new_seed))
            return
        if actions.help:
            self.help_page = 0 if self.help_page is None else None
            return  # no held motion, shutter, or elapsed charged on UI transitions
        if not small and actions.pause:
            if self.help_page is not None:
                self.help_page = None
            else:
                self.paused = not self.paused
            return
        if self.help_page is not None and actions.shutter:
            self.help_page = (self.help_page + 1) % 7
        if small or self.paused or self.help_page is not None or was_inactive or self.state.phase != "playing":
            return
        self.message_age += dt
        motion = self.walker.step(self.world, self.player, actions, min(dt, .10))
        self.player, self.blocked = motion.player, motion.blocked
        viewport = Viewport(size[0], size[1]-4, self.cell_aspect)
        self.sightings = self.renderer.sightings(self.world, camera_from_player(self.player), viewport)
        result = self.rules.step(self.world.city, self.state, self.player, actions, self.sightings, dt)
        self.state = result.state
        if result.messages:
            self.messages, self.message_age = result.messages, 0.0
        elif self.blocked:
            self.messages, self.message_age = ("Wall / city rail: blocked. Turn or strafe along it.",), 0.0

    def hud(self, size):
        cols = size[0]
        city, state = self.world.city, self.state
        status = f"LANTERN | {state.remaining_s:05.1f}s | Photos {len(state.photos)}/3 | Score {state.score} | Seed {city.seed}"
        if self.help_page is not None:
            page = self.help_page
            if page == 0:
                lines = ("LANTERN SURVEY - night photographer | TIME FROZEN",
                         "600s: photograph 3 distinct landmarks; return to depot, E submit.",
                         "W/S walk A/D strafe; J/L or arrows turn; I/K or arrows look up/down.",
                         "SPACE: help/cards next | H or P: begin/resume | Q/Esc: quit")
            elif page == 1:
                lines = ("HELP 2/7 | TIME FROZEN | SPACE next; H close; Q quit",
                         "SPACE photo: clear facade, 18-65m, aim within 12deg. Look up for +40.",
                         "P pause; H help; R restart same seed; N seed+1; E submit at depot.",
                         "Tap/repeat direction keys (140ms hold); no key-up. Cards next ->")
            else:
                landmark = city.landmarks[page-2]
                building = next(b for b in city.buildings if b.id == landmark.building_id)
                clue = {"amber-brick": "Amber windows, brick piers", "cyan-glass": "Cyan glass, cool window grid",
                        "violet-artdeco": "Violet stepped bands, gold windows", "rose-stone": "Rose stone, warm window bays",
                        "emerald-metal": "Emerald metal, green crown"}.get(building.style, building.style)
                lines = (f"CARD {page-1}/5: {landmark.name} | TIME FROZEN",
                         f"District: {landmark.district} | {bearing(self.player, landmark.target)}",
                         f"Look for: {clue}; {building.height:.0f}m high.",
                         "SPACE next card/help | H resume | Q quit")
        elif self.paused:
            lines = (status, "PAUSED - timer and movement frozen", "P resume | H help/cards | R restart | N new city | Q quit", "City remains in view; no menu covers the street.")
        elif state.phase != "playing":
            lines = (status, "SURVEY " + ("WON - delivered at the depot!" if state.phase == "won" else "LOST - the night survey closed."),
                     f"{len(state.photos)} distinct landmarks; {state.score} points. Seed {city.seed}.",
                     "R restart same city | N seed+1 | H help | Q/Esc quit")
        else:
            todo = [l for l in city.landmarks if l.id not in dict(state.photos)]
            nearest = min(todo, key=lambda l: math.hypot(l.target.x-self.player.feet.x, l.target.z-self.player.feet.z), default=None)
            # Navigation uses compact names so depot is never clipped at 80 columns.
            nav = f"Depot {bearing(self.player, city.depot)}"
            if nearest:
                nav += f" | Next {nearest.name}: {bearing(self.player, nearest.target)}"
            target = min(self.sightings, key=lambda s: (abs(s.bearing_error), s.landmark_id), default=None)
            aim = _rejection(target) if target else "Seek a landmark; H shows cards"
            if target and aim is None:
                name = next(l.name for l in city.landmarks if l.id == target.landmark_id)
                aim = f"READY: {name} (+{140 if target.crown_visible else 100}) - SPACE"
            feedback = "Survey ready - return to depot or risk another view!" if len(state.photos) >= 3 else "SPACE photo | E submit | H cards/help | P pause | R restart | Q quit"
            if self.message_age < 8:
                chunks = textwrap.wrap(ascii_text(" / ".join(self.messages)), width=cols) or [""]
                feedback = chunks[min(int(self.message_age/2), len(chunks)-1)]
            lines = (status, nav, "[+] " + aim, feedback)
        return tuple(ascii_text(line)[:cols] for line in lines)

    def render(self, size):
        if self.small:
            return Frame(1, 1, (Cell(" ", (0,0,0), (0,0,0)),), (math.inf,))
        frame = self.renderer.render(self.world, self.appearance, camera_from_player(self.player),
                                     Viewport(size[0], size[1]-4, self.cell_aspect))
        # One-cell aiming marker, not a menu over the architectural scene.
        index = (frame.rows//2)*frame.columns + frame.columns//2
        cells = list(frame.cells)
        cells[index] = replace(cells[index], glyph="+", fg=(240, 225, 180))
        return replace(frame, cells=tuple(cells))


def run(terminal, app, capture=None, frames=None, clock=time.monotonic, sleep=time.sleep):
    previous = clock()
    count = 0
    while frames is None or count < frames:
        start = clock()
        dt, previous = max(0, start-previous), start
        actions, size = terminal.poll(start), terminal.size()
        app.tick(actions, dt, size)
        if app.quit:
            if capture:
                capture.event({"event": "quit", "frame": count, "actions": asdict(actions)})
            break
        begin = clock()
        frame = app.render(size)
        rendered = clock()
        hud = app.hud(size)
        terminal.present(frame, hud)
        presented = clock()
        if capture:
            capture.record(count, start, dt, actions, size, app, frame, hud,
                           (rendered-begin)*1000, (presented-rendered)*1000)
        count += 1
        sleep(max(0, .05-(clock()-start)))  # <=20 Hz; never busy-spin on queued keys
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lantern Survey - walk a colorful 3D terminal city")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--smoke", action="store_true", help="assemble, render and validate without changing terminal modes")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--cell-aspect", type=float, default=.5, help="cell width/height; default 0.5")
    parser.add_argument("--color", choices=("truecolor", "256"), default="truecolor")
    parser.add_argument("--capture-dir", type=Path, help="record real frame checkpoints, per-tick state/actions and timing")
    parser.add_argument("--frames", type=int, help="cleanly exit after this many actual frames (capture/profiling)")
    args = parser.parse_args(argv)
    if not math.isfinite(args.cell_aspect) or args.cell_aspect <= 0:
        parser.error("--cell-aspect must be finite and positive")
    if args.frames is not None and args.frames < 1:
        parser.error("--frames must be positive")
    app = Application(args.seed, args.cell_aspect)
    if args.smoke:
        frame = app.render((100,36))
        print(json.dumps({"status": "ok", "stage": "playable", "seed": args.seed,
                          "eye_height_m": camera_from_player(app.player).eye.y,
                          "viewport": [frame.columns, frame.rows], "cells": len(frame.cells),
                          "landmarks": len(app.world.city.landmarks), "version": __version__}, sort_keys=True))
        return 0
    capture = None
    try:
        if args.capture_dir:
            from .capture import Capture
            capture = Capture(args.capture_dir, args)
        with open_terminal(color=args.color) as terminal:
            if capture:
                capture.attach(terminal)
            return run(terminal, app, capture, args.frames)
    except TerminalUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except TerminalInterrupted as exc:
        return 128 + int(exc.signum)
    finally:
        if capture:
            capture.close()
