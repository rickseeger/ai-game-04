# Street-level perspective — node 4 handoff

Renderer-independent camera math on foundation/spatial/appearance commit
`52ffeaf`. `contracts.py`, City/RayHit, appearance, spatial generation and the
foundation CLI are unchanged. No rendering, input, movement/collision or game
rules are introduced. This is a projection component, not a playable city.

## Approved units and usage

Metres and radians; x east, y up, z north. Ground is y=0, eye is 1.7 m above
feet. Buildings retain their real metre heights; nothing scales towers down to
fit the frame. Yaw 0 faces +z and positive yaw turns toward +x. Positive pitch
looks up. Poses normalize yaw into [0,2*pi), clamp pitch to [-pi/3,+pi/3], and
never modify the supplied frozen shared values. No roll, bobbing or motion.

    from citywalk.camera import Perspective, camera_from_player
    from citywalk.contracts import Player, Vec3, Viewport
    camera = camera_from_player(Player(Vec3(0, 0, 0)))
    viewport = Viewport(100, 32)  # scene only; caller removes HUD rows
    projection = Perspective()
    q = projection.project(Vec3(2, 3.7, 20), camera, viewport)
    direction = projection.ray(49, 15, camera, viewport)

`Perspective` implements the unchanged `contracts.Projection` protocol:

- `project(point, camera, viewport) -> Projected | None`
- `ray(column: int, row: int, camera, viewport) -> Vec3`

`camera_from_player(player, *, hfov=Camera.hfov, near=Camera.near,
far=Camera.far) -> Camera` is an additive assembly helper, not Walker. It rejects
feet off ground y=0; diagnostic non-player poses can use `Camera(eye, ...)`
directly at any finite eye height. Direct Camera values get the same angle
normalization/clamping when prepared. Defaults are HFOV 80 degrees, near .10 m,
far 500 m; default cell width/height is .5. No CLI flags are added here.

## Equations and physical cell aspect

For yaw a, pitch b, the orthonormal world basis is:

    right   = (cos(a), 0, -sin(a))
    up      = (-sin(a)*sin(b), cos(b), -cos(a)*sin(b))
    forward = (sin(a)*cos(b), sin(b), cos(a)*cos(b))
    delta = point - eye
    X = dot(delta, right); Y = dot(delta, up); Z = dot(delta, forward)
    fx = columns / (2*tan(hfov/2))
    fy = fx * cell_aspect
    column = columns/2 + fx*X/Z
    row    = rows/2 - fy*Y/Z

Physical image aspect A = columns*cell_aspect/rows, so VFOV is
2*atan(tan(hfov/2)/A). At 100x32 and .5, fx=59.587679630 columns,
fy=29.793839815 rows, VFOV=0.985652190 rad. A square perpendicular to view has
column_extent*cell_aspect == row_extent; it is not squeezed by tall terminal
characters. Resizing preserves HFOV and recomputes VFOV; no hidden HUD deduction.

Image origin is upper left, and screen center is (columns/2,rows/2). Each ray
passes through (column+.5,row+.5); odd dimensions have a true central sample,
even dimensions straddle the center. Ray uses camera-space direction
((column+.5-columns/2)/fx, (rows/2-row-.5)/fy, 1), normalized then rotated into
world space. These are rectilinear image-plane samples, NOT equal angular steps
per column. The latter would produce the wrong perspective near screen edges.
Pitch rotates the full 3D basis: looking up is not merely shifting a horizon row.

## Clipping, depth and renderer integration

`project` returns None for Z < near or Z > far, including eye-plane and
behind-camera points, BEFORE perspective division. Near and far are inclusive.
It also returns None outside [0,columns) x [0,rows). No snapping/clamping of
screen coordinates or perspective coordinates onto the near plane. Projected
depth is forward-camera Z in metres, NOT radial distance. Screen-boundary tests
use the computed binary64 result; no hidden epsilon grows the frustum. A point
constructed exactly on a rotated plane can round to either side; the renderer
must use an explicit numerical boundary policy for intersection reconstruction.

For a frame, prepare once rather than recomputing camera trigonometry per cell:

    prepared = projection.prepare(camera, viewport)
    direction = prepared.ray(0, 15)
    t_near, t_far = prepared.ray_clip_range(0, 15)
    q = prepared.project(Vec3(2, 3.7, 20))
    offscreen = prepared.project_unclipped(Vec3(0, 100, 20))

`prepare` returns frozen `PreparedPerspective`, with normalized `camera`,
`viewport`, `right`, `up`, `forward`, `focal_columns`, `focal_rows` and `vfov`.
Obtain it via prepare, not by manually constructing its derived fields. Its
`project`/`ray` take only point/indices. `project_unclipped` omits SCREEN clipping
only and still rejects outside near/far; it helps inspect offscreen towers but
is not a line/polygon clipper. There is no global or growing cache. Re-prepare
on pose, lens or viewport change; existing prepared objects remain immutable.

`ray_clip_range(column,row)` returns inclusive eye-relative distances
(near/cos(theta), far/cos(theta)), with cos(theta)=dot(unit_ray,forward).
The implementation computes the same cosine in camera space to avoid world-dot
cancellation for very wide fields of view. For cell (0,15) in the default
viewport: t_near=.130013787 m and t_far=650.068933136 m, NOT .1 and 500.
A plane Z=20 hits that ray at distance 26.002757325 m while projected depth is
exactly 20. This distinction prevents fisheye wall-height distortion.

