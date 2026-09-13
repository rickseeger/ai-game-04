# Lantern Survey (G11)

Foundation milestone, NOT a playable city yet. Default launch reports this and
exits normally. No renderer, movement, terminal adapter or game rules are faked.
Shared Python interfaces are in `citywalk/contracts.py`; implementation handoff
and the chosen game are in [docs/design.md](docs/design.md).

## Requirements and exact commands

Python 3.11+ (standard library only); Git for cloning. No pip, network packages,
curses, native extensions or install step. From a fresh clone:

    git clone git@github.com:rickseeger/ai-game-04.git
    cd ai-game-04
    python3 -m citywalk
    python3 -m citywalk --smoke --seed 11
    python3 -m unittest discover -s tests -v
    python3 tools/build.py
    python3 dist/lantern-survey.pyz
    python3 dist/lantern-survey.pyz --smoke --seed 11

Public HTTPS clone alternative: https://github.com/rickseeger/ai-game-04.git
Windows PowerShell: use the same commands with `py -3` instead of `python3`.
The zipapp can run from any directory; it contains all application source.
`python3 -m citywalk --help` documents currently implemented options.
Tests and source launch run from repository root. Build accepts any working directory.
Building twice from identical source produces identical bytes and prints SHA-256.

## Distribution plan

Both Linux and Windows support the same `.pyz`, with Python 3.11+ explicitly
required. Node 10 packages it into a Linux tar.gz and Windows zip with platform
launchers and instructions, identified commit and checksums. This is a viable
Python-runtime distribution, NOT a standalone native executable. If standalone
is later required, build PyInstaller executables separately on native runners;
never present Linux cross-builds as Windows runtime evidence.

Final terminal target: Linux xterm-compatible UTF-8 terminal and Windows 10/11
Windows Terminal with VT color support. ASCII glyphs keep cell widths portable.
100x36 recommended, 80x24 minimum; proposed controls and resize behavior are in
the design. CI runs foundation tests/build on Linux/Windows with Python 3.11/3.14.
CI configuration is not proof those runs have passed, nor Windows game playtest proof.

This node validates execution and architecture, not beauty or fun. See
`docs/foundation-validation.md` for actual local evidence and limitations.
