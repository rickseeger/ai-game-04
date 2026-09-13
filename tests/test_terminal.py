"""Portable deterministic tests. Fake Win32 coverage is NOT a native launch."""
import io
import os
import signal
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from citywalk.contracts import Actions, Cell, Frame
from citywalk.terminal import (
    AXES, EDGES, ENTER_DISPLAY, LEAVE_DISPLAY, InputDecoder, PosixBackend,
    TerminalAdapter, TerminalInterrupted, TerminalUnavailable, WindowsBackend,
    WindowsConsole, _color, open_terminal,
)


def frame(cols=2, rows=2):
    return Frame(cols, rows, (Cell("#", (255, 95, 0), (0, 0, 0)),) * (cols*rows), (1.0,) * (cols*rows))


class DecoderTests(unittest.TestCase):
    def test_every_ascii_control_and_uppercase(self):
        mapping = {k: v for k, v in AXES.items() if len(k) == 1}
        mapping.update({k: (v, True) for k, v in EDGES.items() if len(k) == 1})
        for key, (field, value) in mapping.items():
            for variant in (key, key.upper()):
                with self.subTest(key=variant):
                    d = InputDecoder()
                    d.feed(variant.encode(), 0)
                    self.assertEqual(d.actions(0), Actions(**{field: value}))

    def test_all_linux_arrows_and_every_split(self):
        for final, field, value in (("A", "look", 1), ("B", "look", -1),
                                    ("C", "turn", 1), ("D", "turn", -1)):
            for sequence in ("\x1b["+final, "\x1bO"+final, "\x1b[1;5"+final):
                for split in range(1, len(sequence)):
                    with self.subTest(sequence=repr(sequence), split=split):
                        d = InputDecoder()
                        d.feed(sequence[:split], 0)
                        self.assertEqual(d.actions(0), Actions())
                        d.feed(sequence[split:], .020)
                        self.assertEqual(d.actions(.020), Actions(**{field: value}))

    def test_windows_every_extended_arrow_split_and_prefix(self):
        for prefix in ("\x00", "\xe0"):
            for code, field, value in (("H", "look", 1), ("P", "look", -1),
                                       ("M", "turn", 1), ("K", "turn", -1)):
                d = InputDecoder()
                d.feed_windows([prefix], 0)
                self.assertEqual(d.actions(0), Actions())
                d.feed_windows([code], .01)
                self.assertEqual(d.actions(.01), Actions(**{field: value}))
        d = InputDecoder()
        d.feed_windows(["\x00", "q"], 0)  # unknown scan code isn't Q
        self.assertEqual(d.actions(0), Actions())

    def test_windows_every_ordinary_key(self):
        for key in "wWsSaAdDjJlLiIkK eEpPhH?rRnNqQ":
            a, b = InputDecoder(), InputDecoder()
            a.feed(key, 0)
            b.feed_windows([key], 0)
            self.assertEqual(a.actions(0), b.actions(0))

    def test_lone_escape_deadline_and_no_mid_csi_quit(self):
        d = InputDecoder()
        d.feed("\x1b", 0)
        self.assertFalse(d.actions(.039).quit)
        self.assertTrue(d.actions(.041).quit)
        self.assertFalse(d.actions(.042).quit)
        for partial in ("\x1b[", "\x1b[1;", "\x1bO"):
            d = InputDecoder()
            d.feed(partial, 0)
            self.assertEqual(d.actions(.05), Actions())
            d.feed("Aw", .06)
            self.assertEqual(d.actions(.06), Actions(forward=1))

    def test_axis_repeat_expiry_latest_opposite_and_diagonal(self):
        d = InputDecoder()
        d.feed("wa", 0)
        self.assertEqual(d.actions(.139), Actions(forward=1, strafe=-1))
        self.assertEqual(d.actions(.141), Actions())
        d.feed("wsd", .2)
        self.assertEqual(d.actions(.2), Actions(forward=-1, strafe=1))
        d.feed("s", .3)
        self.assertEqual(d.actions(.4), Actions(forward=-1))
        self.assertEqual(d.actions(.441), Actions())

    def test_every_edge_suppressed_until_quiet(self):
        for key, field in EDGES.items():
            d = InputDecoder()
            d.key(key, 0)
            self.assertTrue(getattr(d.actions(0), field))
            self.assertFalse(getattr(d.actions(.01), field))
            for now in (.10, .20, .30):
                d.key(key, now)
                self.assertFalse(getattr(d.actions(now), field))
            d.key(key, .551)
            self.assertTrue(getattr(d.actions(.551), field))

    def test_unknown_sequences_paste_strings_nonascii_not_actions(self):
        for data in ("\x1b[99~", "\x1b[?25h", "\x1bx", "\x1b]0;quit\x07",
                     "\x1bPqwe\x1b\\", "\x1b[200~qwe \x1b[201~", b"\xff\xc3\xa9"):
            d = InputDecoder()
            d.feed(data, 0)
            self.assertEqual(d.actions(.1), Actions(), repr(data))
            d.feed("q", .2)
            self.assertTrue(d.actions(.2).quit)

    def test_sequence_storage_bounded(self):
        d = InputDecoder()
        d.feed("\x1b[" + "1" * 10000, 0)
        self.assertLessEqual(len(d.sequence), 32)
        self.assertFalse(d.actions(.1).quit)

    def test_ctrl_c_and_clock_validation(self):
        for method in ("feed", "feed_windows"):
            with self.assertRaises(TerminalInterrupted):
                getattr(InputDecoder(), method)("\x03", 0)
        for partial in ("\x1b[", "\x1b]", "\x1b[200~"):
            d = InputDecoder()
            d.feed(partial, 0)
            with self.assertRaises(TerminalInterrupted):
                d.feed("\x03", .01)
        d = InputDecoder()
        d.feed_windows(["\xe0"], 0)
        with self.assertRaises(TerminalInterrupted):
            d.feed_windows(["\x03"], .01)
        d = InputDecoder()
        d.actions(1)
        for now in (0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                d.actions(now)


class TTY(io.StringIO):
    def isatty(self):
        return True


class FakeBackend:
    def __init__(self):
        self.output = TTY()
        self.dimensions = (80, 24)
        self.data = b""
        self.closed = False
        self.enter_error = None

    def enter(self):
        if self.enter_error:
            raise self.enter_error

    def close(self):
        self.closed = True

    def read(self):
        data, self.data = self.data, b""
        return data

    def size(self):
        return self.dimensions

    def wait(self, timeout):
        self.waited = timeout


class LifecycleTests(unittest.TestCase):
    def test_normal_exception_and_interruption_restore_display_handlers(self):
        for error in (None, RuntimeError("injected"), TerminalInterrupted(signal.SIGTERM)):
            backend = FakeBackend()
            old = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
            try:
                with TerminalAdapter(backend) as term:
                    term.present(frame(), ("HUD",))
                    if error:
                        raise error
            except BaseException as caught:
                self.assertIs(caught, error)
            self.assertTrue(backend.closed)
            output = backend.output.getvalue()
            self.assertTrue(output.startswith(ENTER_DISPLAY))
            self.assertTrue(output.endswith(LEAVE_DISPLAY))
            self.assertEqual(old, {s: signal.getsignal(s) for s in old})

    def test_quit_suspend_and_break_signals_are_handled_when_available(self):
        with TerminalAdapter(FakeBackend()) as term:
            names = ("SIGQUIT", "SIGTSTP") if os.name == "posix" else ("SIGBREAK",)
            for name in names:
                if hasattr(signal, name):
                    sig = getattr(signal, name)
                    with self.assertRaises(TerminalInterrupted):
                        signal.getsignal(sig)(sig, None)

    def test_cleanup_generic_error_does_not_mask_original(self):
        b = FakeBackend()
        def fail():
            raise Exception("termios-like error (not OSError)")
        b.close = fail
        original = RuntimeError("render failed")
        with self.assertRaises(RuntimeError) as caught:
            with TerminalAdapter(b):
                raise original
        self.assertIs(caught.exception, original)
        self.assertIn("termios-like", original.__notes__[0])


    def test_enter_failure_rolls_back_and_does_not_emit_display(self):
        b = FakeBackend()
        b.enter_error = OSError("setup")
        with self.assertRaises(OSError):
            with TerminalAdapter(b):
                self.fail("entered")
        self.assertTrue(b.closed)
        self.assertEqual(b.output.getvalue(), "")

    def test_output_failure_still_restores_modes_and_preserves_exception(self):
        class BrokenOutput(TTY):
            def write(self, value):
                raise BrokenPipeError("disconnected")
        b = FakeBackend()
        b.output = BrokenOutput()
        with self.assertRaises(BrokenPipeError) as caught:
            with TerminalAdapter(b):
                pass
        self.assertTrue(b.closed)
        self.assertIn("cleanup also failed", caught.exception.__notes__[0])

    def test_resize_small_gates_motion_and_actions_but_allows_help_quit(self):
        b = FakeBackend()
        with TerminalAdapter(b) as term:
            term.present(frame(), ())
            b.dimensions = (40, 10)
            b.data = b"w ephq"
            self.assertEqual(term.poll(0), Actions(help=True, quit=True))
            term.present(frame(), ())
            self.assertIn("Resize to 80x24", b.output.getvalue())
            b.dimensions = (100, 36)
            term.present(frame(), ())
            self.assertEqual(term.size(), (100, 36))
            self.assertEqual(b.output.getvalue().count("\x1b[2J"), 4)

    def test_frame_resize_race_notice_then_recovers(self):
        b = FakeBackend()
        with TerminalAdapter(b) as term:
            term.present(frame(100, 32), ("HUD",))
            self.assertIn("Resized; rebuilding view.", b.output.getvalue())
            term.present(frame(), ())

    def test_no_newlines_or_bottom_right_erase_and_hud_sanitized(self):
        b = FakeBackend()
        with TerminalAdapter(b) as term:
            term.present(frame(80, 23), ("x" * 80,))
            self.assertNotIn("\n", b.output.getvalue())
            self.assertIn("x"*80, b.output.getvalue())
            self.assertNotIn("x"*80 + "\x1b[K", b.output.getvalue())
            self.assertNotIn("#\x1b[0m\x1b[K", b.output.getvalue())
            term.present(frame(), ("bad\x1b[2J\n",))
            self.assertIn("bad?[2J?", b.output.getvalue())

    def test_invalid_frame_exception_cleans_up(self):
        b = FakeBackend()
        with self.assertRaises(ValueError):
            with TerminalAdapter(b) as term:
                term.present(Frame(2, 2, (), ()), ())
        self.assertTrue(b.output.getvalue().endswith(LEAVE_DISPLAY))
        for cell in (Cell("\x1b", (1, 2, 3), (0, 0, 0)), Cell("#", (256, 0, 0), (0, 0, 0))):
            with self.assertRaises(ValueError):
                with TerminalAdapter(FakeBackend()) as term:
                    term.present(Frame(1, 1, (cell,), (1,)), ())

    def test_color_modes(self):
        self.assertEqual(_color((255, 0, 0), False, "truecolor"), "\x1b[38;2;255;0;0m")
        self.assertEqual(_color((255, 0, 0), False, "256"), "\x1b[38;5;196m")
        self.assertEqual(_color((128, 128, 128), True, "256"), "\x1b[48;5;244m")
        with TerminalAdapter(FakeBackend(), color="256") as term:
            term.present(frame(), ())
            self.assertIn(";5;", term.backend.output.getvalue())
            self.assertNotIn(";2;255", term.backend.output.getvalue())

    def test_poll_nonblocking_contract_and_wait_delegation(self):
        with TerminalAdapter(FakeBackend()) as term:
            with patch("citywalk.terminal.time.sleep", side_effect=AssertionError("poll slept")):
                self.assertEqual(term.poll(0), Actions())
            term.wait(.02)
            self.assertEqual(term.backend.waited, .02)
            for duration in (-1, float("nan")):
                with self.assertRaises(ValueError):
                    term.wait(duration)
        with self.assertRaises(RuntimeError):
            term.poll(1)

    def test_reuse_and_nested_entry(self):
        term = TerminalAdapter(FakeBackend())
        with term:
            with self.assertRaises(RuntimeError):
                term.__enter__()
        with term:
            self.assertEqual(term.poll(0), Actions())

    def test_redirected_streams_and_unsupported_term(self):
        for backend in (PosixBackend, WindowsBackend):
            with self.assertRaisesRegex(TerminalUnavailable, "smoke"):
                with TerminalAdapter(backend(io.StringIO(), io.StringIO())):
                    self.fail("entered")
        if os.name == "posix":
            for name in ("", "dumb", "unknown", "not-a-terminal"):
                with patch.dict(os.environ, {"TERM": name}):
                    with self.assertRaises(TerminalUnavailable):
                        PosixBackend(TTY(), TTY()).enter()


class FakeConsole:
    """Win32 API mock: validates decisions, NOT ctypes ABI or console behavior."""
    def __init__(self):
        self.modes = {False: 0x267, True: 0x02}
        self.cursor = (27, False)
        self.attributes = 0x71
        self.events = []
        self.data = []
        self.fail_vt = False
        self.fail_cursor = False

    def get_mode(self, output):
        return self.modes[output]

    def set_mode(self, output, value):
        self.events.append(("mode", output, value))
        if self.fail_vt and output and value & 4:
            raise OSError("VT unsupported")
        self.modes[output] = value

    def get_cursor(self):
        return self.cursor

    def set_cursor(self, value):
        self.events.append(("cursor", value))
        if self.fail_cursor:
            raise OSError("cursor failed")
        self.cursor = value

    def info(self):
        return SimpleNamespace(attributes=self.attributes)

    def set_attributes(self, value):
        self.events.append(("attributes", value))
        self.attributes = value

    def read(self):
        value, self.data = self.data, []
        return value

    def size(self):
        return 100, 36


class WindowsMockTests(unittest.TestCase):
    def test_modes_cursor_color_input_and_cleanup(self):
        c, output = FakeConsole(), TTY()
        original = dict(c.modes)
        b = WindowsBackend(TTY(), output, c)
        with TerminalAdapter(b, windows=True) as term:
            self.assertEqual(c.modes[False], (original[False] | 0x80) & ~0x247)
            self.assertEqual(c.modes[True], original[True] | 5)
            c.data = ["\xe0", "K", "W", " "]
            self.assertEqual(term.poll(0), Actions(turn=-1, forward=1, shutter=True))
            self.assertEqual(term.size(), (100, 36))
            term.present(frame(), ("Windows mock only",))
            with patch("citywalk.terminal.time.sleep") as sleep:
                term.wait(.01)
                sleep.assert_called_once_with(.01)
        self.assertEqual(c.modes, original)
        self.assertEqual(c.cursor, (27, False))
        self.assertEqual(c.attributes, 0x71)
        self.assertTrue(output.getvalue().endswith(LEAVE_DISPLAY))

    def test_vt_failure_rolls_back_input_and_output(self):
        c = FakeConsole()
        original = dict(c.modes)
        c.fail_vt = True
        output = TTY()
        with self.assertRaisesRegex(TerminalUnavailable, "Windows 10/11"):
            with TerminalAdapter(WindowsBackend(TTY(), output, c), windows=True):
                self.fail("entered")
        self.assertEqual(c.modes, original)
        self.assertEqual(output.getvalue(), "")

    def test_ctrl_c_exception_and_all_cleanup_attempted(self):
        for event in ("interrupt", "exception", "cleanup_failure"):
            c = FakeConsole()
            original = dict(c.modes)
            with self.assertRaises((TerminalInterrupted, RuntimeError, OSError)):
                with TerminalAdapter(WindowsBackend(TTY(), TTY(), c), windows=True) as term:
                    if event == "interrupt":
                        c.data = ["\x03"]
                        term.poll(0)
                    elif event == "exception":
                        raise RuntimeError("injected")
                    else:
                        c.fail_cursor = True
            self.assertEqual(c.modes, original)
            self.assertIn(("attributes", 0x71), c.events)

    def test_real_read_wrapper_is_bounded_and_never_reads_without_kbhit(self):
        console = WindowsConsole.__new__(WindowsConsole)
        with patch("builtins.input", side_effect=AssertionError("blocking input")):
            class Msvcrt:
                def kbhit(self): return False
                def getwch(self): raise AssertionError("blocking getwch")
            console.msvcrt = Msvcrt()
            self.assertEqual(console.read(), [])
            console.msvcrt = SimpleNamespace(kbhit=lambda: True, getwch=lambda: "w")
            self.assertEqual(len(console.read()), 256)

    def test_factory_platform_selection(self):
        with patch("citywalk.terminal.os.name", "nt"):
            self.assertIsInstance(open_terminal().backend, WindowsBackend)
        with patch("citywalk.terminal.os.name", "posix"):
            self.assertIsInstance(open_terminal().backend, PosixBackend)


if __name__ == "__main__":
    unittest.main()
