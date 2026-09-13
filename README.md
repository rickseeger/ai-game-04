# Lantern Survey (G11)

Explore the street-level 3D colored ASCII city, photograph three distinct
landmarks and return to the depot before 600 active seconds expire.

## Play on Linux

The supported delivery for this pass is a reproducible Linux tarball with a
`lantern-survey` launcher. Python 3.11+ and an interactive xterm-compatible color
terminal are required; 80x24 minimum, 100x36 recommended. No pip dependencies.

See [Linux install, run, controls and rebuild instructions](docs/linux.md).
From source: `python3 -m citywalk`. H starts; W/S/A/D move; J/L turn; I/K look;
SPACE photographs; E submits at the depot; P pauses; Q/Escape quits.
Build: `python3 tools/package_linux.py` from a clean committed checkout.

Windows is explicitly deferred; Windows CI jobs are no longer scheduled.
No Windows artifact/runtime validation is claimed. Packaging and scripted PTY
checks do not establish beauty or fun; independent assessment remains node 11.
See [integration evidence](docs/integration.md) for gameplay and launch details.

## Historical component milestones

The sections below record their original milestone state, not current default
launch behavior. In particular, earlier Windows delivery expectations are deferred.

## Spatial model (node 2)

`citywalk.spatial.CityGenerator().generate(11)` now provides the real 480 m city,
spatial queries, five landmark viewpoints and player-clearance route witnesses.
See [docs/spatial.md](docs/spatial.md) for metre-scale interfaces and limitations.
No terminal input, renderer, movement or game loop is added by this milestone.

    python3 tools/measure_city.py --seeds 11 93 2026

Actual seed measurements and full test output are committed in
`docs/spatial-measurements.json` and `docs/spatial-run.json`.

## Architectural materials (node 3)

`citywalk.appearance.FacadeAppearance` samples existing City/RayHit values into
world-anchored ASCII/RGB materials. No projection, movement or input dependency.
See [docs/appearance.md](docs/appearance.md) for the renderer interface and scale.

    python3 tools/preview_appearance.py --seed 11 --check

Open `docs/appearance-fixtures/atlas.html` for the colored component atlas;
`atlas.txt` and `atlas.json` record glyphs and exact sample coordinates/seeds.
These fixtures establish material behavior, NOT finished 3D city quality.
Actual test/build/fixture results are in `docs/appearance-run.json`.

## Street-level camera (node 4)

`citywalk.camera.Perspective` implements the existing project/ray interface with
metre-scale eye height, full yaw/pitch geometry, rectilinear perspective and
terminal cell-aspect correction. Optional prepared-frame and ray-clip-distance
helpers are documented in [docs/camera.md](docs/camera.md).

    python3 tools/measure_projection.py --check
    python3 -m unittest discover -s tests -p test_camera.py -v

`docs/projection-fixtures.json` records reproducible tower/camera/ray geometry
and real landmark target projections. `docs/camera-run.json` records executed
regression/build checks. These are numeric component fixtures, not rendered
city beauty, a playable game or Windows runtime evidence.

## Colored ASCII renderer (node 5)

`citywalk.rendering.CityRenderer(Perspective())` now produces real opaque RGB/ASCII
Frames and landmark sightings against the existing world/material/camera contracts.
The default app remains informational; input, terminal lifecycle and gameplay stay
in their own later milestones. See [docs/rendering.md](docs/rendering.md).

    python3 tools/capture_renderer.py --check
    python3 tools/capture_renderer.py --benchmark 300 --output ../renderer-recheck
    python3 tools/validate_renderer.py

Open `docs/renderer-frames/frames.html`: 27 actual renderer captures (nine
street-level poses at 80x20, 100x32 and 120x40 scene cells), including an open
vista, a 6 m street in both directions and all five landmarks. Exact RGB/depth
and poses are in frames.json; glyph-only output is frames.txt. These are headless
program frames, not a fabricated illustration or a claimed terminal playtest.
Local 100x32 changed-pose rendering measured median 47.7260 ms / p95 57.1144 ms;
raw samples, environment and exclusions are documented. Beauty and fun still
require the separate human/independent assessment, not merely passing tests.


## Ground walking and collision (node 6)

`citywalk.movement.Walker` consumes the existing `Player`/`Actions`/`Spatial`
contracts: 4 m/s normalized ground walking, 90 degrees/s yaw, 60 degrees/s look,
a 0.30 m disc, continuous axis sweeps and predictable x-then-z wall sliding.
`Walker.spawn(spatial)` validates the approved city spawn without teleporting.
The existing city `segment_clear` query is now explicit in the Spatial protocol.
See [docs/movement.md](docs/movement.md) for semantics, corner stopping, elapsed
handling, integration responsibilities and limitations.

    python3 -m unittest discover -s tests -p test_movement.py -v
    python3 tools/validate_movement.py

`docs/movement-run.json` records real movement and complete regression output,
source hashes, commands, timings and environment. No keyboard adapter or app
loop was added. This is headless movement evidence, not a terminal playtest or a
claim that the complete city game is enjoyable.

## Terminal adapters (node 7)

`citywalk.terminal.open_terminal()` implements the existing Terminal context
manager, nonblocking Actions input, RGB/256-color frame presentation, resize
notices and exception/signal cleanup. This does NOT integrate the game loop.
See [docs/terminal.md](docs/terminal.md) for control timing, support boundaries,
application responsibilities and required native Windows delivery evidence.

    python3 -m unittest discover -s tests -p test_terminal.py -v
    python3 tools/validate_terminal.py
    python3 tools/probe_terminal.py --output ../linux-terminal-probe.json

The final command requires an actual interactive terminal. The probe is a test
pattern and action monitor, NOT the city. Real controlling-Linux-PTY runs,
injected keys, resize checks, raw ANSI transcripts, exact before/after termios,
and full regression/build outputs are in `docs/terminal-pty/` and
`docs/terminal-run.json`. Windows API/input decision tests here use mocks;
no native Windows launch/control result is claimed. Windows Terminal execution
on the exact delivery candidate remains mandatory.

## Survey rules (node 8)

`citywalk.gameplay.SurveyRules` implements the chosen Lantern Survey loop:
photograph at least three distinct landmarks, optionally improve compositions,
and return to submit before 600 active seconds expire. Pure deterministic
transitions include score/progression feedback, win/loss and clean reset.
No interactive app loop is added. See [docs/gameplay.md](docs/gameplay.md) for
exact semantics, defenses and node 9 pause/help/restart integration duties.

    python3 tools/simulate_survey.py --seeds 11 93 2026
    python3 tools/simulate_survey.py --replay docs/gameplay-simulation.json
    python3 tools/validate_gameplay.py

`docs/gameplay-simulation.json` records complete reproducible action tapes:
real collision-checked walking, turns/pitch, actual renderer sightings, three
photos and depot submission. All three tested routes win within 420 seconds.
`docs/gameplay-run.json` records actual complete regression and reproduction
results. This demonstrates rule behavior and reachability, NOT enjoyment,
finished city beauty, terminal play or native Windows runtime evidence.