Future renderer responsibilities (not implemented or validated by this node):

- Use normalized world rays for `Spatial.raycast`. Its `max_distance` is a ray
  distance, so use t_far, NOT camera.far. Near/far clip in forward depth.
- If a nearest eye-origin hit is before t_near, do not just discard it and call
  the pixel sky: other surfaces can lie in the valid interval. Query beyond the
  near cutoff (or use an equivalent interval-aware intersection strategy).
- `Spatial.raycast` ignores distance-zero surfaces. A shifted-origin strategy
  needs a small documented boundary offset and filtering policy to include
  surfaces exactly at near without self-intersection or skipping the next hit.
  Do not silently treat these point projection tests as renderer clip tests.
- When shifting ray origin, add the shift distance back to RayHit.distance
  before storing `Frame.depth` or applying distance fog. Preserve the actual
  hit point/normal/face/building id for `Appearance.sample(city, hit)`.
- `Frame.depth` remains original-eye normalized-ray metres; sky is infinity.
  Along ONE ray, ray distance and forward depth produce the same ordering.
  Across rays, they are different quantities and cannot be interchanged.
- Occlusion, opaque nearest-hit selection, target/crown sighting rules, lighting,
  fog, silhouette filling and terminal glyph output belong to the renderer.
  Do not discard an entire building just because its crown projects to None.

No new Protocol methods or shared fields are required. Consumers needing only
`Projection` may keep using the two foundation methods; optional preparation and
clip-range helpers belong to the concrete camera implementation.

## Validation and reproducible numerical evidence

    python3 -m unittest discover -s tests -p test_camera.py -v
    python3 -m unittest discover -s tests -v
    python3 tools/measure_projection.py
    python3 tools/measure_projection.py --check
    python3 tools/preview_appearance.py --seed 11 --check
    python3 tools/build.py
    python3 dist/lantern-survey.pyz --smoke --seed 11

Windows with Python 3.11+: replace python3 with py -3. No third-party packages.
The fixture tool works from any directory. `--output PATH` selects a scratch
file. `--check` is read-only and fails for absent, malformed or stale fixtures.
The JSON records input camera/viewport/world points, clipped/unclipped results,
a 100 m Building with all eight corners in four poses, five cell rays and their
clip ranges, plus real City landmark target/crown probes and target RayHits for
seeds 11,93,2026. No artificial screenshot or city art is represented.

JSON preserves full binary64 input/output precision for direct pose/point
replay; the examples below are rounded. Check uses absolute tolerance 1e-8 to
allow platform libm final-bit differences. Classification, identifiers, array
lengths and other discrete data must still match. Tests independently verify
known pinhole numbers, sequential yaw/pitch rotation covariance, straight edges,
all-cell round trips across four viewport sizes and four poses, and actual
spatial target hits. Tests also replay the serialized camera/point inputs directly. The committed
fixture is a regression reference, not the sole correctness oracle.

Observed default-camera probes (column,row,forward depth):

    world (2,3.7,20) -> (55.958767963,13.020616019,20)
    world (2,3.7,40) -> (52.979383981,14.510308009,40)

Doubling distance halves both offsets from (50,16). At just 20 m from a 100 m
facade, the base projects to row 18.532476384, but the crown is row -130.436722690
and project returns None. With pitch +pi/3, the same crown projects inside at
(50,6.031327434), depth 95.130297192, while the base is below the frame. This
shows human-scale towering geometry without compressing height. The same crown
fits at 200 m in the level view. At yaw -.2/0/+.2, its horizontal projections
are 62.079020654/50/37.920979346: turning right moves fixed geometry left.

`docs/camera-run.json` records actual full-suite output, command return codes,
platform/Python, source/fixture/build hashes, deterministic rebuild and honest
foundation launch output. At this milestone 49 regression tests pass, including
16 camera tests; original spatial and appearance fixtures remain unchanged.
The worker records final commit SHA, push read-back and fresh remote validation
outside the repository in `../completion-evidence.json`, avoiding self-SHA claims.

## Validation limits and rejected inputs

Positive integer dimensions/indices are strict (bool is not an index), cell
aspect must be positive, FOV strictly between 0 and pi, and 0 < near < far.
Nonfinite or wrong numeric types, invalid player feet, out-of-range ray cells,
and nonrepresentable derived floating-point scales raise ValueError rather than
emit NaN/infinity. Extremely tiny FOV/aspect or huge dimensions can be finite yet
numerically unusable and are rejected. Finite world deltas/projected coordinates
that overflow also raise ValueError. Binary64 limits apply; metre-scale city
coordinates and approved settings are the intended operating range.

No Windows runtime or Python 3.11 runtime was exercised locally; a Python 3.11
syntax parse is not execution proof. Local evidence is Linux/Python 3.14.4.
Configured CI is not a claimed observed CI pass. No renderer performance,
anti-aliasing, complete near-clipped city rendering, movement, input, gameplay,
city beauty or enjoyment is established. Those independent integration and
experiential gates remain open with their assigned owners. No tree/node state
was modified by this task-scoped worker.
