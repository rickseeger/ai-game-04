# Spatial city — node 2 handoff

This implements `CityGenerator` and `Spatial` from the foundation at
21c1755ed2ce934eed7d2a3ad584ecc15236aed3. `citywalk/contracts.py` is unchanged.
Read `docs/design.md` for the game design; its node-1 status paragraph is historical.
No projection, facades, renderer, movement, terminal input or game loop is added.
The informational CLI intentionally still describes the non-playable foundation.

## Use

    from citywalk.spatial import CityGenerator
    from citywalk.contracts import Rect, Vec3
    spatial = CityGenerator().generate(11)
    city = spatial.city
    assert spatial.walkable(city.spawn, 0.30)
    candidates = spatial.nearby(Rect(-20, -20, 20, 20))
    hit = spatial.raycast(Vec3(0, 1.7, 0), Vec3(0, 0, 1), 500)
    path = spatial.path_to(city.landmarks[0].id)
    route = spatial.survey_route()

`SpatialWorld` implements the structural Spatial protocol. `city` is a read-only
property returning the existing frozen City value. `SpatialWorld(custom_city)`
also supports hand-authored fixtures, validating finite, positive building
volumes, in-bounds footprints and unique IDs. Overlapping custom buildings are
allowed for occlusion/tie fixtures; generated buildings never overlap.
No shared dataclass or Protocol signature changed. Imports only use contracts
and the Python standard library. Additional metadata is optional: consumers
requiring only the foundation Spatial protocol must not assume it exists.

## Coordinates and city construction

All distances are metres: x east, y up, z north. Closed bounds [-240,240] on
both ground axes; 480 x 480 m, flat ground y=0. Human feet y=0, eye y=1.7,
player radius 0.30 m. Height is actual solid geometry, not a display scale.
Building footprints are extruded from y=0 to height. Ordinary buildings 12–99 m
in 3 m storeys; landmarks 84–120 m. Generated footprint sides are at least 9 m.

Ten blocks per axis. Eleven road centerlines each way, with outer promenades
centered at +/-231 m and inner streets every 48 m. Roads have 12,14,16 or 18 m
clear width. Outer blocks are shorter to retain an 18 m boundary promenade.
Variable lot sizes, 2 m setbacks, unsplit/split/quadrant lots, 6 m through-lanes,
eight empty-block plazas, five distinct landmark districts. Every block is
surrounded by connected streets; splits extend fully through a lot, not into
blind courtyards. No interiors, overhangs, props or invisible interior obstacles.
Road centerline sightlines extend 478 m between the tested end positions.

Landmarks stand immediately north of reserved plazas. Their targets are the
center of the south facade at half building height. Viewpoints are eye poses
across those plazas, with yaw 0 (+z) and pitch aimed at the target. All five are
within the design horizontal photo range 18–65 m and have unobstructed target
rays. Crown rays hit the same landmark; this is geometric visibility only,
not proof of screen inclusion or a composition bonus with a future renderer.

Styles are stable opaque material hints: amber-brick, cyan-glass,
violet-artdeco, rose-stone, emerald-metal. Nearby ordinary buildings inherit the
nearest landmark district style. `material_seed` is a stable unsigned 32-bit
integer for later facade sampling. This node supplies no colors or glyph art.
IDs are stable within a seed, sorted for queries; ordinary IDs encode block and
split index, landmark-0..4 identify geometry, sight-0..4 identify objectives.

## Determinism

Generation v1 uses a local specified SplitMix64 stream with inclusive integer
ranges via modulo. It does not use global random state, hash(), time or unordered
iteration to choose geometry. Integer seeds are accepted (bool is rejected).
Geometry seeds are reduced modulo 2**64; thus seeds differing by 2**64 share
geometry, although City.seed retains the supplied integer. This is intentional,
not a guarantee of unique geometry for every arbitrary-size integer.

Reproducible seeds 11,93,2026 are tested across two fresh processes with
PYTHONHASHSEED=1 and 917; observed canonical City JSON SHA-256 values are pinned
in tests and recorded in spatial-measurements.json. Changing generation requires
an explicit version/handoff and refreshed golden evidence, not quietly changing
fixtures. Additional geometry/bounds tests cover 0,-1,2**63.

## Static query semantics

`nearby(Rect)` returns all intersecting CLOSED building footprints, deduplicated
and sorted by building ID. Touching counts; zero-area queries are allowed.
Inverted/nonfinite rectangles raise ValueError. Query rects may extend outside
the city; clamping the indexed search prevents unbounded cell enumeration.

`walkable(feet, radius)` tests the exact horizontal disc against the nearest
point on each closed rectangle; square-expanded broad phase is not the collision
answer. Radius must be finite and nonnegative. Finite feet with y != 0 return
False; invalid numeric input raises ValueError. All building contact within
radius + 1e-6 m blocks. Boundary clearance must be strictly greater than that
padding too (consistent tangency rule); ground outside the city is not walkable.
Spawn/depot are the center intersection. The entire 3 m depot submission disc
has verified clearance. Landmark viewpoints provide additional safe placements.

