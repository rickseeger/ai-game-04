# Ground walking and collision — node 6

## API and existing-world handoff

    from citywalk.contracts import Actions
    from citywalk.spatial import CityGenerator
    from citywalk.movement import Walker
    from citywalk.camera import camera_from_player

    world = CityGenerator().generate(11)
    walker = Walker()
    player = walker.spawn(world)  # validates the actual City.spawn
    result = walker.step(world, player, Actions(forward=1, strafe=1), 0.05)
    player = result.player
    camera = camera_from_player(player)

`Walker.step(Spatial, Player, Actions, dt) -> MotionResult` implements the
unchanged Movement protocol and returns immutable shared values. `Walker` has
no clock, input state, terminal access, RNG, world copy or concrete-peer imports.
It can be shared across players/worlds; actions are injected by callers/tests.
`Walker.spawn(Spatial) -> Player` is an additive convenience method with default
yaw/pitch zero. It validates the approved City.spawn, NOT a replacement spawn
search. Invalid spawn/current feet raise ValueError, including dt=0 or idle;
there is no teleport, depenetration or hiding invalid city data.

The one explicit protocol addition is
`Spatial.segment_clear(start: Vec3, end: Vec3, radius: float) -> bool`. The real
`SpatialWorld` already implemented this method in node 2. Its implementation is
unchanged: an exact closed-disc sweep using existing footprints, spatial index,
world bounds and epsilon. Both endpoints and the entire segment must be clear.
Movement passes radius explicitly. Existing renderer/camera/appearance methods
and all shared dataclass fields/signatures are unchanged. Future test doubles
for Movement must implement this query as well as walkable/city; an endpoint-only
query is NOT a valid substitute. The protocol-only adapter test exercises this
handoff without assuming navigation metadata or concrete world internals.

## Metres, elapsed seconds and injected axes

Feet remain at y=0. The unchanged camera helper adds exactly 1.7 m eye height;
looking does not affect walking speed, slope, height or collision. x is east,
z north, yaw zero points +z and positive yaw turns toward +x. Forward/back and
right/left strafe use (sin yaw, cos yaw) and (cos yaw, -sin yaw) in x/z.

Full walking speed is 4 m/s in all directions, with instantaneous start/stop
(no acceleration, inertia, sprint or bobbing). Local forward/strafe vector is
divided by max(1, its length): diagonals cannot run faster, and analog magnitude
below one is preserved. Forward/strafe/turn/look must be finite numeric axes in
[-1,1]; out-of-range values are rejected rather than silently saturated. Bool,
strings and unrepresentable/nonfinite numeric inputs raise ValueError.

Yaw rate is 90 degrees/s; pitch rate 60 degrees/s. Yaw is normalized to [0,2*pi)
and pitch clamped to +/-60 degrees before and after stepping, matching camera
pose conventions. Turning/looking continue even when walking is blocked. At a
pitch limit reversing look immediately moves away from it. dt=0 preserves valid
canonical poses and reports no blockage; out-of-range finite angles are still
canonicalized. Idle steps do not count as blocked. MotionResult.blocked means
at least one requested translation component was shortened by collision during
this call, including partial movement/sliding; it is not persistent state.

Walking and turning together integrates the constant local velocity over each
subinterval analytically (midpoint heading multiplied by sinc of the half-turn
angle). This avoids an end-yaw/frame-rate steering bias and cancellation for
tiny angular rates. Free-space straight distances and constant-action turning
arcs agree across 20/60/120 Hz and a single long call, to floating precision.
The body never moves vertically and pitch does not enter the velocity equation.

## Collision, wall slides, corners and frame stalls

Moving calls subdivide their full dt into equal intervals no longer than 0.025 s,
so the displacement vector is <=0.10 m at full speed. Each interval resolves
world x first, then world z from the updated position. Each component uses the
real Spatial.segment_clear query with the designed 0.30 m radius. Contact within
1e-6 m of radius blocks, including boundary contact, just as walkable does.
No center-only or square-footprint approximations are substituted for the disc.

If a sweep blocks, 30 safe-side prefix bisections advance that component up to
contact (positional bisection error <=0.10/2**30 m, apart from floating rounding).
Bisection asks whether the entire prefix is clear, never whether only its end is
walkable; thus it remains monotone across thin obstacles and grazing corners.
The other axis still executes. A flat wall therefore preserves requested tangent
velocity, discards normal velocity and does not speed up the remaining axis.
No accumulated pressure/inertia means the player can immediately back away.

