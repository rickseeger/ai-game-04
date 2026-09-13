# Colored ASCII renderer - node 5 handoff

Implemented on node 4 revision `17640c4`, using the unchanged shared contracts,
city geometry, architectural sampler and perspective module. This milestone is
an exercised renderer, NOT the completed game, a terminal adapter, a movement
implementation or a beauty/fun verdict. No tree or node status was changed.

## Consumer interface

    from citywalk.spatial import CityGenerator
    from citywalk.appearance import FacadeAppearance
    from citywalk.camera import Perspective, camera_from_player
    from citywalk.contracts import Player, Vec3, Viewport
    from citywalk.rendering import CityRenderer

    world = CityGenerator().generate(11)
    appearance = FacadeAppearance()
    renderer = CityRenderer(Perspective())
    camera = camera_from_player(Player(Vec3(0, 0, 0), yaw=0, pitch=.15))
    frame = renderer.render(world, appearance, camera, Viewport(100, 32))
    sightings = renderer.sightings(world, camera, Viewport(100, 32))

Constructor injection is explicit: `CityRenderer(projection)`. Render/sightings
signatures implement `contracts.Renderer` exactly. The renderer imports contracts
and stdlib only. A projection implementing only the foundation project/ray
methods works and is tested against the prepared fast path. `Perspective.prepare`
is detected as an optional optimization; it is not a new Protocol requirement.
Reuse one renderer/appearance per render worker. Projection is a fixed dependency,
not a mutable setting to replace between calls. No global state or unbounded cache.

Metres/radians, x east/y up/z north, original FOV and cell-aspect conventions.
All captured cameras are at the unchanged 1.7 m eye height on verified walkable
feet positions. Buildings retain their generated heights; none are shrunk to
fit the display. Each scene cell is a real center ray through the validated
perspective interface, querying the real spatial grid, sampling the real material.
No procedural skyline overlay, illustrated city, fake HUD or invented frame.

Frames are row-major immutable Cell tuples and eye-relative normalized-ray depth
values; sky is infinity. Glyphs are printable single-cell ASCII and colors are
RGB integer triples. The renderer emits NO ANSI and touches no terminal modes.
Terminal encoding/lifecycle stays in node 7; application integration stays in
node 9. Only the foundation launch status text was clarified to avoid saying
that the now-existing headless renderer does not exist.

## Occlusion and clipping policy

The nearest opaque surface on each cell ray supplies both color and depth.
Wall orientation, corners, ground and roofs come from Spatial RayHit, not screen
heuristics. A tower remains filled even when all upper corners are offscreen.
Full pitch rotation produces converging verticals when looking up; turning right
moves the city left. Ground vanishing lines and diminishing architectural bays
come from world-anchored metre coordinates, not angular ray columns or a map.

Near/far clip in forward camera depth, converted to ray distances. Cast from
`eye + direction * max(0, t_near - 1e-8)` with max distance
`t_far - shift + 1e-8`. This deliberately includes exact near/far surfaces within
a 1e-8 m ray-distance reconstruction tolerance. The same tolerance can admit a
surface just outside a mathematical clip plane by at most 1e-8 m. It is not a
metre-scale geometry allowance. Add shift back to each returned hit distance
BEFORE Appearance.sample, shading or Frame.depth; hit world coordinates are real.

Geometry fully before near does not turn a cell into sky: the next valid surface
is queried. If near cuts through a solid, its exit surface is rendered; there is
no invented near-plane cap. Spatial ground/id/face tie rules are retained. For
unusual huge diagnostic coordinates binary64 limits remain; intended use is the
approved metre-scale city, not arbitrary astronomical clip intervals.

One pose/viewport ray-geometry cache is retained, containing original-eye clip
intervals and sky cells. A separate single-lens clip table depends only on
viewport/FOV/near/far, saving redundant ray generation on turns. Pose, lens and
resize invalidation are tested. City hits, materials and final frames are never
cached: every render really queries the world again.

## Light, atmosphere and legibility

The existing district palettes remain intact. Compass-facing light factors are
south 1.05, east .95, north .80, west .72, roof 1.12 and ground .90. Foregrounds
with a channel >=190 retain at least .98 illumination, keeping warm windows and
cyan/green signs luminous without adding a new emissive field. These are static
art-direction factors, NOT shadows, global illumination or dynamic lighting.

