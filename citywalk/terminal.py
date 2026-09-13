"""Context-managed terminal adapters; no game loop or concrete game dependencies.

poll() never waits. The caller schedules frames with a monotonic clock and a
sleep, or uses wait(timeout) between ticks. See docs/terminal.md for boundaries.
"""
import math
import os
import select
import signal
import sys
import threading
import time

from .contracts import Actions, Frame

ESC_DELAY = 0.040
AXIS_HOLD = 0.140
EDGE_RELEASE = 0.250
MIN_SIZE = (80, 24)
ENTER_DISPLAY = "\x1b[?25s\x1b[?1049h\x1b[0m\x1b[?25l\x1b[2J\x1b[H"
# Show explicitly for terminals without DECRPM/private-mode save support, then
# restore saved visibility on those with support. Reset SGR, leave alt screen.
LEAVE_DISPLAY = "\x1b[0m\x1b[?25h\x1b[?1049l\x1b[?25r"

AXES = {
    "w": ("forward", 1), "s": ("forward", -1),
    "a": ("strafe", -1), "d": ("strafe", 1),
    "j": ("turn", -1), "l": ("turn", 1),
    "i": ("look", 1), "k": ("look", -1),
    "left": ("turn", -1), "right": ("turn", 1),
    "up": ("look", 1), "down": ("look", -1),
}
EDGES = {" ": "shutter", "e": "interact", "p": "pause", "h": "help",
         "?": "help", "r": "restart", "n": "new_seed", "q": "quit",
         "escape": "quit"}
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}
WIN_ARROWS = {"H": "up", "P": "down", "M": "right", "K": "left"}


class TerminalUnavailable(RuntimeError):
    """Actionable unsupported terminal / disconnected terminal error."""


class TerminalInterrupted(KeyboardInterrupt):
    def __init__(self, signum=signal.SIGINT):
        self.signum = signum
        super().__init__(f"terminal interrupted by signal {signum}")


class InputDecoder:
    """Incremental bounded decoder. All times supplied by the monotonic caller."""
    def __init__(self):
        self.axes = {}
        self.last_edge = {}
        self.edges = set()
        self.state = "normal"
        self.sequence = ""
        self.started = 0.0
        self.last_now = -math.inf
        self.win_prefix = False

    def _clock(self, now):
        if not math.isfinite(now) or now < self.last_now:
            raise ValueError("poll time must be finite and monotonic")
        self.last_now = now
        if self.state == "esc" and now - self.started >= ESC_DELAY:
            self.state = "normal"
            self.key("escape", now)
        elif self.state in ("csi", "ss3") and now - self.started >= ESC_DELAY:
            # Never convert a truncated arrow to quit or its final byte to a
            # gameplay letter. Discard through the next sequence final byte.
            self.state = "discard"

    def key(self, key, now):
        key = key.lower()
        if key == "\x03":
            raise TerminalInterrupted()
        if key in AXES:
            axis, value = AXES[key]
            self.axes[axis] = (value, now)
        elif key in EDGES:
            if now - self.last_edge.get(key, -math.inf) >= EDGE_RELEASE:
                self.edges.add(EDGES[key])
            self.last_edge[key] = now

    def feed(self, data, now):
        self._clock(now)
        if isinstance(data, bytes):
            data = data.decode("latin1")
        for char in data:
            if char == "\x03":
                raise TerminalInterrupted()
            state = self.state
            if state == "normal":
                if char == "\x1b":
                    self.state, self.started = "esc", now
                elif ord(char) < 128:
                    self.key(char, now)
            elif state == "esc":
                if char in "[O":
                    self.state = "csi" if char == "[" else "ss3"
                    self.sequence = ""
                elif char in "]PX^_":
                    self.state = "string"
                elif char == "\x1b":
                    self.started = now
                else:
                    # Unsupported Alt chord, not a quit plus gameplay key.
                    self.state = "normal"
            elif state in ("csi", "ss3", "discard"):
                if "@" <= char <= "~":
                    if state != "discard":
                        if self.sequence == "200" and char == "~":
                            self.state, self.sequence = "paste", ""
                            continue
                        if char in ARROWS and (not self.sequence or
                                all(c in "0123456789;" for c in self.sequence)):
                            self.key(ARROWS[char], now)
                    self.state, self.sequence = "normal", ""
                else:
                    self.sequence = (self.sequence + char)[-32:]
                    if len(self.sequence) == 32:
                        self.state = "discard"
            elif state == "paste":
                self.sequence = (self.sequence + char)[-6:]
                if self.sequence == "\x1b[201~":
                    self.state, self.sequence = "normal", ""
            elif state == "string":
                if char == "\x07":
                    self.state = "normal"
                elif char == "\x1b":
                    self.state = "string_esc"
            elif state == "string_esc":
                self.state = "normal" if char == "\\" else "string"

    def feed_windows(self, chars, now):
        self._clock(now)
        for char in chars:
            if char == "\x03":
                raise TerminalInterrupted()
            if self.win_prefix:
                self.win_prefix = False
                if char in WIN_ARROWS:
                    self.key(WIN_ARROWS[char], now)
            elif char in ("\x00", "\xe0"):
                self.win_prefix = True
            else:
                self.feed(char, now)

    def actions(self, now):
        self._clock(now)
        values = {axis: value for axis, (value, at) in self.axes.items()
                  if now - at < AXIS_HOLD}
        values.update({edge: True for edge in self.edges})
        self.edges.clear()
        return Actions(**values)


