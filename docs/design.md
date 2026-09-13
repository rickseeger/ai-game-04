# Lantern Survey — bounded design and implementation handoff

Status: node 1 foundation. This document specifies future behavior; only the
informational CLI, shared types, smoke tests and zipapp builder exist now.
The authoritative G11 mission requires a beautiful, genuinely interesting city;
none of these design decisions or automated checks establish that outcome.

## One game: photograph the city before the night survey closes

You are a municipal night photographer, on foot in a luminous city. Start at the
survey depot with five named landmark cards (name, district, facade clue and
compass bearing, not a top-down maze map). In 600 seconds of active play, obtain
photos of at least THREE DISTINCT landmarks and return within 3 m of the depot,
pressing E to submit. Submission with fewer than three is rejected with feedback.
The timer reaching zero before a valid submission is a loss. No combat,
inventory, NPC simulation, interiors, parkour, procedural quests or metagame.

Player decisions: which three of five sights to seek, which streets offer good
views, whether to detour for a better composition or fourth/fifth photo, and
when to abandon that detour to get home. All five landmarks occupy distinct
neighborhoods with different silhouettes/colors. Broad avenues are fast and
legible; side streets/plazas offer alternative viewpoints and skyline reveals.
Do not create a single prescribed corridor or hide objectives in blind alleys.

SPACE photographs the best eligible landmark: center target visible by spatial
raycast, horizontal distance 18–65 m, target projected within the scene, and
absolute bearing error <= 12 degrees. Sort simultaneous candidates by absolute
bearing error, then id; take only one. Award 100 points once per landmark; add
40 composition points if its crown (height minus 1 m at footprint center) also
projects inside the scene and is unoccluded. Rephotographing may upgrade 100 to
140 but cannot farm points or advance distinct count. A miss consumes no film
but time spent positioning still matters. Five unlimited-film targets keeps the
rules small; no pseudo-random shutter success or hidden scoring.

HUD: remaining time, photos/3, score, nearest unphotographed landmark bearing and
range, depot bearing/range, and short event feedback. Scene gets all but four
terminal rows. Reticle eligibility feedback tells why a photo fails (occluded,
too near/far, off-center); success shows the landmark name and +points. At three
photos explicitly say "Survey ready — return to depot or risk another view".
Won/lost freezes time/movement and shows photos, score and restart instructions.
R restarts the SAME seed from zero score/full time; N starts seed+1. Neither
preserves collected photos. Q always quits. Help/pause freezes timer and motion.
Seed shown on HUD and result screen for repeatable comparisons; no leaderboards.

Transition ordering: quit handled first by application; restart/new seed resets
all state; help/pause toggles application overlays; inactive phases do not step.
An active step deducts dt FIRST (clamp remaining to zero); zero loses even if E
was pressed that frame. Otherwise apply shutter then submission. Shutter/E are
edge events; photo bonus upgrades add only the score delta. Rules derive valid
ids from city.landmarks, reject unknown sighting ids, and never trust an arbitrary
photo count supplied by input. Future simulation fixtures may inject sightings,
but integration must use Renderer.sightings backed by the actual spatial world.

Why this is city exploration, not a generic maze: progress requires looking at
recognizable architecture from street-level vantage points, not touching map
cells. Tower height, corners, occluding facades, long sightlines and plazas
change where a photograph works. Crown bonuses reward looking up and finding
an open vista. Varied landmarks support remembering places without a minimap.
The timer creates an optional-detour tradeoff, not a speedrunning requirement:
generation must provide a demonstrable three-photo return route within 420 s at
walking speed, leaving 180 s for framing/exploration. This is a design hypothesis;
if independent play finds the timer punishing or scoring dull, revise it with
fresh play evidence instead of claiming the rule list proves fun.

## Scale and visual direction

Python 3.11+ and stdlib only. One main thread, deterministic generation; no async
framework or game engine. Use immutable shared values in citywalk/contracts.py.
Initially a 480 x 480 m open street city, x/z bounds [-240,240]. Approximately
10 x 10 blocks with varied split footprints; primary streets 12–18 m clear,
secondary paths >= 6 m. Sidewalk material bands do not obstruct walking. Heights
12–100 m with five landmark crowns up to 140 m. One connected pedestrian
network, several plazas, nonidentical footprints and diagonally offset views.
City boundary blocks movement visibly (edge promenade/rail), never an invisible
interior wall. Flat ground and axis-aligned solid extruded building footprints
are the deliberate geometric bound; no overhang collision or interior geometry.

