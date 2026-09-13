"""Build a deterministic Python-runtime Linux tarball from a clean Git commit."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "lantern-survey-linux"


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def committed_source(root):
    sha = git(root, "rev-parse", "HEAD")
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("Refusing ambiguous provenance: commit or remove working-tree changes first")
    return sha


def archive_bytes(root, sha):
    # Read committed blobs, not ignored/untracked modules from the working tree.
    def blob(name):
        return subprocess.check_output(["git", "show", f"{sha}:{name}"], cwd=root)
    names = git(root, "ls-tree", "-r", "--name-only", sha, "citywalk").splitlines()
    entries = {name: (blob(name), 0o644) for name in names if name.endswith(".py")}
    for source, target, mode in (("packaging/lantern-survey", "lantern-survey", 0o755),
                                 ("packaging/entrypoint.py", "entrypoint.py", 0o644),
                                 ("docs/linux.md", "README.md", 0o644)):
        entries[target] = (blob(source), mode)
    manifest = {"schema": 1, "source_commit": sha,
                "repository": "https://github.com/rickseeger/ai-game-04.git",
                "target": "linux-python-runtime", "python_minimum": "3.11",
                "windows": "deferred; not built or runtime validated",
                "files_sha256": {n: hashlib.sha256(data).hexdigest()
                                 for n, (data, _) in sorted(entries.items())}}
    entries["BUILD.json"] = ((json.dumps(manifest, sort_keys=True, indent=2)+"\n").encode(), 0o644)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, (data, mode) in sorted(entries.items()):
            info = tarfile.TarInfo(f"{PREFIX}/{name}")
            info.size, info.mode, info.mtime = len(data), mode, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return out.getvalue(), manifest


def build(root, output):
    sha = committed_source(root)
    data, manifest = archive_bytes(root, sha)
    output.mkdir(parents=True, exist_ok=True)
    name = f"lantern-survey-linux-{sha}.tar.gz"
    artifact = output / name
    artifact.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    (output/"SHA256SUMS").write_text(f"{checksum}  {name}\n")
    (output/"provenance.json").write_text(json.dumps({**manifest, "artifact": name,
        "artifact_sha256": checksum, "build_command": "python3 tools/package_linux.py"}, indent=2)+"\n")
    print(artifact)
    print("sha256 " + checksum)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"dist")
    args = parser.parse_args()
    build(ROOT, args.output.resolve())