class PosixBackend:
    def __init__(self, input_stream, output_stream):
        self.input = input_stream
        self.output = output_stream
        self.saved = None

    def enter(self):
        if not self.input.isatty() or not self.output.isatty():
            raise TerminalUnavailable("Interactive input/output must be TTYs; run in a terminal, or use --smoke for pipes.")
        term = os.environ.get("TERM", "")
        if term in ("", "dumb", "unknown") or not term.startswith(("xterm", "screen", "tmux", "rxvt", "alacritty", "foot", "wezterm", "kitty", "st-")):
            raise TerminalUnavailable("Use an xterm-compatible ANSI terminal with TERM set correctly; --smoke is pipe-safe.")
        import termios
        self.fd = self.input.fileno()
        self.saved = termios.tcgetattr(self.fd)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] &= ~(termios.IXON | termios.ICRNL | termios.INLCR)
        attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN)
        # ISIG retained: Ctrl-C is a real interrupt on a controlling terminal.
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def close(self):
        if self.saved is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)
            self.saved = None

    def read(self):
        if not select.select([self.fd], [], [], 0)[0]:
            return b""
        data = os.read(self.fd, 4096)
        if not data:
            raise TerminalUnavailable("Terminal input disconnected; relaunch in a live terminal.")
        return data

    def size(self):
        size = os.get_terminal_size(self.output.fileno())
        return size.columns, size.lines

    def wait(self, timeout):
        select.select([self.fd], [], [], timeout)


class WindowsConsole:
    """Thin real Win32 calls. Import/construct only on Windows; injectable in tests."""
    def __init__(self, input_stream, output_stream):
        import ctypes
        from ctypes import wintypes as w
        import msvcrt
        self.ctypes, self.msvcrt = ctypes, msvcrt
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        class Coord(ctypes.Structure):
            _fields_ = [("X", w.SHORT), ("Y", w.SHORT)]

        class Rect(ctypes.Structure):
            _fields_ = [("Left", w.SHORT), ("Top", w.SHORT), ("Right", w.SHORT), ("Bottom", w.SHORT)]

        class Info(ctypes.Structure):
            _fields_ = [("size", Coord), ("position", Coord), ("attributes", w.WORD),
                        ("window", Rect), ("maximum", Coord)]

        class Cursor(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("visible", w.BOOL)]

        self.Info, self.Cursor, self.DWORD = Info, Cursor, w.DWORD
        signatures = {
            "GetConsoleMode": [w.HANDLE, ctypes.POINTER(w.DWORD)],
            "SetConsoleMode": [w.HANDLE, w.DWORD],
            "GetConsoleScreenBufferInfo": [w.HANDLE, ctypes.POINTER(Info)],
            "GetConsoleCursorInfo": [w.HANDLE, ctypes.POINTER(Cursor)],
            "SetConsoleCursorInfo": [w.HANDLE, ctypes.POINTER(Cursor)],
            "SetConsoleTextAttribute": [w.HANDLE, w.WORD],
        }
        for name, args in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, w.BOOL
        self.hin = msvcrt.get_osfhandle(input_stream.fileno())
        self.hout = msvcrt.get_osfhandle(output_stream.fileno())

    def call(self, name, *args):
        if not getattr(self.kernel, name)(*args):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def get_mode(self, output):
        mode = self.DWORD()
        self.call("GetConsoleMode", self.hout if output else self.hin, self.ctypes.byref(mode))
        return mode.value

    def set_mode(self, output, mode):
        self.call("SetConsoleMode", self.hout if output else self.hin, mode)

    def info(self):
        info = self.Info()
        self.call("GetConsoleScreenBufferInfo", self.hout, self.ctypes.byref(info))
        return info

    def get_cursor(self):
        cursor = self.Cursor()
        self.call("GetConsoleCursorInfo", self.hout, self.ctypes.byref(cursor))
        return cursor

    def set_cursor(self, cursor):
        self.call("SetConsoleCursorInfo", self.hout, self.ctypes.byref(cursor))

    def set_attributes(self, attributes):
        self.call("SetConsoleTextAttribute", self.hout, attributes)

    def size(self):
        window = self.info().window
        return window.Right - window.Left + 1, window.Bottom - window.Top + 1

    def read(self):
        chars = []
        for _ in range(256):
            if not self.msvcrt.kbhit():
                break
            chars.append(self.msvcrt.getwch())
        return chars


