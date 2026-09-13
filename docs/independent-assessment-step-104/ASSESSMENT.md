# Independent candidate assessment — node 11, step 104

Verdict: BLOCKED on an actual human playtest. Not accepted. This worker did not
complete a meaningful experiential session and cannot truthfully judge beauty
or enjoyment through the available text-only interface. No node completion,
contract edits, harness changes, Windows validation, or root approval is claimed.

## Provenance and independent execution

Actual delivered Linux tarball, copied unchanged from node_10_step_103/deliverables:
lantern-survey-linux-7c877935eacfecdb39100528713b74fbfd55527a.tar.gz
Source commit: 7c877935eacfecdb39100528713b74fbfd55527a
SHA-256: dde8c725ecac97b59544cb0552b35af06a90acf0402a91abc5d621dd32458d9b
Evidence checkout base: 48dbdecbe77a0426dcb1d81d65d42fcfa41d138b
The subsequent evidence commit is not a new game build. All installed payload
hashes were verified against BUILD.json AND the identified Git source blobs.
See artifact-verification.json. The exact small tarball is committed beside this
report, so a tester need not access a server-only distribution path.

Read before testing: README.md, docs/linux.md, docs/linux-revalidation-step-103.md
and its JSON, docs/gameplay.md, the packaging source and capture/app/PTY interfaces.
Earlier automated victories and worker assertions were not reused as new proof.
The fresh probe uses only the existing Session PTY transport/capture/cleanup,
not full_run, its route solver, or injected game state. probe.py is the new action
sequence. The installed candidate ran outside the checkout, on Linux x86_64,
glibc 2.43, Python 3.14.4, a 100x36 controlling xterm-256color PTY emitting truecolor.
An undersize 70x20 transition was also exercised. No DISPLAY or WAYLAND_DISPLAY
was configured. More importantly, this session has no image-view/browser-render
observation tool: terminal results expose strings and files, not a visible color
emulator or a physical keyboard experience. A web extraction tool cannot supply
that missing local visual/experiential interface.

## Route, actions and actual observations

49.584 seconds wall time; 917 rendered frames, 26 RGB checkpoints, approximately
112.727 metres walked excluding restart. This is a bounded technical probe,
NOT a meaningful playthrough. Exact timed key bytes are in runtime/inputs.json;
coordinates, actions, HUD, rules and collisions are in runtime/trace.jsonl.
probe-notes.json records the named route stops.

At seed 11 spawn (0,0), read initial help, photo rules and the Amber Spire card.
Start with H; E correctly rejects submission with zero photos. Hold W north to
z=40.542m; pause to capture. Turn right with L and look up with I (yaw 1.8544,
pitch 0.5934 radians). SPACE misses. Advance into the facade: first collision
frame 349 at x=7.700m, z=38.288m. Continued forward input slides along it; A
strafes clear, S backs away, K lowers view. Open/close help; shrink and restore
terminal; R resets; W+D walks diagonally from the depot into another facade.
Q exits with code 0. There were 236 blocked frames, no photos and no victory.
No conclusion about human discoverability follows from this intentionally short,
unoptimized action sequence.

I inspected actual captured glyph output for frame 0 and look-up frame 293 and
read their camera/RGB data. The glyph-only spawn shows facade columns beside a
converging dotted street; the look-up capture changes the facade/sky geometry.
Camera eye height is 1.7m. Those frames contain 467 and 547 distinct RGB fg/bg
pairs respectively. These are real output facts, NOT perceived color quality,
a screenshot evaluation, or evidence that the city feels tall or attractive.
Open runtime/frames.html for actual color-cell reconstructions, not physical
terminal screenshots. runtime/terminal.ansi.gz preserves the freshly emitted
ANSI stream; frames.jsonl.gz preserves RGB/depth cells.

Render median 42.787ms and p95 50.578ms at 100x36; presentation median 3.065ms.
These timings do not establish subjective responsiveness or input latency.
Q restored exact native termios, cursor visibility, normal screen and SGR reset
in this PTY (runtime/pty-result.json). Physical-emulator restoration and fresh
Escape/Ctrl-C coverage still require a real terminal; earlier records are not
represented as fresh checks here.

## Separate acceptance verdicts

Human-scale depth: UNASSESSED visually; numerical eye height and text geometry
are supportive technical evidence only.
Towering architecture: UNASSESSED visually; look-up geometry changes, but an
imposing human-scale impression has not been assessed.
Color and variety: UNASSESSED visually; real RGB emission is verified, harmony,
district distinction, readability and richness are not.
Worthwhile exploration: UNASSESSED; no meaningful discovery session completed.
Responsive controls: LIMITED technical pass for the exercised inputs; human
repeat timing, aiming precision and overshoot need playtesting.
Collision: LIMITED technical pass for observed facade blocking/sliding and
escape by strafing; not an exhaustive corner/tunneling or experiential verdict.
Terminal restoration: PASS only for this Q-exit Linux PTY scope; see above.
Genuinely interesting gameplay: UNASSESSED; no enjoyment assertion or scripted
victory substituted for a human session.

## Concrete shortcomings and narrowly scoped follow-up

