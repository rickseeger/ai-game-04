# Linux delivery revalidation — step 103

Linux execution passed. Durable contract acceptance is blocked on controller
reconciliation, not on another Linux rebuild. No harness state was changed.

Artifact source commit: 7c877935eacfecdb39100528713b74fbfd55527a.
This report is a subsequent evidence-only commit, NOT the artifact source.
Existing committed packaging, launcher, instructions, source, tests and Ubuntu-only
CI were inspected and reused without unnecessary implementation changes.
Prior step-102 recordings are untouched.

## Reproduce and play

Follow docs/linux.md using the source commit above. Exact executed validation:

    python3 tools/validate_linux.py --commit 7c877935eacfecdb39100528713b74fbfd55527a --output /opt/g-harness/workspace/G11/node_10_step_103/linux-validation

For another run choose a NEW absolute output directory. Delivered files are at:

    /opt/g-harness/workspace/G11/node_10_step_103/deliverables/

From that directory, in an interactive Linux color terminal with Python 3.11+:

    sha256sum -c SHA256SUMS
    mkdir -p "$HOME/.local/opt"
    tar -xzf lantern-survey-linux-7c877935eacfecdb39100528713b74fbfd55527a.tar.gz -C "$HOME/.local/opt"
    "$HOME/.local/opt/lantern-survey-linux/lantern-survey"

Use a fresh/empty install destination rather than overlaying an old release.
H starts; W/S/A/D walk; J/L turn; I/K look; SPACE photographs; E submits at depot;
P pauses; R restarts; N changes seed; Q/Escape quits. Terminal: 80x24 minimum,
100x36 recommended. No pip dependencies; this requires Python, not a native binary.

Tarball SHA-256:

    dde8c725ecac97b59544cb0552b35af06a90acf0402a91abc5d621dd32458d9b

## Actual results

Fresh public HTTPS clone, empty --without-pip venv, fresh HOME, allowlisted
environment, Python 3.14.4, Linux x86_64/glibc 2.43, zlib 1.3.1; no installed
Python packages. This is dependency isolation on the existing host, not a container
or a newly provisioned OS. All 157 tests passed. Zipapp build/smoke passed; two
Linux tarball builds were byte-identical; checksum and installed manifest passed.

The extracted launcher ran from an unrelated working directory in a controlling
Linux PTY. Real-time keyboard input exercised help, movement, turning/look,
facade collision, pause, minimum-size rendering, undersize pause, three photos,
depot submission for a 420-point win, restart, new seed and Q. Exit code 0;
exact native termios restored; cursor visible, alternate screen exited, SGR reset.
Run duration: 270.403 seconds. Evidence replay matched 4,836 frame records and
regenerated all 24 RGB checkpoints. Raw emitted truecolor ANSI is retained, not
substituted with a schematic. Open deliverables/linux-frames.html for captures.

linux-validation-evidence.tar.gz contains linux-validation/commands.json,
validation.json, host-details.json, all command stdout/stderr logs, distribution,
PTY input/telemetry, raw ANSI, RGB captures and a SHA-256 file inventory. Archive
members were read back and checked before retiring the scratch clone/venv/install.
Archived execution paths are historical. ALL_SHA256SUMS checks delivered files.
Detailed results, provenance and artifact hashes: linux-revalidation-step-103.json.

Source-commit GitHub Actions run 34774383582 succeeded for Ubuntu Python 3.11
and 3.14. The workflow has only ubuntu-latest; no Windows job was scheduled.
https://github.com/rickseeger/ai-game-04/actions/runs/34774383582

## Exact scope conflict requiring controller action

The stored node objective and Rick authorize Linux only and explicitly defer
Windows. However completion_contract still says “build both platform artifacts
from an identified commit” and “Exercise the Windows artifact on Windows through
an available runner or real tester, recording launch, controls, rendering, and
quit results.” The full stored text is preserved in the adjacent JSON and in
workspace stored-node-contract.json. Prior controller failure log 120 explicitly
identified this same mismatch; it was not a Linux execution failure.

Request to controller: reconcile node 10 durable completion_contract with the
already authorized Linux-first objective and preserve the both-platform packaging
and native Windows runtime clauses for a later Windows pass. Do not dispatch more
Linux rebuilds or unauthorized Windows work to resolve this contract-only failure.
The worker cannot edit or weaken the durable contract and does not claim it met.

No Windows build or native Windows execution was performed or claimed. Later
Windows work needs an identified artifact and a native Windows tester/interactive
runner recording launch, controls, rendering and quit against its checksum.
Automated PTY checks establish neither physical-emulator display quality nor
beauty/enjoyment; independent installed-game assessment remains node 11.
