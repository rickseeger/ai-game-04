# Lantern Survey rules — node 8 handoff

Implemented `citywalk.gameplay.SurveyRules` against the unchanged shared
`Gameplay`, `SurveyState`, `Sighting`, `Actions` and `GameResult` interfaces.
Read `docs/design.md`, contracts and implemented spatial/rendering/movement
APIs before implementation. The chosen design was retained, not replaced by
an easier route or weaker photo criteria. Nodes 1–7 are the prerequisites
identified in the task packet. Their design/status text is historical.

## Bounded loop and decisions

`start(city)` returns playing / 600 active seconds / zero photos / zero score.
Photograph any three of five different architectural landmarks, then return
within an inclusive horizontal 3 m depot radius and press E before time expires.
Three photos alone do not win. Fourth/fifth photos and composition upgrades are
optional risks; no extra time is granted. Taking the same easy photo repeatedly
cannot replace navigation to distinct neighborhoods. Knowing the avenues,
plazas, facade orientation, sightlines and way home is useful to progression.
Position controls horizontal range and occlusion; yaw frames the target and
pitch can expose the crown. The scoring maximum is five 140-point photographs.

Every eligible shutter chooses one target by (absolute bearing error, id).
Eligibility: known landmark id, finite horizontal range in [18,65] m, finite
bearing error with absolute value <=12 degrees, and Renderer-provided visible.
`visible` already means target is projected inside the scene/clip interval AND
unoccluded. Rules do not reimplement projection/raycasting or trust crown alone.
A new photo awards 100, or 140 when crown_visible. Later upgrades add only 40;
downgrades and repeats add zero. Already-photographed candidates retain normal
priority: the shutter does not secretly choose a second-best new landmark.
Duplicate sighting entries award at most once; an exact same-id/bearing tie
prefers the crown consistently. Renderer ordinarily emits each id exactly once.

Active step order: validate dt, preserve terminal states, validate playing-state
records, subtract FULL dt, lose at zero, otherwise shutter then submission.
Exact-deadline submission loses; simultaneous third shutter/E can win only if
time remains and the player is at the depot. A miss or invalid submission still
costs elapsed time. Won/lost returns the identical state and no messages for
all valid dt/actions. Invalid dt raises ValueError even in terminal phases.
Negative, nonfinite, boolean, nonnumeric and overflowing elapsed values are
rejected. Finite nonnegative zero is valid, including shutter/submission edges.

Feedback includes successful landmark names and awarded deltas, repeat/no-reward
notice, range/aim/visibility failure hints, premature/distant submission,
third-photo readiness, and win/loss/restart prompts. The shared Sighting has no
separate projected/occluded reason field, so the visibility hint accurately says
"occluded or outside the scene" rather than inventing a diagnosis. On a miss,
closest known finite-bearing target determines the hint; invalid/unknown-only
input reports no valid landmark. No film limit or hidden random success exists.

Photos remain unique immutable tuples, sorted by id, and score is their sum.
Invalid/foreign/duplicate photo records, invalid awards or inconsistent totals
raise ValueError rather than producing a false count or laundering a forged
score. This is defensive API validation, not a save-file anti-cheat system.
Caller supplies trusted City, Player and renderer Sighting contracts; external
input must not be allowed to construct those values directly. State has no seed
field: application MUST discard it whenever switching cities, even if ids match.
Rules import only contracts and math, and have no clock, rendering, filesystem,
terminal, random state or mutable per-session instance data.

## Node 9 responsibilities (not implemented or claimed here)

Instantiate/reset with `state = rules.start(spatial.city)` and
`player = walker.spawn(spatial)`. R reuses the same seed/world; N generates seed+1.
Both discard all old photos, score, phase, movement pose and feedback. Reset
edge latches/UI overlays and the active-time clock baseline as well; do not
charge time spent on a result screen to a new game. The tests reset the same
rules instance after playing/won/lost and replay actions from a fresh world.
There is no implicit reset from `Actions.restart` in `SurveyRules.step`.

