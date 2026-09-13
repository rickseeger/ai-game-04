"""Executable foundation only; deliberately does not simulate a finished city."""
import argparse
import json
from . import __version__
from .contracts import Camera, Vec3, Viewport


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lantern Survey - G11 foundation")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--smoke", action="store_true", help="validate foundation wiring and exit")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args(argv)
    camera = Camera(Vec3(0.0, 1.7, 0.0))
    viewport = Viewport(100, 32)
    if args.smoke:
        print(json.dumps({"status": "ok", "stage": "foundation", "seed": args.seed,
                          "eye_height_m": camera.eye.y, "viewport": [viewport.columns, viewport.rows],
                          "version": __version__}, sort_keys=True))
    else:
        print("LANTERN SURVEY | runnable foundation " + __version__)
        print("A planned street-level ASCII city photography expedition.")
        print("City rendering, movement and gameplay are not implemented in this foundation.")
        print("Launch verified; no terminal modes changed. See docs/design.md for the bounded design.")
    return 0
