"""Fresh public clone, isolated stdlib environment, install and real Linux PTY run."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time


def validate(commit, output, remote):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Use the full 40-character lowercase commit SHA")
    output.mkdir(parents=True, exist_ok=False)
    logs = output/"logs"
    logs.mkdir()
    home = output/"home"
    home.mkdir()
    runtime = output/"unrelated working directory"
    runtime.mkdir()
    commands = []
    report = {"passed": False, "source_commit": commit, "remote": remote,
              "host": platform.platform(), "bootstrap_python": sys.version,
              "isolation": "fresh public clone; fresh HOME; venv --without-pip, no system site packages; allowlisted environment; installed launcher from unrelated cwd (not a container)",
              "windows": "explicitly deferred; no artifact or native execution claimed",
              "independent_beauty_or_fun_validated": False}
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8",
           "LC_ALL": "C.UTF-8", "TERM": "xterm-256color",
           "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null"}

    def run(argv, cwd, timeout=180):
        start = time.monotonic()
        index = len(commands)
        stdout = logs/f"{index:02d}.stdout.log"
        stderr = logs/f"{index:02d}.stderr.log"
        entry = {"argv": [str(a) for a in argv], "cwd": str(cwd),
                 "stdout": str(stdout.relative_to(output)), "stderr": str(stderr.relative_to(output))}
        commands.append(entry)
        with stdout.open("w") as out, stderr.open("w") as err:
            try:
                proc = subprocess.run(entry["argv"], cwd=cwd, env=env,
                                      stdout=out, stderr=err, timeout=timeout)
                entry["returncode"] = proc.returncode
            finally:
                entry["wall_seconds"] = time.monotonic()-start
                (output/"commands.json").write_text(json.dumps(commands, indent=2)+"\n")
        print(f"{index:02d} exit={proc.returncode}:", entry["argv"], flush=True)
        if proc.returncode:
            raise RuntimeError(f"Command {index} failed: see {stderr}")
        return stdout.read_text()

    try:
        repo = output/"clone"
        run(["git", "clone", remote, repo], output)
        run(["git", "checkout", "--detach", commit], repo)
        assert run(["git", "rev-parse", "HEAD"], repo).strip() == commit
        venv = output/"venv"
        run([sys.executable, "-m", "venv", "--without-pip", venv], output)
        env["PATH"] = str(venv/"bin")+":/usr/bin:/bin"
        report["environment"] = dict(env)
        details = run(["python3", "-c", "import sys,platform,importlib.metadata,json,zlib; print(json.dumps(dict(python=sys.version,executable=sys.executable,prefix=sys.prefix,base_prefix=sys.base_prefix,platform=platform.platform(),machine=platform.machine(),packages=[d.metadata['Name'] for d in importlib.metadata.distributions()],zlib=zlib.ZLIB_VERSION),indent=2))"], runtime)
        report["runtime_environment"] = json.loads(details)
        assert report["runtime_environment"]["packages"] == []
        assert report["runtime_environment"]["prefix"] != report["runtime_environment"]["base_prefix"]
        run(["python3", "-m", "unittest", "discover", "-s", "tests", "-v"], repo)
        run(["python3", "tools/build.py"], repo)
        run(["python3", "dist/lantern-survey.pyz", "--smoke", "--seed", "11"], repo)
        run(["python3", "tools/package_linux.py"], repo)
        artifact = repo/"dist"/f"lantern-survey-linux-{commit}.tar.gz"
        first = hashlib.sha256(artifact.read_bytes()).hexdigest()
        run(["python3", "tools/package_linux.py"], repo)
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == first
        report["two_builds_byte_identical"] = True
        run(["sha256sum", "-c", "SHA256SUMS"], repo/"dist")
        install = home/".local/opt"
        run(["mkdir", "-p", install], runtime)
        run(["tar", "-xzf", artifact, "-C", install], repo/"dist")
        installed = install/"lantern-survey-linux"
        launcher = installed/"lantern-survey"
        manifest = json.loads((installed/"BUILD.json").read_text())
        assert manifest["source_commit"] == commit
        for name, digest in manifest["files_sha256"].items():
            assert hashlib.sha256((installed/name).read_bytes()).hexdigest() == digest, name
        run([launcher, "--smoke", "--seed", "11"], runtime)
        run([launcher, "--help"], runtime)
        # The controller imports route planning from the fresh clone; the GAME
        # subprocess imports exclusively from the extracted distribution.
        run(["python3", "tools/validate_app_pty.py", "--output", output/"pty",
             "--launcher", launcher, "--cwd", runtime], repo, timeout=600)
        run(["python3", "tools/verify_app_evidence.py", output/"pty"], repo, timeout=240)
        meta = json.loads((output/"pty/metadata.json").read_text())
        assert meta["source_directory"] == str(installed/"citywalk")
        assert meta["distribution"] == manifest
        assert meta["executable"] == str(venv/"bin/python3")
        assert str(repo) not in meta["sys_path"]
        expected = {n.split("/")[-1]: h for n,h in manifest["files_sha256"].items() if n.startswith("citywalk/")}
        assert meta["source_sha256"] == expected and expected
        raw = gzip.decompress((output/"pty/terminal.ansi.gz").read_bytes())
        assert b"\x1b[38;2;" in raw and b"LANTERN SURVEY" in raw
        report["actual_truecolor_ansi_captured"] = True
        report["installed_sources_match_manifest_and_commit"] = True
        assert run(["git", "status", "--porcelain"], repo).strip() == ""
        deliveries = output/"distribution"
        deliveries.mkdir()
        for name in (artifact.name, "SHA256SUMS", "provenance.json", "lantern-survey.pyz"):
            shutil.copyfile(repo/"dist"/name, deliveries/name)
        report["artifact"] = str((deliveries/artifact.name).relative_to(output))
        report["artifact_sha256"] = first
        report["legacy_pyz_sha256"] = hashlib.sha256((deliveries/"lantern-survey.pyz").read_bytes()).hexdigest()
        report["pty_result"] = json.loads((output/"pty/summary.json").read_text())
        report["verification"] = json.loads((output/"pty/verification.json").read_text())
        report["passed"] = True
    except BaseException as exc:
        report["error"] = repr(exc)
        raise
    finally:
        (output/"validation.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote", default="https://github.com/rickseeger/ai-game-04.git")
    args = parser.parse_args()
    validate(args.commit, args.output.resolve(), args.remote)