Application owns quit first, restart/new seed, help/pause, undersize freeze,
terminal phase motion freeze, event edge detection and clock accounting.
Do NOT call movement/rules during help/pause/undersize or on result screens.
Passing dt=0 is NOT a pause substitute: shutter/E still act at dt=0. Ignoring
pause/help/restart flags inside these pure rules is deliberate and tested;
actual integrated pause/help/restart tests remain node 9, not a node 8 claim.
After resume reset the monotonic baseline to exclude paused time.

Active integration: input -> UI gating -> movement with min(dt,0.10) -> camera
-> real renderer sightings -> rules with full active dt -> render -> HUD/present.
Do not cap the rules dt after stalls. Application keeps event messages visible
for a readable duration (empty messages on an ordinary tick are not an erase
command). Build HUD from state and city: time, photos/3, score, seed, nearest
unphotographed bearing/range, depot bearing/range and reticle feedback.
No clocks or terminal orchestration were added to the rules. The default CLI
remains informational and is NOT yet an integrated playable application.

## Reproduction and evidence

From repository root, stdlib Python 3.11+:

    python3 -m unittest discover -s tests -p test_gameplay.py -v
    python3 -m unittest discover -s tests -p test_gameplay_integration.py -v
    python3 tools/simulate_survey.py --seeds 11 93 2026
    python3 tools/simulate_survey.py --replay docs/gameplay-simulation.json
    python3 tools/validate_gameplay.py

The validator records actual full-suite, simulation, action-only replay, build
and smoke commands, exit codes, stdout/stderr, timings, platform and input-file
SHA-256 values in `docs/gameplay-run.json`. Its Git HEAD is the prerequisite
base at validation time; file hashes identify the tested uncommitted snapshot
that is committed with this evidence. The delivering commit is reported by the
worker, not embedded circularly in its own files.

`docs/gameplay-simulation.json` contains complete ordered Actions/dt tapes,
seed, scene size, geometric route waypoints, every photo/submission event with
actual renderer sightings, poses, immutable state, elapsed time, distance and
final outcome. Replaying consumes ONLY the seed, viewport and Actions/dt tape;
recorded poses/photos are compared afterwards, never injected. It creates a
fresh world, safe spawn and fresh rules state, then verifies identical output.
The route planner uses the existing spatial graph witness to select a route,
but every translation, turn and pitch adjustment goes through Walker.step with
real collision queries; no player pose or photo state is assigned from a
waypoint. Every tick calls CityRenderer.sightings with the actual camera/world.
All movement, turning, looking, shutter and submission time is charged at dt
<=0.1 s. Endpoint clearance and walking-speed bounds are checked each tick.

Executed seed results (full precision retained in JSON):

| Seed | Actual distance | Active elapsed incl. framing | Photos / score | Outcome |
|---|---:|---:|---:|---|
| 11 | 878 m | 240.90 s | 3 / 420 | won at depot |
| 93 | 871 m | 239.15 s | 3 / 420 | won at depot |
| 2026 | 875 m | 240.15 s | 3 / 420 | won at depot |

All select sight-2 / sight-3 / sight-4, all under the unchanged 420 s route-time
target, all replay identically from clean state. No prerequisite defect was
encountered and no upstream algorithm/interface or fixture was weakened.
Integration tests also check all five actual viewpoint targets at both 80x20
and 100x32 scene sizes, plus a real 100-to-140 framing upgrade and rejection
when looking down removes target projection despite valid range/bearing.
Unit tests cover transition ordering, deadlines, submission distance/count,
all photo gates/boundaries, malformed values, candidate priority, unknown ids,
duplicate farming, upgrade deltas, optional five-photo score, corrupt records,
inert phases, elapsed validation and deterministic reset.

Limitations: this is an ideal planned headless route with numeric injected
Actions, NOT a terminal keyboard playthrough. No native Windows execution,
interactive pause, screenshot/beauty judgment or enjoyment assessment is
claimed. It establishes real-rule reachability and measurable navigation time,
not whether a human finds the routes, camera, timer or scoring enjoyable.
That remains node 11 independent play/quality assessment on node 9/10 delivery.