Corners are intentionally axis-resolved, not a continuous surface-normal slide:
  - Two perpendicular walls block both components; holding into a concave corner
    stays safely stopped, without jitter or penetration.
  - Direct diagonal pressure into a convex rounded disc/box corner can also stop
    both axes. Steer away/cardinally around it to proceed. The player is not
    automatically pushed or rolled around the corner.
  - Ordering is always x then z, with a small directional bias. Exact free-space
    arcs are integrated as short chords; actual collision trajectories follow
    these two axis legs, not a literal curved sweep. Every leg is swept safely.
  - Collision results are deterministic for a fixed action/dt sequence, but
    exact contact paths at corners are not promised invariant under arbitrary
    frame repartitioning. Flat-wall slides and unobstructed travel have explicit
    frame-rate consistency tests.

World bounds use the same finite-city clearance rule. Edges and boundary corners
stop/slide like solid walls; movement adds no invisible interior obstacles.
Rendering the intended visible outer promenade rail remains a renderer/integration
responsibility; no boundary visual or terminal integration is claimed here.

There is no silent dt clamp inside Walker: 30 s really requests 120 m. Tests
exercise 1, 5 and 20 s building challenges and 120 s boundary traversal. Sweeps
also catch a thin grazing fixture with BOTH substep endpoints walkable, where
substep endpoint tests alone would tunnel. Runtime is proportional to the number
of substeps (and blocked axes need extra sweep queries); enormous finite dt is
not a constant-time API. Unrepresentable derived step counts/angles raise
ValueError rather than producing NaNs. Production integration MUST cap simulated
motion dt at 0.10 s after a stall, while giving gameplay the full active elapsed
time, as the design specifies. Motion never reads or changes a gameplay timer.

## Application responsibilities (later nodes, not implemented here)

Call spawn before starting/restarting an interactive session and report any
ValueError. Map terminal events to Actions elsewhere. Gate quit, pause, help,
win/loss and too-small-terminal states BEFORE calling movement; non-motion flags
in Actions are deliberately ignored here, not interpreted as UI policy. Use the
returned player with camera_from_player. No terminal input, lifecycle, gameplay
strategy, packaging or broad application wiring was added in this node.

## Real verification and limits

    python3 -m unittest discover -s tests -p test_movement.py -v
    python3 -m unittest discover -s tests -v
    python3 tools/validate_movement.py

The validation tool records exact command arguments, stdout/stderr, return codes,
wall timings, platform/Python and SHA-256 of source/test/documentation inputs in
`docs/movement-run.json`. It runs the focused suite and the full pre-existing
regression suite plus the new tests; no fabricated captures or substitute data.
The test-only small geometry uses the real SpatialWorld implementation; the
seeded collision, wall, corner, spawn, large-frame and replay tests additionally
use actual generated cities for seeds 11, 93 and 2026. Accepted axis sweeps are
checked by an independent all-building interval-distance oracle, separate from
the production sweep algorithm and index. A deterministic randomized action tape
checks safe endpoints through turns and variable dt; it is not exhaustive proof.

During development an initial test expected diagonal input to roll automatically
around a convex corner. Real execution stopped instead, consistent with the
specified x-then-z axis solver. The test and this handoff now explicitly require
safe, repeatable stopping there and immediate escape when steering away; no
surface-normal corner steering is claimed or added silently.

The first full regression run found two renderer fixture checks failing solely
because the shared contracts source fingerprint had changed. The real capture
generator was rerun; complete frame payloads and HTML/text bytes were asserted
unchanged before updating only frames.json source metadata. The initial real
output is retained in movement-run-before-fixture-refresh.json; exact old/new
hashes and unchanged-payload assertions are in movement-fixture-refresh.json.
No renderer code, geometry, images or tests were changed to bypass the checks.
The final run includes a read-only renderer fixture regeneration check.

This is numerical/headless movement validation, not keyboard responsiveness,
Windows runtime, complete gameplay, human-scale visual judgement or fun proof.
The full game still needs independent controller/human validation in later nodes.
The submitted commit SHA and push readback are recorded separately in the worker
result; the committed run records its tested input hashes rather than attempting
to put a self-referential commit SHA in its own contents.
