# Lantern Survey (G11)

Foundation, spatial-generation, appearance, camera, renderer, movement, terminal and gameplay-rule milestones, NOT a playable city yet. Default launch reports this and
exits normally. Headless rendering and injected-action movement are real; terminal adapters are available as components; pure survey rules are implemented; interactive application integration is not.
Shared Python interfaces are in `citywalk/contracts.py`; implementation handoff
and the chosen game are in [docs/design.md](docs/design.md).

## Requirements and exact commands

Python 3.11+ (standard library only); Git for cloning. No pip, network packages,
curses, native extensions or install step. From a fresh clone:

    git clone git@github.com:rickseeger/ai-game-04.git
    cd ai-game-04
    python3 -m citywalk
    python3 -m citywalk --smoke --seed 11
    python3 -m unittest discover -s tests -v
    python3 tools/build.py
    python3 dist/lantern-survey.pyz
    python3 dist/lantern-survey.pyz --smoke --seed 11

Public HTTPS clone alternative: https://github.com/rickseeger/ai-game-04.git
Windows PowerShell: use the same commands with `py -3` instead of `python3`.
The zipapp can run from any directory; it contains all application source.
`python3 -m citywalk --help` documents currently implemented options.
Tests and source launch run from repository root. Build accepts any working directory.
Building twice from identical source produces identical bytes and prints SHA-256.

## Distribution plan

Both Linux and Windows support the same `.pyz`, with Python 3.11+ explicitly
required. Node 10 packages it into a Linux tar.gz and Windows zip with platform
launchers and instructions, identified commit and checksums. This is a viable
Python-runtime distribution, NOT a standalone native executable. If standalone
is later required, build PyInstaller executables separately on native runners;
never present Linux cross-builds as Windows runtime evidence.

Final terminal target: Linux xterm-compatible UTF-8 terminal and Windows 10/11
Windows Terminal with VT color support. ASCII glyphs keep cell widths portable.
100x36 recommended, 80x24 minimum; proposed controls and resize behavior are in
the design. CI runs foundation tests/build on Linux/Windows with Python 3.11/3.14.
CI configuration is not proof those runs have passed, nor Windows game playtest proof.

This node validates execution and architecture, not beauty or fun. See
`docs/foundation-validation.md` for actual local evidence and limitations.

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
