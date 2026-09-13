# Terminal component — node 7 implementation and evidence

## Scope and completion contract

Assigned objective: implement and verify Linux and Windows terminal input,
display lifecycle, and reliable terminal restoration. The full supplied contract:

> Commit platform-appropriate terminal adapters with tested mappings for every
> advertised control, nonblocking input, escape-sequence handling, resize
> behavior, and cleanup on normal quit, interruption, and exceptions. Exercise
> the Linux adapter through a real pseudo-terminal, inject controls, and verify
> terminal attributes and cursor/display state are restored. Provide
> Windows-specific tests and implementation without representing mocks as
> Windows runtime validation; actual Windows launch and control evidence is
> required at the delivery gate. Record transcripts and executed tests.

This change implements only that component. It preserves `contracts.Terminal`,
`Actions`, `Frame`, and every movement/camera/renderer interface. No gameplay,
city construction, rule implementation, or application loop is added. The
informational app wording is updated; it still changes no terminal state and
`--smoke` remains pipe-safe. This report is worker evidence, not durable node or
mission completion, beauty, fun, or release approval.

## API and application integration handoff

`citywalk.terminal.open_terminal()` returns a context manager implementing:

- `size() -> (columns, total_rows)`: current console/window dimensions, not a
  cached environment fallback. Windows uses the visible window, not buffer size.
- `poll(monotonic_now) -> Actions`: no waiting and bounded input consumption.
  Linux select with zero timeout and at most 4096 bytes; Windows at most 256
  `kbhit/getwch` characters. Decoder timing must be finite and nondecreasing.
- `present(frame, hud_tuple)`: owns all ANSI encoding, RGB validation and output.
  Frame glyphs must be printable single-cell ASCII; untrusted HUD controls and
  non-ASCII are replaced with `?`. It uses absolute cursor addressing without
  newlines, never scrolls by advancing beyond bottom-right, and avoids erasing
  the final full-width cell. SGR colors are run-compressed within each row.

Optional backward-compatible `open_terminal(color="256")` quantizes to the
nearest xterm color cube/gray; default is `truecolor`. These are component
options, NOT an implemented application `--color` flag. The test probe exposes
that flag itself. The Linux `TERM` check accepts known xterm-compatible families
(xterm/screen/tmux/rxvt/alacritty/foot/wezterm/kitty/st); dumb, missing, unknown,
legacy Linux virtual console and generic non-VT terminals receive an actionable
error before display entry. Set TERM correctly; do not spoof a capable terminal.
Windows must have real console handles and successfully enable VT output.
Redirected input OR output is rejected with instructions to use a terminal or
headless `--smoke`. No curses dependency or packages are required.

Optional `wait(timeout)` is a concrete helper, not a Protocol change. Linux
select waits for input or deadline. Windows sleeps for the bounded timeout;
console readiness includes resize/key-up records that msvcrt does not consume,
so waiting on that handle alone could spin. The application MUST schedule frame
ticks/sleep; repeatedly calling a nonblocking poll without pacing is a busy loop
in its caller. The probe sleeps on a 20 ms cadence and is only a component test.

Application node 9 must keep the context around the entire interactive session,
catch `TerminalUnavailable`/`TerminalInterrupted` OUTSIDE the context, display
errors after cleanup, and map interruptions to an appropriate exit code. Poll
before simulation; handle quit first. Use the current size to allocate a fresh
viewport `(cols, total_rows-4)` and corresponding renderer frame. Frame dimensions
racing a resize produce a rebuild notice, not clipping with an incorrect camera
aspect. Shrink/grow clears stale screen regions; normal frames also clear unused
row tails/HUD rows. Below 80x24, only a plain resize/help/quit notice is shown and
poll returns help/quit only, clearing held movement. The application MUST freeze
both timer and simulation while undersized, and resume from a fresh clock tick
without catch-up elapsed time. The terminal does not own game time or state.
100x36 is recommended. Resume/render/UI overlay logic is still application work.

## Every advertised control and timing

| Input (letters case-insensitive) | Actions field/value |
| --- | --- |
| W / S | forward +1 / -1 |
| A / D | strafe -1 / +1 |
| J / L or Left / Right | turn -1 / +1 |
| I / K or Up / Down | look +1 / -1 |
| Space | shutter |
| E | interact (submission belongs to gameplay) |
| P | pause |
| H or ? | help |
| R | restart |
| N | new_seed |
| Q or lone Escape | quit |
| Ctrl-C | TerminalInterrupted, unwind context |

