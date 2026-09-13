"""Fresh keyboard-only technical probe. NOT a human/visual playtest."""
from pathlib import Path
import json, sys, time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.validate_app_pty import Session
output = Path(__file__).resolve().parent / "runtime"
launcher = ROOT.parent / "installed/lantern-survey-linux/lantern-survey"
if output.exists():
    raise SystemExit("Refusing to overwrite runtime evidence")
s = Session(output, launch_command=[str(launcher)], cwd=ROOT.parent)
notes = []
def note(label):
    r = s.latest
    notes.append({"label": label, "frame": r["frame"], "player": r["player"], "state": r["state"], "hud": r["hud"], "blocked": r["blocked"]})
    print(json.dumps(notes[-1]), flush=True)
def hold(keys, seconds):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        s.send(keys)
        s.next()
    s.wait(.25)
def snapshot(label):
    s.edge("p", "pause"); s.wait(.35); note(label); s.edge("p", "pause"); s.wait(.35)
try:
    note("Initial help at spawn")
    s.edge(" ", "shutter"); s.wait(.35); note("Photo rules help")
    s.edge(" ", "shutter"); s.wait(.35); note("First landmark card")
    s.edge("h", "help"); s.wait(.35)
    s.edge("e", "interact"); note("Premature depot submission")
    hold("w", 10); snapshot("North along starting street")
    hold("l", 1); hold("i", .4); snapshot("Turn right and look up")
    s.edge(" ", "shutter"); note("Unassisted photograph attempt")
    hold("w", 8); snapshot("Walk toward facade")
    hold("a", 4); snapshot("Strafe beside obstruction")
    hold("s", 3); hold("k", .4); snapshot("Back away and lower view")
    s.edge("h", "help"); s.wait(.35); note("Help after exploration")
    s.edge("h", "help"); s.wait(.35)
    s.resize(70,20); s.wait(.5); note("Undersize pause")
    s.resize(100,36); s.wait(.5)
    s.edge("r", "restart"); s.wait(.35)
    hold("wd", 8); snapshot("Diagonal facade collision from reset")
    report=s.close()
    (output.parent/"probe-notes.json").write_text(json.dumps({"kind":"independent technical probe, not meaningful human play", "route":notes, "exit_code":report["exit_code"]},indent=2)+"\n")
finally:
    if s.process.poll() is None:
        s.close()
