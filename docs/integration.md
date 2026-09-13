# Playable application integration (node 9)

Launch `python3 -m citywalk` in a real ANSI terminal. Python 3.11+; standard
library only. The real city renderer now fills all but FOUR terminal rows at
100x36 (recommended) and 80x24 (minimum). A single-cell + is the aiming reticle;
no map, menu or result box is painted over the city. Color defaults to truecolor;
`--color 256` selects the existing quantized terminal adapter. Adjust physical
cell width/height with `--cell-aspect 0.5` (default).

## Onboarding and controls

The initial four-row help strip freezes time. SPACE pages through instructions
and five landmark cards: names, districts, facade clues, height and current
compass bearings. H or P begins/resumes. In play:

- W/S walk, A/D strafe. J/L or left/right arrows turn.
- I/K or up/down arrows look up/down; SPACE photographs.
- E submits within 3m of the starting depot, with at least three photos.
- P pauses, H opens/closes help/cards. Both freeze motion and time.
- R restarts the same seed; N generates seed+1. Both reset photos, time and pose.
- Q/Escape quits; Ctrl-C is an emergency exit with terminal restoration.

Tap or repeat movement keys: terminal events have a 140ms renewable hold, not
reliable key-up events. Shutter/UI keys require 250ms without repetition before
another edge. This is a terminal constraint, not a claim of precision key holds.
HUD gives time, distinct photos/3, score, seed, depot and nearest unphotographed
landmark bearings/ranges, current reticle rejection/eligibility, and feedback.
Long event feedback is wrapped across successive two-second HUD messages rather
than covering the city. After three photos, return-to-depot guidance persists.
Win/loss freezes both movement and time; results and restart instructions remain
in the same four HUD rows. Small windows show the adapter resize/quit notice;
time and motion freeze and resume without a resize catch-up jump.

## Wiring and clock

`Application` owns one generated Spatial, validated Walker.spawn, one appearance,
Perspective-backed renderer and SurveyRules. Each active tick is input -> UI
priorities -> capped movement -> camera -> real renderer sightings -> rules ->
actual scene rendering -> HUD -> terminal present. Rules are never fed fabricated
sightings or photo counts. Raw real monotonic elapsed is charged to gameplay;
movement alone is capped at 0.10s after a stall. Target scheduling is at most
20Hz, sleeping after the complete tick; no busy-spin while keys are queued.
UI transitions discard the interval at the boundary (at most one frame in normal
play), and the first tick after a too-small viewport discards inactive elapsed.
Quit has priority over resets/UI. On reset, N takes precedence if both N and R
are in the same poll. Existing terminal context restoration runs on normal quit,
frame limit, exceptions and supported interrupts. SIGKILL remains uncatchable.

## Capture and exact reproduction commands

    python3 -m citywalk --capture-dir /tmp/lantern-live --seed 11
    python3 -m citywalk --capture-dir /tmp/lantern-profile --frames 300
    python3 tools/validate_app_pty.py --output /tmp/lantern-pty
    python3 tools/verify_app_evidence.py /tmp/lantern-pty
    python3 tools/validate_app_interrupts.py
    python3 tools/validate_integration.py
    python3 -m unittest discover -s tests -v
    python3 tools/build.py
    python3 dist/lantern-survey.pyz --smoke --seed 11

The PTY driver takes several real minutes. It opens a controlling Linux PTY,
launches the actual `python3 -m citywalk` CLI, and sends ONLY real documented key
bytes. Read-only per-frame telemetry guides key choices along the pre-existing
city route witness. No direct movement/rule calls, pose injections, accelerated
clock, modified deadline or seeded photo records occur in this application run.
It first pages onboarding, rejects premature submission, collides with a real
facade, restarts, tests pause and resize (including 300 minimum-size frames),
walks/turns/looks/photographs three distinct landmarks, returns and wins, tests
result freeze, restarts, starts seed+1 and quits. Native Linux termios before,
during and after are compared exactly, and actual ANSI entry/exit is checked.
The evidence verifier separately replays recorded Actions/dt through Application
and regenerates captured rendered checkpoints. That consistency check is not a
substitute for the real PTY run: the full byte transcript and input log remain.

Capture files in `docs/app-pty/`:

- metadata.json: base Git SHA/dirty flag, exact module hashes, platform/Python,
  command line, seed, aspect, color, clock policy and limitations.