Fog transmission is exp(-max(0, ray_distance-12)/145), blending both foreground
and background toward RGB (24,30,53). Near masses stay saturated while remote
walls fade and lose fine glyph contrast. Beyond 110 m, small nonstructural glyphs
become colons; beyond 190 m they become dots. Quiet background colors preserve
opaque masses. Sky is a world-elevation indigo-to-haze gradient, with no stars or
fake skyline. Paving joints are sampled from the appearance module; contrast
fades after 18 m and glyphs become dots past 40 m to restrain far-ground aliasing.

The ground is the existing continuous 2 m paving-joint surface, including the
city-edge stripe. Narrow lanes, plazas and avenues read through real clear width,
receding walls and paving perspective. No asphalt/sidewalk classifier or rail is
invented: those are not in the shared City material contract. The boundary stripe
is not a geometric boundary affordance or a complete integration solution.

## Genuine frame products and reproduction

From repository root, Python 3.11+ standard library only:

    python3 tools/capture_renderer.py
    python3 tools/capture_renderer.py --check
    python3 tools/capture_renderer.py --benchmark 300 --output ../renderer-recheck
    python3 tools/capture_renderer.py --seed 93 --output ../renderer-seed93
    python3 -m unittest discover -s tests -p test_rendering.py -v
    python3 tools/validate_renderer.py

On Windows replace python3 with py -3; this is a reproduction instruction, NOT
an observed Windows run. The capture tool also works from another directory.
`--check` is read-only; a missing/stale file fails. It cannot be combined with
benchmarking. Benchmark output is nondeterministic timing and is never golden-
compared. Frame byte checks are exact on the recorded environment; cross-platform
libm last-bit depth differences may require an explicitly reviewed tolerance
policy later, not silent fixture replacement. Renderer source hashes are embedded
in frames.json, so an intentional source edit requires regenerating captures.

Open `docs/renderer-frames/frames.html` for the actual colored frames. It directly
encodes each Frame Cell as fixed 8x16 CSS pixels (physical aspect .5), without
external assets, image retouching or JavaScript. `frames.txt` is the same glyph
output; `frames.json` contains all camera/viewport inputs, source SHA-256 values,
per-panel cell tables/indices, full-precision original-eye depths (null for sky)
and actual landmark sighting results. These are program-generated frame captures,
not claimed browser screenshots or observed terminal output. Tests parse the
HTML and verify every displayed glyph and RGB against the generated Frame data.

There are nine poses at each of three sizes, 27 actual frames:

- broad_vista: Civic plaza, eye (-24,1.7,-36), yaw -.28, pitch .30, exposing an
  oblique open sightline, layered architecture and nearby towering clock facade.
- avenue_east: depot intersection looking east, yaw pi/2, pitch .12, long roadway.
- narrow_street: generated 6 m lane-x-5-4, eye (24,1.7,-24), yaw 0, pitch .12.
- narrow_reverse: same lane, yaw pi, pitch .35; opposite architecture/occlusion.
- landmark_sight-0 through landmark_sight-4: Amber Spire, Tidal Beacon, Violet
  Clock, Rose Lantern and Emerald Crown, from their real validated viewpoints,
  pitched toward their targets. Their actual heights/crowns remain intact.

All coordinates above describe seed 11; other seeds select their own actual
metadata. Selection uses public-space metadata only in the diagnostic assembly
tool; the renderer itself does not depend on concrete SpatialWorld metadata.

Supported documented scene/terminal dimensions (four future HUD rows reserved):

    scene 80x20   -> terminal 80x24 minimum
    scene 100x32  -> terminal 100x36 recommended
    scene 120x40  -> terminal 120x44 larger view

Scene sizes exclude HUD rows; the renderer does not silently subtract them.
No terminal-size querying, minimum-window lifecycle or input handling is added.
The camera permits other positive scene sizes/aspects, but these three are the
actual capture/performance evidence, not an unlimited display-quality promise.

## Landmark sightings handoff

