# Linux delivery: executed result

Candidate: b90fb50e368f9d40592edaee4575ce31a3a2fe1a.
The evidence-only commit containing this report is NOT the artifact source commit.
Use the candidate above for exact rebuilds via docs/linux.md.

Two independent public HTTPS clones and empty --without-pip venvs on Linux
passed all 157 tests with Python 3.11.16 and 3.14.4. Each built the Linux tarball
twice with identical bytes; the two Python versions also produced the same hash:

    93428c045eb2178c3d6c1cf5ecb815837215d10e9c4d7debfb3e6cafb599c926

Both installed the tarball into a fresh HOME, then ran its launcher from an
unrelated directory in a controlling PTY. Each walked, turned/looked, collided
with a real facade, paused/resized, photographed three real landmarks, returned
to win with 420 points, restarted/changed seed, and quit with exit 0. Exact native
termios were restored. Read-back replay matched 4,127 frames (3.11) and 4,911
frames (3.14), regenerating all 24 actual RGB checkpoints in each run.

GitHub Actions run 34774048306 completed successfully for both Ubuntu matrix
jobs (3.11 and 3.14), including tests, zipapp smoke, Linux packaging and upload.
No Windows job was scheduled. This is verified CI output, not only configuration.

Full commands/stdout/stderr, environment, manifests, input logs, raw color ANSI,
RGB/depth checkpoints, exact termios and reports are archived under:

    /opt/g-harness/workspace/G11/node_10_step_102/deliverables/

The runnable tarball and SHA256SUMS are in that same directory. Evidence archives:
linux-validation-311-evidence.tar.gz and linux-validation-314-evidence.tar.gz.
Each includes a hashed evidence-files.json index. Extract an archive to inspect
linux-validation-314/pty/frames.html (or the 311 counterpart); standalone HTML
copies are linux-314-frames.html and linux-311-frames.html beside the archives.
Absolute artifact paths, checksums, exact results and CI URLs are in the adjacent
linux-validation.json. Archives retain historical execution paths in their logs.

No native Windows artifact or execution is claimed: Windows is explicitly
deferred by the assignment, leaving the older broad both-platform contract open.
This is engineering validation, not independent evidence of beauty or fun.
Node 11 must assess the actual installed game. No durable node/root completion
is declared by this worker.
