# Lantern Survey: Linux distribution

Photograph three distinct city landmarks, then return to the starting depot and
press E before 600 active seconds expire. This is the real colored 3D ASCII city,
not a map or a headless demo. Beauty and enjoyment need independent assessment.

## Prerequisites

Linux, Python 3.11 or newer, and an interactive xterm-compatible UTF-8 terminal
with ANSI color (e.g. GNOME Terminal, xterm, kitty). No pip packages, curses,
compiler, administrator install, or network access needed to play the tarball.
Python is a required system runtime: this is NOT a standalone binary.
Debian/Ubuntu: `sudo apt-get install python3`. Building also needs Git, tar and
sha256sum; automated isolated validation additionally needs python3-venv.

Use at least 80 columns by 24 rows; 100x36 recommended. Smaller windows pause
play and display a resize notice. Truecolor is default; use `--color 256` on
256-color terminals. Keep TERM correctly configured by your terminal (do not
set a fake value for an unsupported terminal). Redirected stdin/stdout, TERM=dumb,
and the Linux virtual console are not supported for interactive play. No mouse.

## Install and launch a delivered tarball

Place the tar.gz and its matching SHA256SUMS together. From that directory:

    sha256sum -c SHA256SUMS
    mkdir -p "$HOME/.local/opt"
    tar -xzf lantern-survey-linux-*.tar.gz -C "$HOME/.local/opt"
    "$HOME/.local/opt/lantern-survey-linux/lantern-survey"

Keep only ONE release tarball in that directory when using the wildcard.
Extract into a new/empty destination for each release (do not overlay old code).
The launcher works from any current directory, including paths with spaces.
It runs the adjacent packaged code, not a checkout or the caller directory.
Set LANTERN_PYTHON to an executable name or full path if Python is not called
python3. PYTHONPATH and user site packages are ignored. No permanent PATH edits.
Delete the extracted lantern-survey-linux directory to uninstall; game progress
is session-only. Only an explicit --capture-dir writes game evidence to disk.

    "$HOME/.local/opt/lantern-survey-linux/lantern-survey" --smoke --seed 11
    "$HOME/.local/opt/lantern-survey-linux/lantern-survey" --help
    "$HOME/.local/opt/lantern-survey-linux/lantern-survey" --color 256

--smoke checks real scene assembly/rendering without a TTY; it is not gameplay
validation. Quit returns to the shell and restores terminal modes, cursor and
normal screen. Q/Escape is preferred; Ctrl-C also cleans up. SIGKILL, terminal
loss and machine failure cannot guarantee restoration (use reset if necessary).

## Controls

Initial help pauses the clock: SPACE pages instructions/landmark cards; H or P
starts. W/S walk; A/D strafe. J/L or Left/Right turn. I/K or Up/Down look.
SPACE photographs; E submits near the depot after three distinct photos.
P pauses/resumes, H opens/closes help. R restarts; N selects seed+1.
Q/Escape quits; Ctrl-C is an emergency exit. Tapping/repeating movement renews a
140 ms hold; there are no reliable terminal key-up events. Shutter/UI keys need
250 ms without repetition for a new press. Do not paste controls into gameplay.

## Rebuild from the identified commit

Use the full source_commit in the delivered BUILD.json or provenance.json as
COMMIT below. Public HTTPS clone needs no SSH key. From a fresh directory:

    git clone https://github.com/rickseeger/ai-game-04.git
    cd ai-game-04
    git checkout --detach COMMIT
    python3 -m unittest discover -s tests -v
    python3 tools/build.py
    python3 dist/lantern-survey.pyz --smoke --seed 11
    python3 tools/package_linux.py
    cd dist
    sha256sum -c SHA256SUMS

Then follow the install/launch commands above. Build requires a clean tracked
and untracked Git worktree (ignored dist/__pycache__ are harmless). Package bytes
are taken from Git blobs at HEAD; fixed archive metadata makes repeated builds
byte-identical on the same Python/zlib toolchain. Compare SHA256SUMS when using a
different toolchain. BUILD.json binds each payload file to SHA-256 and a full Git
commit. The tarball, SHA256SUMS and provenance.json are in dist/. The legacy .pyz
is also stdlib-only but the tested Linux delivery entrypoint is the tar launcher.

## Reproduce clean Linux validation

After pushing the candidate commit, with python3-venv installed, run from checkout:

    python3 tools/validate_linux.py --commit COMMIT --output /absolute/new/evidence-dir

The output directory MUST NOT exist. The script freshly clones the public repo,
checks out that exact SHA, creates a --without-pip isolated venv and fresh HOME,
clears inherited Python/environment dependencies, runs all tests, builds twice
and compares bytes, verifies checksums, and extracts to the fresh HOME as above.
It launches the INSTALLED launcher from an unrelated directory in a controlling
PTY: real-time movement, turns/look, facade collision, pause/resize, three real
photos, depot win, restart/new seed, and Q. It records raw ANSI with color, exact
native before/after termios, action telemetry, rendered RGB cells and HTML frames.
A separate replay regenerates checkpoints and checks hashes. A PTY proves emitted
ANSI and kernel mode restoration; it is not a screenshot or physical-emulator
assessment. See validation.json, commands.json and pty/frames.html in the output.
This takes several minutes. Never reuse old recordings as evidence of a new run.

## Windows is deferred

This pass only builds and validates Linux. CI schedules Ubuntu with Python 3.11
and 3.14; Windows jobs are removed from the matrix to avoid unsupported noise.
No Windows archive or Windows runtime pass is claimed. The older broad node
contract is not fully discharged by this Linux-only scope. In the later Windows
pass, build an identified candidate and ask Andrew or an interactive native
Windows 10/11 runner to record launch, every control, city rendering, resize,
Q/Escape/Ctrl-C and shell/mode restoration against its SHA-256. Artifact existence,
Linux execution, mocks, or cross-compilation alone do not close that gate.
