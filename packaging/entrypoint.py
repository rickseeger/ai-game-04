"""Source distribution entrypoint; no site packages or working-directory imports."""
import sys

if sys.version_info < (3, 11):
    print("Lantern Survey requires Python 3.11 or newer.", file=sys.stderr)
    raise SystemExit(2)

from citywalk.app import main

raise SystemExit(main())