Stable landmark-id order. `visible` requires target projection in scene/clip
range, nearest eye-origin world ray on the same building and hit distance within
.05 m of target distance. This rejects looking THROUGH the landmark at an
internal/rear point. Crown is footprint center at height-1: it must project in
scene and its ray must first hit the target building. It is intentionally inside
the volume, so the surface-target .05 m rule does not apply to crowns.

Sightings use eye-origin occlusion, not near-clipped scene rays: a solid in front
of near still blocks photography. Range is horizontal eye/player-to-target
metres; bearing_error is signed shortest horizontal angle in [-pi,pi).
Visibility does NOT itself implement photo range/bearing eligibility, scoring,
timer, player motion or input; the gameplay owner consumes these facts.

## Executed validation and measured performance

`docs/renderer-baseline.json` records the untouched baseline: 49 tests passed.
`docs/renderer-run.json` records full final regression/build/fixture checks, actual
stdout/stderr, return codes, environment and source hashes: 67 tests passed in
12.719 s. Repository .gitattributes keeps text/fixtures LF on all platforms;
Python 3.11 syntax parsing passed, but local runtime evidence is Python 3.14 only.
New tests include an
independent six-finite-plane intersection oracle over complete frames, front/rear
occlusion, overlapping boxes, corner/ground tie cases, roof views, clipped entry
skins, inside-box exits, inclusive near/far, off-axis ray distances, sky/ground
horizon, towering facades, perspective shrinkage, shading/fog, cache invalidation,
protocol-only injection, safe generated poses, all five landmarks for seeds
11/93/2026, every HTML Cell and two fresh-process PYTHONHASHSEED values.

Actual environment: Linux 7.0.0-31-generic x86_64 / glibc 2.43, CPython 3.14.4,
AMD EPYC 9354P 32-Core Processor reported by /proc/cpuinfo, four logical CPUs
visible. No third-party packages/GPU. perf_counter_ns wall duration, 9 warmups
per size, 300 measured frames per size cycling broad vista/narrow lane/clock
poses. Every measured frame changes pose and rebuilds ray geometry; no finished
frame cache. Times include queries, materials, lighting and Frame allocation,
exclude city generation, sightings, HTML/JSON encoding and terminal presentation.

    scene       median ms    p95 ms     maximum ms
    80x20        23.2913      28.8689      35.1748
    100x32       47.7260      57.1144      73.0415
    120x40       69.2143      79.5394      85.5111

The 100x32 design targets (median <=50 ms, p95 <=100 ms) are met in this run,
not guaranteed on other hardware or with terminal/game overhead. Larger frames
cost more; no city size/height reduction was used to get these numbers.
`docs/renderer-frames/performance.json` retains all samples, per-scene statistics,
method and machine information. The earlier unoptimized 100x32 median 53.1717 ms
missed the median target (`docs/renderer-performance-before.json`). Profiling
showed spatial broad phase plus material/shading work and duplicate camera-ray
construction. Retaining lens clip distances removed redundant ray work without
changing ANY rendered glyph/color/depth. `docs/renderer-profile.txt` records a
final changed-pose profile; instrumented times are not benchmark times.

## Honest remaining limitations

Static pose/seed output is deterministic and repeated frames are exact. One
center sample per cell is NOT full spatial/temporal antialiasing: thin cornices,
windows and paving joints can pop when moving or at low resolution. Fog/glyph
simplification reduces remote clutter but does not remove all shimmer. No
supersampling, temporal jitter, hidden painting or camera-dependent fake doors.
ASCII alone loses the colored mass hierarchy; use the RGB preview for review.

The captured glyph rows were inspected and HTML was structurally/semantically
validated; no actual browser display, interactive terminal session, Windows
runtime, continuous moving-camera playtest, full game or human beauty/fun judgment
is claimed. The CSS preview is not proof a particular terminal font/palette will
look identical. Directional factors have no cast shadows; all ground is paving;
landmarks remain axis-aligned extruded solids with sampled decorative crowns.
Movement, lifecycle/restoration, HUD, controls, game rules, boundary presentation,
release artifacts and independent aesthetic/play assessment remain with their
separate nodes. Completing this renderer does not complete the root mission.