Directional events persist 140 ms, renewed by key repetition. The latest
opposite direction wins on an axis; different axes can coexist. This is tap/
repeat input, not true key-up or precision held/simultaneous-key tracking.
Each physical shutter/UI key is edge-suppressed until 250 ms without that key;
repeats renew suppression. H and ? are separate physical keys for this policy.
Returned edges clear after each poll; no repeated photo/UI events from a held
key's auto-repeat cadence. These rules implement the design, but OS initial
repeat delay may cause a gap in continuous walking. Real playtests must assess
responsiveness; no playability conclusion is drawn here.

Linux decoding buffers split CSI and SS3 arrows (also numeric modifiers).
A lone Escape resolves after 40 ms. An incomplete CSI/SS3 timeout never quits:
it discards through the next final byte rather than interpreting the arrow's
final A/D as strafe. Very delayed/corrupt sequences can therefore lose a key;
no parser can infer an absent final byte without a tradeoff. Unsupported Alt
chords, function-key sequences, OSC/DCS strings and bracketed paste contents
are discarded, not converted into gameplay commands. Bounded storage prevents
input floods from growing a sequence buffer. Strings/pastes wait for their
terminator; Ctrl-C still interrupts even inside malformed input. Non-ASCII
bytes/characters are ignored. Ordinary unbracketed pasted ASCII is ordinary
input, so do not paste gameplay controls into an active session.

Windows msvcrt `\x00`/`\xe0` extended-key prefixes persist across polls; H/P/M/K
scan codes mean Up/Down/Right/Left, not letter actions. Unknown extended codes
are swallowed. VT INPUT is disabled deliberately; output VT is enabled. Ctrl-C
is read as U+0003 with processed input disabled; SIGINT/Ctrl-Break paths are also
handled when delivered by the host Python runtime.

## Lifecycle guarantees and honest boundaries

Context entry saves modes before mutation and installs/restores previous signal
handlers on the main thread. Reentrant use is rejected; sequential reuse resets
decoder state. Setup/partial display-write failure rolls back. Linux saves exact
termios (including control characters), disables canonical/echo/flow-control/
CR translation, keeps ISIG and uses VMIN=VTIME=0; it does not change descriptor
flags. Windows uses typed pointer-width-safe ctypes Win32 declarations, saves
input/output modes, cursor size/visibility and console text attributes, disables
Quick Edit/line/echo/processed/VT input, and enables processed/VT output. Failed
VT setup restores already changed modes and reports an actionable error.

Exit resets SGR, shows/restores cursor visibility and leaves alternate screen,
then restores native modes. Linux xterm private-mode save/restore preserves an
initially hidden cursor on supporting emulators; explicit show is the fallback.
Windows additionally restores cursor info and console attributes via Win32.
Linux cannot generally recover an arbitrary preexisting SGR style; it resets
to default colors so the shell is usable. Main-screen content/cursor position
use conventional alternate-screen save/restore (1049), not a screen scrape.
Already being inside someone else's alternate-screen context is not supported.

Normal Q/Escape, handled Ctrl-C, SIGTERM and exceptions unwind the same path.
On POSIX SIGQUIT and SIGTSTP also exit cleanly instead of dumping core or
suspending a raw screen; resume/job-control is deliberately not implemented.
A second handled signal is ignored only during cleanup. Even if output fails,
mode restoration is attempted; cleanup errors are raised (or attached as notes
to the original exception) rather than silently claiming success. A disconnected
terminal can make display restoration impossible. There is NO guarantee after
SIGKILL, os._exit, native crash, machine loss, Windows TerminateProcess/taskkill
/F, or console-window destruction. Windows SIGTERM as a Python handler does not
turn Windows forced process termination into a catchable event.

## Reproducible executed Linux evidence

From repository root:

    python3 -m unittest discover -s tests -p test_terminal.py -v
    python3 -m unittest discover -s tests -v
    python3 tools/validate_terminal_pty.py
    python3 tools/probe_terminal.py --help
    python3 tools/build.py
    python3 dist/lantern-survey.pyz --smoke --seed 11
    python3 -m citywalk --smoke --seed 93