class WindowsBackend:
    def __init__(self, input_stream, output_stream, console=None):
        self.input, self.output = input_stream, output_stream
        self.console = console
        self.saved_in = self.saved_out = self.cursor = self.attributes = None

    def enter(self):
        if not self.input.isatty() or not self.output.isatty():
            raise TerminalUnavailable("Use Windows Terminal with console input/output, not redirected pipes; --smoke works headlessly.")
        try:
            if self.console is None:
                self.console = WindowsConsole(self.input, self.output)
            c = self.console
            self.saved_in, self.saved_out = c.get_mode(False), c.get_mode(True)
            self.cursor, self.attributes = c.get_cursor(), c.info().attributes
            # Disable line/echo/processed input, Quick Edit and VT input.
            # Keep extended flags, so Quick Edit actually turns off. Ctrl-C is
            # read as U+0003; arrow input remains msvcrt extended-key pairs.
            c.set_mode(False, (self.saved_in | 0x80) & ~(0x01 | 0x02 | 0x04 | 0x40 | 0x200))
            c.set_mode(True, self.saved_out | 0x01 | 0x04)  # processed + VT output
        except OSError as exc:
            raise TerminalUnavailable("VT console mode unavailable. Use Windows 10/11 Windows Terminal and Python 3.11+; --smoke is pipe-safe.") from exc

    def close(self):
        # Attempt EVERY restoration even when one API call fails.
        errors = []
        for value, method, args in (
            (self.cursor, "set_cursor", (self.cursor,)),
            (self.attributes, "set_attributes", (self.attributes,)),
            (self.saved_in, "set_mode", (False, self.saved_in)),
            (self.saved_out, "set_mode", (True, self.saved_out)),
        ):
            if value is not None:
                try:
                    getattr(self.console, method)(*args)
                except OSError as exc:
                    errors.append(exc)
        self.saved_in = self.saved_out = self.cursor = self.attributes = None
        if errors:
            raise errors[0]

    def read(self):
        return self.console.read()

    def size(self):
        return self.console.size()

    def wait(self, timeout):
        # Console event readiness includes resize/key-up records that kbhit
        # does not consume. A bounded sleep avoids spinning on those records.
        time.sleep(timeout)


def _safe_text(text):
    return "".join(c if " " <= c <= "~" else "?" for c in text)


def _color(rgb, background, mode):
    if len(rgb) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in rgb):
        raise ValueError("cell colors must be RGB integers in 0..255")
    prefix = 48 if background else 38
    if mode == "truecolor":
        return f"\x1b[{prefix};2;{rgb[0]};{rgb[1]};{rgb[2]}m"
    # Nearest xterm color-cube or gray (do not rely on mutable ANSI 0..15).
    levels = (0, 95, 135, 175, 215, 255)
    indices = [min(range(6), key=lambda i: abs(levels[i] - value)) for value in rgb]
    cube = tuple(levels[i] for i in indices)
    gray_index = min(range(24), key=lambda i: sum((8 + 10*i - v)**2 for v in rgb))
    gray = 8 + 10*gray_index
    if sum((gray-v)**2 for v in rgb) < sum((a-b)**2 for a, b in zip(cube, rgb)):
        index = 232 + gray_index
    else:
        index = 16 + 36*indices[0] + 6*indices[1] + indices[2]
    return f"\x1b[{prefix};5;{index}m"


