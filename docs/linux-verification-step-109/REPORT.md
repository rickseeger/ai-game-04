# Independent Linux verification — G11 node 12, step 109

## Result and scope

The existing Lantern Survey candidate installed and launched successfully from a
new public HTTPS clone on Linux. No game implementation was replaced or modified.
The exact tested source revision is 26b206cea12e0e630036693a128a3de1b6fe61e9. The later evidence-only commit
containing this report is NOT a new tested game revision: use 26b206cea12e0e630036693a128a3de1b6fe61e9 when
rebuilding this delivery. Source, automated tests, packaging and the original
installation/control documentation already exist at that exact commit.

This is fresh scripted functional verification, not a human playtest. The scripts
send keyboard bytes to the real game in controlling Linux PTYs and observe actual
frames/state; they do not inject player poses, invoke gameplay rules to advance
the live game, or accelerate its clock. Route metadata and the existing validator
were reused after code inspection. New supplemental control/lifecycle checks and
an independent geometry/readback check were executed in this worker session.
Previous repository evidence is preserved unchanged. This report does not modify
mission state or declare any node durably complete.

Windows remains deferred. Beauty, exploration appeal and enjoyment remain gated
by node 11 and actual human playtesting; this report does not supersede its
assessment or claim those judgments passed. No unmet requirement was observed
within this Linux functional-delivery scope.

## Identified runnable delivery

Artifact: lantern-survey-linux-26b206cea12e0e630036693a128a3de1b6fe61e9.tar.gz
SHA-256: 6db2af41eabb18ae2aca449f14de0081722e88dc6d0f4f15f7ba8d98835630a6
Local durable directory: /opt/g-harness/workspace/G11/node_12_step_109/repo/docs/linux-verification-step-109
Repository directory: docs/linux-verification-step-109/

This tarball is a Python-runtime Linux distribution, NOT a standalone executable.
The archive includes an executable lantern-survey launcher, the committed Python
modules, BUILD.json with source revision and payload hashes, and a copy of the
Linux instructions. provenance.json and SHA256SUMS sit beside it. Two builds were
byte-identical on the tested Python/zlib toolchain. Both the legacy .pyz smoke
launch and installed tar launcher passed; the tar launcher is this delivery.

## Prerequisites and reproducible installation

Linux and Python 3.11+; no pip dependencies. To play, use a UTF-8 xterm-compatible
ANSI color terminal, at least 80x24 (100x36 recommended). Keep TERM set accurately
for that terminal. Truecolor is default; --color 256 also passed fresh PTY checks.
Python must be on PATH as python3, or set LANTERN_PYTHON to its executable path.
On Debian/Ubuntu, install python3 if absent. Source retrieval requires Git;
build/install verification uses tar and sha256sum. Isolated validation additionally
requires python3-venv. Only Python 3.14.4 was freshly exercised here; other supported
Python versions are not newly certified by this run. This is not a GUI, and
redirected stdin/stdout, TERM=dumb and Linux virtual consoles are unsupported.

From this report directory, verify and install into a new directory:

    sha256sum -c SHA256SUMS
    mkdir -p "$HOME/.local/opt"
    INSTALL=$(mktemp -d "$HOME/.local/opt/lantern-step-109.XXXXXX")
    tar -xzf lantern-survey-linux-26b206cea12e0e630036693a128a3de1b6fe61e9.tar.gz -C "$INSTALL"
    "$INSTALL/lantern-survey-linux/lantern-survey" --smoke --seed 11
    "$INSTALL/lantern-survey-linux/lantern-survey" --seed 11

The last command requires an interactive terminal; --smoke alone is NOT gameplay
validation. The launcher works from unrelated directories, including paths with
spaces. The actual validation used a fresh HOME, no third-party packages and an
unrelated working directory, and confirmed the game imported the installed code,
not the checkout. Remove only the newly created INSTALL directory to uninstall.
No persistent progress is saved; --capture-dir is an explicit opt-in evidence sink.

To rebuild and launch source from an empty directory:

    git clone https://github.com/rickseeger/ai-game-04.git
    cd ai-game-04
    git checkout --detach 26b206cea12e0e630036693a128a3de1b6fe61e9
    python3 -m unittest discover -s tests -v
    python3 -m citywalk --seed 11
    python3 tools/build.py
    python3 dist/lantern-survey.pyz --smoke --seed 11
    python3 tools/package_linux.py
    cd dist
    sha256sum -c SHA256SUMS

Quit the interactive source session before continuing. Follow the installation
commands above using this dist directory. Packaging requires a clean worktree;
place new captures outside the checkout. 26b206cea12e0e630036693a128a3de1b6fe61e9 already contains the required
source, tests and docs/linux.md. Rebuild reproducibility across different Python/
zlib toolchains is not asserted; compare the actual resulting checksum.

## Controls freshly exercised

SPACE pages initial help/cards; H or P begins. W/S moves forward/back; A/D strafes;
J/L and Left/Right turn; I/K and Up/Down look. SPACE photographs. After three
distinct photos, return to the depot and press E before 600 active seconds expire.
P pauses/resumes; H opens/closes help; R resets; N selects seed+1. Q/Escape quits;
Ctrl-C interrupts and restores the terminal. Movement keys renew a 140 ms hold;
shutter/UI keys require 250 ms release before a fresh edge. Do not paste controls.
A too-small window pauses gameplay and shows a resize notice.

Both source and installed game passed explicit signed movement/strafe/yaw/pitch
checks for every letter and arrow mapping, help/start/pause freezes, early E
rejection, R reset and N seed advancement. The full installed run additionally
paged all help/cards, reached a building collision using keyboard walking,
checked 80x24 and undersized resize behavior, photographed three landmarks,
submitted at the depot, verified the won-state freeze, restarted and selected
a new seed. All of that is scripted rather than subjective playtesting.