Night palette: deep indigo sky, blue/violet shaded faces, warm amber windows,
cyan signage, rose brick, pale stone, sparse emerald accents. District-specific
palettes plus deterministic per-building variations. Windows anchored to 3 m
floor cadence, doors about 2.1 m tall at ground, facade bays 2–4 m wide. Roof
bands, lit crowns, alternating setbacks represented by facade pattern (no fake
walkable geometry). Use printable ASCII ramp " .,:;-=+*#%@", bars/slashes for
edges, restrained lit windows rather than all-noise facades. Background colors
and depth fog create coherent masses; glyph variation must not destroy planes.
Ground perspective, a stable horizon, directional face lighting, distance fog
and real occlusion make depth legible. No invented skyline image substituted
for actual city geometry. Nearby towers should routinely extend beyond frame;
look-up reveals their crowns. Different streets must reveal different silhouettes.

## Coordinates, projection, motion and frame contract

Metres, seconds and radians everywhere; x east, y up, z north. Player.feet.y=0;
camera eye = feet + (0,1.7,0). Yaw 0 looks +z; positive yaw turns toward +x.
Forward = (sin(yaw),0,cos(yaw)); right = (cos(yaw),0,-sin(yaw)). Positive pitch
looks up, clamped to [-60,+60] degrees; yaw normalized to [0,2*pi). Rect stores
closed x/z bounds, building y in [0,height]. Player is a horizontal disc radius
0.30 m. Tangency counts blocked with 1e-6 m tolerance. IDs unique and stable
within a seed; deterministic output must not depend on Python hash randomization.
Nearest ray ties resolve ground before building, then building id, then face
name lexicographically. Ray origins offset by a small epsilon where needed;
never conflate forward projection depth with normalized-ray distance.

Camera defaults: horizontal FOV 80 degrees, near 0.10 m, far 500 m. Viewport rows
exclude four HUD rows. Actual cell width/height ratio defaults 0.5 (overridable
later via --cell-aspect). Physical image aspect A=columns*cell_aspect/rows;
vertical FOV = 2*atan(tan(hfov/2)/A). Image origin upper left. Pixel centers are
(column+0.5,row+0.5); projected screen center is (columns/2,rows/2), and positive
camera-up decreases row. project returns None at depth < near, depth > far or
outside screen [0,columns) x [0,rows); points at near are valid. ray returns a
normalized world direction through a cell center. Renderer clips by near/far
in forward depth (convert to ray distance), chooses nearest opaque surface,
uses sky on miss; Frame.depth stores ray distance (infinity for sky). Exactly
columns*rows cells and depths, printable single-cell ASCII glyphs, RGB integers
0..255. Terminal alone encodes ANSI; logic/tests must not parse color strings.

Walk 4.0 m/s, yaw 90 degrees/s, pitch 60 degrees/s. Normalize diagonal input;
no sprint or bobbing. Movement.step accepts finite dt >= 0, sweeps/substeps so
each displacement <= 0.10 m, checks player radius, and resolves x then z for
predictable wall sliding. No tunneling on a 1 s test step. Turning is independent
of blockage. Integration caps simulated motion dt at 0.10 s after a stall, but
passes full active elapsed time to gameplay (so stalls cannot buy free time).
Invalid dt raises ValueError. App monotonic clock; no wall-clock time in modules.

## Ownership and concrete APIs

All Protocols in contracts.py are declarations, not fake implementations. Nodes
create these modules with the following public implementations. Imports flow
inward to contracts, never sideways to concrete peers; inject peers via Protocols.
New fields/signature changes require an explicit handoff update and consumer
tests rather than silently creating a second coordinate convention.