class TerminalAdapter:
    def __init__(self, backend, *, windows=False, color="truecolor"):
        if color not in ("truecolor", "256"):
            raise ValueError("color must be truecolor or 256")
        self.backend, self.windows, self.color = backend, windows, color
        self.decoder = InputDecoder()
        self.active = self.display = False
        self.handlers = {}
        self.last_size = None

    def _interrupt(self, signum, frame):
        raise TerminalInterrupted(signum)

    def __enter__(self):
        if self.active or self.display or self.handlers:
            raise RuntimeError("terminal context already active")
        if threading.current_thread() is not threading.main_thread():
            raise TerminalUnavailable("Interactive terminal must run on the main thread for signal cleanup.")
        self.decoder, self.last_size = InputDecoder(), None
        try:
            signals = [signal.SIGINT, signal.SIGTERM]
            signals += ([signal.SIGQUIT, signal.SIGTSTP] if os.name == "posix"
                        else [signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])
            for sig in signals:
                self.handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, self._interrupt)
            self.backend.enter()
            self.display = True  # partial write also requires rollback
            self._write(ENTER_DISPLAY)
            self.active = True
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        errors = []
        # Prevent a second handled signal interrupting restoration itself.
        for sig in self.handlers:
            signal.signal(sig, signal.SIG_IGN)
        try:
            if self.display:
                try:
                    self._write(LEAVE_DISPLAY)
                except Exception as error:
                    errors.append(error)
            try:
                self.backend.close()
            except Exception as error:
                errors.append(error)
        finally:
            for sig, handler in self.handlers.items():
                signal.signal(sig, handler)
            self.handlers.clear()
            self.active = self.display = False
        if errors:
            if exc_value is not None:
                exc_value.add_note(f"Terminal cleanup also failed: {errors!r}")
            else:
                raise errors[0]

    def _write(self, text):
        self.backend.output.write(text)
        self.backend.output.flush()

    def _require_active(self):
        if not self.active:
            raise RuntimeError("use terminal inside its context manager")

    def size(self):
        self._require_active()
        return self.backend.size()

    def poll(self, now):
        self._require_active()
        data = self.backend.read()
        if self.windows:
            self.decoder.feed_windows(data, now)
        else:
            self.decoder.feed(data, now)
        actions = self.decoder.actions(now)
        cols, rows = self.size()
        if cols < MIN_SIZE[0] or rows < MIN_SIZE[1]:
            self.decoder.axes.clear()
            return Actions(quit=actions.quit, help=actions.help)
        return actions

    def wait(self, timeout):
        self._require_active()
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("wait timeout must be finite and nonnegative")
        self.backend.wait(timeout)

    def present(self, frame: Frame, hud: tuple[str, ...]):
        cols, rows = self.size()
        chunks = []
        if (cols, rows) != self.last_size:
            chunks.append("\x1b[0m\x1b[2J")
        if cols < MIN_SIZE[0] or rows < MIN_SIZE[1]:
            chunks.append("\x1b[H\x1b[0m" + "Resize to 80x24; H help; Q/Esc quit."[:max(0, cols)])
        else:
            if (frame.columns <= 0 or frame.rows <= 0 or
                    len(frame.cells) != frame.columns * frame.rows or
                    len(frame.depth) != len(frame.cells)):
                raise ValueError("frame dimensions/cells/depth disagree")
            if frame.columns > cols or frame.rows + len(hud) > rows:
                # Resize raced frame creation. Do not wrap or crash; next tick
                # rebuilds viewport. Never silently alter the camera's aspect.
                chunks.append("\x1b[0m\x1b[2J\x1b[HResized; rebuilding view.")
            else:
                previous = None
                for row in range(frame.rows):
                    chunks.append(f"\x1b[{row+1};1H")
                    for cell in frame.cells[row*frame.columns:(row+1)*frame.columns]:
                        if len(cell.glyph) != 1 or not " " <= cell.glyph <= "~":
                            raise ValueError("frame glyph must be single printable ASCII")
                        colors = (cell.fg, cell.bg)
                        if colors != previous:
                            chunks.extend((_color(cell.fg, False, self.color), _color(cell.bg, True, self.color)))
                            previous = colors
                        chunks.append(cell.glyph)
                    chunks.append("\x1b[0m" + ("\x1b[K" if frame.columns < cols else ""))
                    previous = None
                for index, line in enumerate(hud):
                    text = _safe_text(line)[:cols]
                    chunks.append(f"\x1b[{frame.rows+index+1};1H\x1b[0m" + text + ("\x1b[K" if len(text) < cols else ""))
                used = frame.rows + len(hud)
                if used < rows:
                    chunks.append(f"\x1b[{used+1};1H\x1b[0m\x1b[J")
        self._write("".join(chunks))
        self.last_size = (cols, rows)


def open_terminal(*, color="truecolor"):
    """Existing no-argument Protocol entry point; optional component color mode."""
    if os.name == "nt":
        return TerminalAdapter(WindowsBackend(sys.stdin, sys.stdout), windows=True, color=color)
    if os.name == "posix":
        return TerminalAdapter(PosixBackend(sys.stdin, sys.stdout), color=color)
    raise TerminalUnavailable("Unsupported OS; use Linux xterm or Windows Terminal, or --smoke.")