## Actual results

Linux host: Linux-7.0.0-31-generic-x86_64-with-glibc2.43. Python: 3.14.4 (main, Aug 20 2026, 10:41:58) [GCC 15.2.0].
The isolated venv contained no third-party distributions; zlib 1.3.1.
Recorded UTC: 2026-09-13T18:48:39.059416+00:00

Automated suite: 157 tests passed in 16.767 seconds. All fresh-clone
validator commands exited 0. Existing Windows mock tests in that suite do not
constitute native Windows execution.

Installed full run: 269.8602620700003 wall seconds; 4935 state frames
replayed exactly and 24 actual checkpoints regenerated exactly. Photo frames: [1137, 2457, 4027].
Win frame 4917; score 420; 368.2914333289991 active seconds remained.

Independent geometric readback verified player clearance for all 4935 full-run state
frames. The collision was with building block-05-05-0-0, not the city rail.
Minimum clearance: 0.3000010000420179 m for the 0.30 m player radius.
Submission distance from depot: 0.41822614933123775 m.

All 9 fresh real-game PTY sessions restored native termios exactly and emitted
normal-screen/cursor/SGR restoration. Both source and installed artifact: Q=0,
Escape=0 (256-color), Ctrl-C=130 and SIGTERM=143. These signal exit codes are
expected clean interruption behavior, not test failures.

Terminal restoration means exact native termios before/after equality plus actual
emitted ANSI cleanup sequences independently parsed to normal screen, visible
cursor and reset SGR. It does not mean a physical terminal emulator was visually
inspected. SIGKILL, lost terminal or machine failure cannot guarantee cleanup.
The actual captured RGB/glyph frame dumps and HTML renderings are not screenshots
of a physical desktop terminal.

## Evidence map and preservation

validation.json: exact revision, environment, install/build/runtime/replay results.
independent-readback.json: source binding, all PTY cleanup results and independently
calculated point-to-building rectangle clearance for every full-run state frame.
runtime-frames.html and runtime-frames.txt: newly captured full-game checkpoint
cells/HUD, convenient direct copies of fresh-linux/pty frames in the archive.
supplemental_probe.py: the executed fresh source/installed controls and exits probe.
readback_probe.py: the executed independent readback and geometric assertions.
runtime-and-install-evidence.tar.gz: full fresh logs, captures and command results.
ARCHIVE_CONTENTS.json: every archived regular file, original relative path, size
and SHA-256. Every member was read back and hash-verified after archive creation.
ALL_SHA256SUMS: hashes of all report-directory products except that checksum file.
SHA256SUMS: distribution-only checksum for the installation command above.

Within the evidence archive:

    fresh-linux/commands.json                exact executed commands/cwd/status/duration
    fresh-linux/logs/04.stdout.log           isolated runtime/package inventory
    fresh-linux/logs/05.stderr.log           complete automated-suite output
    fresh-linux/logs/06..17.*.log             actual build/install/runtime/replay outputs
    fresh-linux/pty/                         full gameplay PTY evidence
    supplemental-source/                    source controls and Q/Escape/Ctrl-C/SIGTERM
    supplemental-artifact/                  installed controls and the same exit cases
    *-transcript.log                         worker command stdout/stderr captures
    fresh-linux/distribution/                original artifacts/provenance/checksums

Each PTY case preserves raw terminal.ansi.gz, frame cells/depth in frames.jsonl.gz,
plain/HTML frames, checkpoints.ansi.gz, per-frame trace.jsonl, inputs.json,
metadata.json, timing.json and pty-result.json. Captures use entirely new paths;
none of the earlier docs/app-pty or docs/app-lifecycle paths were reused. Scratch
clones, installed copies and venv are disposable execution infrastructure, not
additional delivered versions. Original absolute execution paths in logs are
retained as provenance; archived evidence is independent of retaining that scratch.

## Repeat the fresh verification

From a checkout containing this evidence report, use new output paths. The original
validator clones 26b206cea12e0e630036693a128a3de1b6fe61e9 anew; the supplemental scripts import helpers from
that fresh checkout and run either its module or its installed artifact:

    EVIDENCE="$PWD/docs/linux-verification-step-109"
    WORK=$(mktemp -d)
    python3 tools/validate_linux.py --commit 26b206cea12e0e630036693a128a3de1b6fe61e9 --output "$WORK/fresh-linux"
    run_isolated() {
        env -i PATH="$WORK/fresh-linux/venv/bin:/usr/bin:/bin" \
            HOME="$WORK/fresh-linux/home" LANG=C.UTF-8 LC_ALL=C.UTF-8 \
            TERM=xterm-256color PYTHONDONTWRITEBYTECODE=1 "$@"
    }
    run_isolated python3 "$EVIDENCE/supplemental_probe.py" \
        --repo "$WORK/fresh-linux/clone" --output "$WORK/supplemental-source"
    run_isolated python3 "$EVIDENCE/supplemental_probe.py" \
        --repo "$WORK/fresh-linux/clone" --output "$WORK/supplemental-artifact" \
        --launcher "$WORK/fresh-linux/home/.local/opt/lantern-survey-linux/lantern-survey" \
        --cwd "$WORK/fresh-linux/unrelated working directory"
    run_isolated python3 "$EVIDENCE/readback_probe.py" \
        --workspace "$WORK" --output "$WORK/independent-readback.json"

TERM is explicitly set for the scripted Linux PTYs that implement that interface;
do not use this setting to misrepresent an unsupported physical terminal.
Generated summaries must say passed=true; any assertion/command failure is a failed
reproduction, not success. This procedure takes several minutes and sends only
scripted input; a separate human session is still needed for node 11.