2. spatial.py: CityGenerator.generate(seed:int)->Spatial. Spatial.city returns
   City; raycast(origin,direction,max_distance)->RayHit|None for nearest solid
   building or ground; walkable(feet,radius)->bool includes boundary;
   nearby(Rect)->tuple[Building,...] for broad-phase movement. Raycast requires
   unit direction and finite positive max_distance. Bounds are movement limits,
   not infinite ray walls. Landmark.target is facade-center-height aim point
   on the building surface; viewpoint is a known valid eye pose with yaw/pitch.
   Crown is derived from footprint center and height. Supply reachable viewpoint
   fixtures with crown visible where bonus is intended and seed route witness.
3. appearance.py: FacadeAppearance.sample(city,hit)->Cell. Outward normal/face
   defines local coordinates: north/south walls use x horizontally, east/west
   use z, all use y vertically; roof/ground use x/z. Uses hit building_id to
   locate style/material_seed. Stable world anchoring prevents shimmer. Returns
   local material colors; renderer adds lighting/fog, not appearance module.
4. camera.py: Perspective.project(point,camera,viewport)->Projected|None and
   ray(column,row,camera,viewport)->Vec3 per equations above. Validate dimensions,
   aspect, FOV and clip range. Pure math, no generator/render/input dependencies.
5. rendering.py: CityRenderer.render(spatial,appearance,camera,viewport)->Frame;
   sightings(spatial,camera,viewport)->tuple[Sighting,...]. Cast world rays for
   target/crown, require nearest building id matches landmark and distance
   within 0.05 m of target distance (surface target); crown requires first hit
   on target building, not clear path through it. visible also requires target
   inside projection and clip range; range_m is horizontal player-to-target
   distance, bearing_error shortest signed horizontal angle. Sightings only
   for the five city landmarks, stable id order. Start accelerated per-cell
   rays (spatial grid broad phase); optimize from measured output, not guesses.
6. movement.py: Walker.step(spatial,player,actions,dt)->MotionResult. Independent
   injected Actions tests. Safe spawn check is mandatory before starting app.
7. terminal.py: open_terminal()->Terminal context manager. size()->(cols,total
   rows), poll(monotonic_now)->Actions, present(Frame,hud_lines)->None. Linux
   select/os.read + termios; Windows msvcrt input + ctypes VT mode support.
   Save/restore modes, cursor, alternate screen, colors in finally on quit,
   Ctrl-C and exceptions. SIGTERM cleanup on Linux; do not promise SIGKILL
   restoration. Unsupported/non-TTY interactive launch exits with instructions;
   --smoke remains pipe-safe. Avoid curses dependency on Windows.
8. gameplay.py: SurveyRules.start(city)->SurveyState and
   step(city,state,player,actions,sightings,dt)->GameResult. Pure rules; no clock,
   rendering, terminal or filesystem access. Known geometry via City; valid
   shutter opportunities via Sighting. App handles reset/pause/help, rule phases
   handle win/loss and immutable photo records. No rewards carried over restart.
9. app.py integrates implementations; owns pause/help state, clock, CLI seed,
   assembly, rendering/HUD composition, restart, lifecycle and capture pipeline.
   Sequence: input -> UI gating -> movement -> camera -> sightings -> rules ->
   scene render -> HUD -> terminal present. One world/appearance shared by all.

## Terminal controls and support policy (future node 7/9)

W/S forward/back; A/D strafe left/right; Left/Right or J/L turn; Up/Down or I/K
look up/down; SPACE shutter; E submit at depot; P pause; H or ? help; R restart
same seed; N seed+1; Q or Escape quit; Ctrl-C emergency clean exit. ASCII letters
case-insensitive. Arrow decoding buffers escape sequences; lone Escape resolves
as quit only after 40 ms (not midway through CSI). Windows extended keys map to
the same Actions. Digital directional events set axis to +/-1 for 140 ms renewed
by repeat, because terminals have no reliable key-up; simultaneous opposite
keys use most recent. Shutter/UI repeats suppressed until 250 ms without that
key. These constraints need real hold/tap playtests; advertise tapping/repeating,
not unsupported precision simultaneous-key guarantees. No mouse requirement.