`python3 tools/validate_terminal.py` executes all of these and records exact argv,
stdout, stderr, exit codes, durations, host/Python and executed-source SHA-256 in
`docs/terminal-run.json`. Local execution: 28 terminal tests, 119 full regression
tests, all passing. Build and both actual smoke launches exit 0. The recording
identifies the pre-commit parent plus working-file hashes; it does not pretend
the parent commit alone contains this implementation.

`docs/terminal-pty/summary.json` summarizes seven real controlling-Linux-PTY
cases: normal Q, delayed Escape, injected exception, kernel-generated Ctrl-C
from byte 03, SIGTERM, SIGQUIT and SIGTSTP. Each checks exact termios equality
before/after, changed active attributes, previous signal handlers restored,
bounded nonblocking idle polls, and a real timed wait with negligible process
CPU (not a busy spin). The normal case injects every ordinary advertised
non-quit control and four split arrows, an unknown CSI, shrink/grow and quit.
Uppercase and repetition boundaries are additionally deterministic unit tests.

Each `<case>.json` contains the actual injections, responses, timings and exact
termios arrays; `<case>.ansi` contains captured actual terminal output. Git
marks `.ansi` as non-text so CR/LF and escape bytes survive checkout unchanged. A small
independent VT control-state checker verifies enter/hide/reset/exit ordering and
final normal screen/reset SGR/restored visibility for initially visible/hidden
models. A PTY is NOT an emulator: these are real emitted bytes and actual kernel
mode restoration, with modeled VT interpretation, not physical emulator queries
or screenshots. This does not prove a particular emulator rendered correctly.

Two additional PTY runs exercise the shipped interactive probe itself (normal
quit and injected exception), including full-width scene/HUD presentation and
its own independent before/after mode snapshots. These are `probe_normal.*`
and `probe_exception.*`. The probe's test pattern is explicitly NOT city art.

## Native Windows validation gap and delivery-gate procedure

This worker host is Linux; no native Windows console is available. A wine64
binary was discoverable, but Wine is not native Windows execution and was not
used as substitute evidence. `WindowsMockTests` use a deliberately named fake
console to cover mode bit decisions, partial setup rollback, all cleanup
attempts, cursor/attribute restore, nonblocking read bounds and extended input.
Portable decoder tests cover all advertised Windows mappings and split prefixes.
These do NOT validate the real ctypes ABI, msvcrt event behavior, Windows VT
emulation, actual process interruption, or a Windows game launch. Existing CI
configuration is not evidence of a run, and a noninteractive CI console may not
be able to launch the interactive adapter.

On an actual Windows 10/11 machine in Windows Terminal, with Python 3.11+ and a
clean checkout of the exact candidate SHA, run (PowerShell):

    py -3 -m unittest discover -s tests -v
    py -3 tools/probe_terminal.py --output ../windows-terminal-normal.json
    py -3 tools/probe_terminal.py --output ../windows-terminal-ctrl-c.json
    py -3 tools/probe_terminal.py --raise-after 3 --output ../windows-terminal-exception.json
    py -3 tools/probe_terminal.py --color 256 --output ../windows-terminal-256.json

In the normal run physically exercise EVERY table entry, uppercase variants,
tapping/repetition and both arrow/letter alternatives, resize below 80x24 and
back, then Q. Repeat with Escape quit; in the second run Ctrl-C. Inspect actual
raw Windows characters, action events, dimension changes and native before/after
mode/cursor/attribute equality in the JSON reports. Record the source SHA,
Windows/Python/terminal versions, a terminal recording/screenshots and observations
that the original screen, colors, cursor and normal shell typing work afterward.
A test exit code alone is not proof every control was exercised. No native
Windows report is prepopulated or marked passing here.

At node 9/10 delivery, additionally launch the actual Windows game artifact,
exercise its controls and route/restart/quit/resize/cleanup on Windows, and
identify the artifact checksum and commit. Andrew or a native interactive runner
can provide that evidence. Neither this component probe, mocks nor a Linux zipapp
smoke establishes native Windows success or substitutes for the required final
Windows artifact/play validation. Human-scale beauty and gameplay enjoyment also
remain separate independent assessment gates.