`segment_clear(start, end, radius=0.30)` is an ADDITIVE static clearance query:
endpoints must be valid ground positions; it tests the entire closed swept disc
using segment/AABB intersection and exact endpoint/corner distances. It detects
thin obstacles even when both endpoints are safe. This is NOT player stepping,
wall sliding, input normalization, dt handling or a claim that later Walker
collision is correct. Use it to validate routes; movement still needs its own
independent integration/tunneling tests.

`raycast(origin, unit_direction, max_distance)` returns the nearest strictly
positive surface hit in metres along a normalized ray (unit tolerance 1e-6).
Nonfinite input, nonunit direction or nonpositive max_distance raises ValueError.
Building entry/exit uses full 3D slabs; origin inside returns the exit. A t=0
surface is ignored, so a surface origin directed inward reaches the far face,
and outward misses that building. Rays on closed edges count as hits. Offset
surface origins when a consumer needs self-intersection avoidance.

North is +z, south -z, east +x, west -x, roof +y. Normals point outward. The
finite ground plane uses face ground, building_id=None, normal +y. Below-ground
custom rays can hit building undersides (ground face, normal -y); at equal
distance the actual ground wins. Exact distance ties sort ground first, then
building ID, then face lexicographically. There are no ray walls at city bounds
and no infinite ground outside them. Upward rays through empty space miss.
A 24 m uniform grid accelerates both broad phase and projected-ray DDA traversal;
this is not a measured renderer frame-rate guarantee.

## Public-space and navigation metadata

Concrete `SpatialWorld.public_spaces` is a tuple of frozen PublicSpace(id, kind,
rect), with kinds avenue/street/promenade/plaza/lane. These are descriptive
regions, not extra colliders. Rects may overlap (intersections, crossing lanes),
and their closed edges may coincide with buildings or city limits; use disc
queries rather than assuming every point of a labeled rect is a safe player
center. All such rectangles have no positive-area building overlap.
Future rendering should visibly mark the outer promenade boundary/rail; no
invisible interior wall is introduced here and no rail rendering is claimed.

`navigation_points` (feet Vec3) and `navigation_edges` (undirected index pairs)
form a 131-node/230-edge witness graph. Node 0 is the depot. Main-road
intersections plus orthogonal plaza connectors reach all five viewpoints.
`destination_nodes` stores immutable (sight_id,node_index) pairs.
`path_to(id)` returns a depot-to-viewpoint point tuple (unknown IDs raise KeyError).
`survey_route()` searches three-distinct-destination permutations using shortest
graph paths, returning frozen RouteWitness: IDs, feet points (depot at each end),
distance_m, walking_seconds at 4 m/s, and 45 positioning seconds (15/photo).
This is optimal on this graph, not an assertion of globally shortest free-space
walking. A custom SpatialWorld without navigation has no implied route support.

## Actual validation and remaining gates

    python3 -m unittest discover -s tests -v
    python3 tools/measure_city.py --seeds 11 93 2026
    python3 tools/build.py
    python3 dist/lantern-survey.pyz --smoke --seed 11

Full stdout/stderr, return codes and platform are in spatial-run.json. Detailed
measurements, all viewpoint poses and depot paths, route points, actual query
checks and reproducible geometry hashes are in spatial-measurements.json.

Tests include independent plane-intersection ray oracles, brute disc/rectangle
and nearby oracles, a numerical convex-distance sweep oracle, tangencies,
corners, inside/surface/parallel rays, distance cutoffs, ties, invalid inputs,
and the explicit point-passable but player-too-narrow counterexample. Query
correctness is NOT inferred from a connected map. Source-level generation
checks cover scale, nonoverlap, public-space clearance and dimension variation.

Across each representative seed, every navigation edge is continuously clear
for the player and even a 1 m radius; all five destinations are safe/reachable.
A full 2 m exploration lattice flood requires continuous swept-disc clearance
on every traversed edge, not just free endpoints. Every sampled free point is
reachable (counts recorded per seed). This finite sampling is supporting
evidence, not a mathematical proof about every real-valued point. Through-lane
and setback construction avoids isolated unsampled courtyard pockets.

A three-viewpoint depot-return geometry replay samples every route segment at
<=0.1 m and checks real queries and target rays. Measured routes are 878/871/875 m
for seeds 11/93/2026; walking plus the explicit framing allowance is
264.50/262.75/263.75 seconds, below the 420 s design budget. This is NOT a scored
three-photo game simulation: Walker, Perspective/Renderer and SurveyRules do
not exist yet. Their owners must replay these fixtures through real components,
verify photo eligibility/crown projection, score, return submission and timer.
This qualification resolves the foundation design request for a future full
simulation without violating this node contract excluding movement/gameplay.

No Windows runtime, interactive collision, terminal lifecycle, rendered city
beauty or gameplay enjoyment is claimed. Source tests/build run locally;
configured CI is not observed CI evidence. Independent quality gates remain.