100x36 recommended, 80x24 minimum. Smaller windows show a plain resize/help/quit
notice and freeze game time/motion. Resize rebuilds viewport/frame and clears
stale regions without resetting game. Restore succeeds even after render error.
ANSI truecolor preferred, xterm-256 quantized fallback (--color 256 planned);
Windows must explicitly enable VT processing or show a clear actionable error.
No claim of legacy cmd.exe support without VT. Headless capture and smoke never
change terminal attributes. Source launch and zipapp are same entry point.

## Dependency order and verification gates

After this foundation, 2/3/4/6/7/8 may develop against shared values and explicit
fixtures independently. 3 uses hand-authored City/Hit fixtures; 6 uses small
Spatial fixtures; 8 uses City/Sighting fixtures. Real-world validation of 6/8
then requires 2; final appearances should be checked on 2. Renderer 5 integrates
2+3+4; app 9 integrates 5+6+7+8; packaging 10 follows 9; independent experiential
assessment 11 evaluates the actual candidate from 10. No harness/tree changes
are made by this worker. A passing fixture is not a substitute for integration.

Measurable checks subsequent owners must execute (targets, not current results):
- 2: seeds 11,93,2026 deterministic across two processes/PYTHONHASHSEED values;
  bounds/height/footprints valid, five unique landmarks, connected streets,
  spawn/depot radius clearance, no overlap errors; >= 3 distinct height bands
  and footprint sizes; route witness <= 1680 m plus positioning budget, with
  actual three-photo simulation <= 420 s. Test all five destination viewpoints.
- 3: repeat facade sampling at fixed coordinates/seeds yields identical cells,
  valid RGB/glyphs, 3 m floor cadence, door/window/crown fixtures for each style.
- 4: eye height 1.7; project/ray center round trips; yaw and pitch basis; near
  rejection; doubled forward distance halves projected offsets; square-world
  proportions corrected for 0.5 cell aspect; tower clipping and rotation fixtures.
- 5: front wall occludes rear, ground/sky horizon and far fog, correct near clip,
  actual broad vista/narrow lane/landmark frames. At 100x32 scene cells measure
  300 warmed frames: target median <= 50 ms, p95 <= 100 ms on recorded CPU/OS/
  Python. If not met, profile broad phase; do not reduce city scale silently.
- 6: stable distance at 20/60/120 Hz, normalized diagonal, wall stop/slide,
  corners, bounds, dt=0 and invalid dt, 1 s tunneling challenge, safe spawn.
- 7: every key mapping including split escape sequences, key repetition,
  nonblocking polls, resize. Linux PTY injection verifies termios before/after
  quit/Ctrl-C/exception, cursor/show and alternate-screen exit. Windows unit
  tests are not Windows runtime proof; require real Windows release play.
- 8: success, exact-deadline loss, invalid submission, missing/occluded/range/
  bearing failures, photo uniqueness and bonus upgrade, inert terminal phases,
  pause integration, deterministic reset. Full seeded route simulation including
  returning to depot, not direct state fabrication. Fixtures alone do not prove fun.
- 9/10: fresh-clone full suite/build/launch, interactive route, collision,
  win/loss/restart/quit, clean terminal. Windows artifact launch and controls on
  Windows require runner or Andrew, with exact build SHA; external access failure
  must be reported as blocked rather than passed.

Capture plan for 5/9: add documented --capture-dir, --frames, --fixed-dt and
--replay JSON-input-file options (NOT implemented now). Each capture records
source SHA, seed, camera pose, terminal size/cell aspect, color mode, platform,
raw input sequence/timestamps, actual Frame cells/depth (encode infinity as null),
ANSI frame, plain-text frame and measured render times. Capture positions from
generator fixtures: depot broad vista, narrow street eye-level, landmark looking
up; include multiple orientations and moving corner reveals. A PTY recording
adds actual terminal output and restoration evidence; no synthetic city art.

Independent quality gate: G or a real human must meaningfully play the delivered
artifact, separately judge towering human scale/depth/color/variety and fun,
record route, actions, concrete observations and deficiencies, and retest fixes.
A terminal transcript, scripted winning route, score or test count cannot prove
a city is beautiful or a game enjoyable. If this interface cannot support that
assessment, request an actual playtest rather than inventing one.