1. Ambiguous photograph guidance: at frame 310 the HUD says Next Violet Clock,
37m away, but the reticle and failed photo say too far; approach within 65m,
without naming the aimed candidate. The navigation and reticle select different
landmarks (nearest unphotographed versus nearest bearing). This is not evidence
that range arithmetic is broken, but is a concrete unnamed-target feedback
problem. Targeted fix: name the reticle/rejection target (or explicitly distinguish
navigation target from aim target) and keep it readable at 80 columns. Reproduce
with this route, then fresh human play must verify the ambiguity is gone.
2. README historical terminal-adapter section still says native Windows Terminal
execution remains mandatory without qualifying it as deferred historical scope,
while current Linux instructions explicitly defer Windows. Targeted docs fix:
mark that legacy requirement as deferred. Do not alter the harness contract here.
Controller separately reconciles node 10 with Rick-authorized Linux-only scope.
3. The decisive visual/enjoyment evidence is missing. Do not infer boredom from
zero photos or beauty from dense glyphs. Human findings must become bounded fix
requests with route, expected/actual behavior and fresh candidate play after fixes.

Neither an automated rerun nor fixing these two textual issues closes the human
acceptance gate. No unbounded redesign is requested or implemented in this task.

## Precise blocking request to Rick / a Linux playtester

Please play this exact Linux candidate in an actual color terminal for a complete
survey attempt (up to its 600 active seconds), then briefly retry or explore a
second district. Do not use the worker route solver. Record your real outcome,
including getting lost, failed photos, losing or quitting; a win is not required
to give useful evidence. Windows is deferred; Andrew need not test Windows now.

From a fresh directory with Git, Python 3.11+, tar and sha256sum installed:

    git clone https://github.com/rickseeger/ai-game-04.git
    cd ai-game-04/docs/independent-assessment-step-104
    sha256sum -c SHA256SUMS
    TESTDIR=$(mktemp -d)
    tar -xzf lantern-survey-linux-7c877935eacfecdb39100528713b74fbfd55527a.tar.gz -C "$TESTDIR"
    stty -g > "$TESTDIR/terminal-before.txt"
    "$TESTDIR/lantern-survey-linux/lantern-survey" --seed 11 --capture-dir "$TESTDIR/human-capture"
    stty -g > "$TESTDIR/terminal-after.txt"
    cmp "$TESTDIR/terminal-before.txt" "$TESTDIR/terminal-after.txt"
    printf "Capture directory: %s/human-capture\n" "$TESTDIR"

Use 100x36 recommended (80x24 minimum), a real xterm-compatible UTF-8 color
terminal, and its own correct TERM. No pip dependencies. This is a Python-runtime
launcher, not a standalone binary. Do not run these interactive steps through
redirected stdin or a headless command runner. The checksum must match above.

SPACE pages help/cards; H begins. W/S walk, A/D strafe, J/L turn, I/K look;
SPACE photographs; E submits within 3m of the depot after 3 distinct photos;
P pauses; H help; R restarts; N next seed; Q/Escape quits. Movement is terminal
key-repeat with a 140ms hold, not native key-up. Do not paste movement strings.
Use the cards and bearings to find landmarks; explore both a narrow street and
an open junction, look from ground to crowns, try a facade and corner collision,
frame a photo, improve its crown composition if possible, and attempt the depot
return. Pause to take actual screenshots of street, look-up tower, distinctive
district/landmark, photo feedback and final outcome. Save a short real gameplay
screen recording if available. Then test shell typing after Q; launch short fresh
runs to check Escape and Ctrl-C and report restoration failures verbatim.

Return: tester name/date; distro/Python/terminal/font/grid; artifact checksum;
route and time spent; actions, photo count/score/outcome; screenshots/recording;
human-capture directory; before/after terminal files; and separate yes/no/mixed
answers with concrete examples:
  - Does depth feel street-level, rather than a flat wall or overhead map?
  - Do the towers feel imposing when looking up? Which view demonstrates it?
  - Are colors readable and districts/architecture visibly varied?
  - Did exploring reveal worthwhile views, or just repetitive corridors?
  - Can you move and aim reliably without annoying overshoot or latency?
  - Do walls/corners block naturally, and can you recover without getting stuck?
  - Do Q, Escape and Ctrl-C return a usable, correctly restored shell?
  - Was finding/framing/returning genuinely interesting? What decisions mattered?
    Would you voluntarily play again? What specifically was dull or frustrating?

For every failure, give location/landmark, action, expected versus actual result
and screenshot/time marker. Controller should dispatch targeted fixes, identify
the new artifact and require FRESH play of affected routes plus a full enjoyable
survey attempt before acceptance. Node 0 is not proposed complete here; all
remaining delivery gates must validate and Rick retains root approval.

## Evidence use and reproduction

assessment.json is the machine-readable limited verdict. probe.py can reproduce
the technical sequence after extracting the included tarball under the checkout
parent as installed/lantern-survey-linux, and moving aside its existing runtime/
directory (the script refuses overwrite). It relies on this repository version
of tools.validate_app_pty.Session, not game logic injection. A repeat is new
technical evidence only. Runtime metadata records BUILD.json provenance; an
installed payload outside Git need not have a Git source_sha. Use its distribution
source_commit and artifact-verification.json rather than treating null as a
missing artifact identity. ALL_SHA256SUMS binds all evidence files except itself.