- trace.jsonl: actual per-frame elapsed/input/state/pose/sightings/HUD/timings.
- inputs.json: raw injected key bytes as hex with monotonic timestamps and the
  last observed frame; explicit terminal resize operations.
- terminal.ansi.gz: LOSSLESS compressed raw PTY bytes (no newline normalization).
- frames.jsonl.gz: actual checkpoint cells, RGB, depths (sky is null), camera,
  viewport, actions, state, labels and timings, not imagined city drawings.
- checkpoints.ansi.gz: the actual terminal-present output at those checkpoints.
- frames.txt / frames.html: plain and colored views of those same Frame cells.
- timing.json: samples summarized by total terminal size, including cold/paused
  frames. Render excludes HUD/ANSI/capture; present includes HUD, ANSI encode,
  output write and flush into the concurrently drained PTY. Trace has raw data.
- pty-result.json / summary.json: actual result, collision/photo/win frame IDs,
  exit status, exact termios, byte count/hash and modeled VT restoration.
- verification.json: read-back integrity, exact trace/frame regeneration results.

`--smoke` now assembles and renders the real city without changing modes. A
redirected interactive launch fails with actionable TTY instructions. Headless
renderer tools remain available; the proposed design-stage `--fixed-dt` and
`--replay` CLI flags are intentionally not exposed as playable clocks. The
real-time PTY driver plus evidence verifier provide reproducible input/capture
validation without permitting a benchmark to masquerade as real-time play.

## Scope boundaries

The complete scripted keyboard route and material/frame evidence are engineering
checks, NOT independent validation of architectural beauty or gameplay enjoyment.
There is no native Windows runtime claim from this Linux worker. Distribution
verification is node 10; independent play/appearance assessment is node 11.
Performance numbers and executed commands are recorded in the adjacent runtime
and regression reports, not inferred from design targets or test counts.

`docs/app-lifecycle/` records additional actual application Escape/256-color,
Ctrl-C, SIGTERM and deliberately injected fourth-render exception runs. All
compare exact native termios restoration and actual VT exit bytes. The expected
interrupt/error exit codes are not labeled successful gameplay. The fault case
patches rendering only, runs the real main/context manager, and records the exact
launch code and traceback. `docs/integration-run.json` contains full executed
regression output, local build/smoke results, CPU/OS/Python and source hashes.

## Recorded execution result

The actual Linux PTY run won with three distinct 140-point photos (420 total),
using 232.994 active seconds. Full driver wall time (including paused checks and
transcript compression) was 270.446s. Q exited 0 and restored termios exactly.
The read-back verifier matched all 4,821 actual tick records and regenerated
all 24 checkpoint frames exactly. Full unittest discovery passed 150 tests.
Local source and built zipapp smoke commands also exited 0. Lifecycle PTYs
restored exact termios for Escape/256-color (0), Ctrl-C (130), SIGTERM (143)
and deliberate render exception (1). These expected codes are recorded, not
collapsed into an invented zero status.

Actual render times (all frames, cold/paused included; total terminal sizes):

- 80x24: 304 frames, median 17.563ms, p95 23.268ms; present median 1.849ms.
- 100x36: 4510 frames, median 47.777ms, p95 58.746ms; present median 3.211ms.

80x24 measurements are paused depot frames; 100x36 includes moving city poses,
onboarding and gameplay. Other validation processes ran concurrently during
part of the recording. These are measured application costs under that load,
not an isolated benchmark or physical terminal-emulator latency claim.

Defects handled: the obsolete foundation CLI assertions were replaced with
real playable smoke/TTY safety checks. Capture HTML string quoting and the
lifecycle fault-driver quoting were corrected before their successful runs.
No unresolved integration defect was observed by these checks. Scripted
keyboard navigation does not settle human usability or enjoyment.

The PTY metadata base SHA predates this uncommitted implementation and explicitly
marks it dirty; exact SHA-256 hashes of EVERY application module bind the run
to the subsequently committed source. The verifier checks all those hashes.
Driver-only diagnostic/extra lifecycle-launch support was added while the
full route was running; application modules were unchanged throughout.

A fresh clone of the pushed integration commit also passed all 150 tests,
built and exercised the local zipapp, and verified the committed real PTY
evidence. Exact commands/stdout/stderr and the checked-out SHA are preserved in
`docs/fresh-clone-run.json`. Fixed-width frame trailing spaces are intentional;
Git attributes preserve compressed transcripts and suppress whitespace warnings
only for the actual frame text files, without altering captured data.
