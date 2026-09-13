"""Reproducible stdlib-only source zipapp, runnable on Linux and Windows."""
from pathlib import Path
import hashlib
import zipfile

root = Path(__file__).resolve().parents[1]
out = root / "dist" / "lantern-survey.pyz"
out.parent.mkdir(exist_ok=True)
entries = {"__main__.py": b"from citywalk.app import main\nraise SystemExit(main())\n"}
for source in sorted((root / "citywalk").rglob("*.py")):
    entries[source.relative_to(root).as_posix()] = source.read_bytes().replace(b"\r\n", b"\n")
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
    for name, data in sorted(entries.items()):
        info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data)
print(out)
print("sha256 " + hashlib.sha256(out.read_bytes()).hexdigest())
