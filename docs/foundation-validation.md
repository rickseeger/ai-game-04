# Foundation validation (node 1 only)

Repository verified before writing source:
- Read /opt/g-harness/data/g.db using SQLite URI mode=ro. G11 trees.repo_url
  was exactly git@github.com:rickseeger/ai-game-04.git. Read node 1 full contract,
  other node interfaces/acceptance requirements and the full authoritative
  /opt/g-harness/docs/missions/g11-3d-ascii-city.md mission specification.
- `git ls-remote --symref git@github.com:rickseeger/ai-game-04.git` exited 0
  without refs. `git clone git@github.com:rickseeger/ai-game-04.git repo` succeeded
  with the empty-repository warning; workspace initially empty, clone contained
  only .git. No existing work overwritten. `git remote -v` matched configured URL.
- Before first commit, ran `git config user.name 'the gardener'` and
  `git config user.email 'root@g.seeger.net'` in this repository.
- No controller commands or mission/node-state writes performed.

Actual local validation: see foundation-run.json for command argv, complete
stdout/stderr, return codes, platform and Python version (Linux / Python 3.14.4).

    python3 -m citywalk
    python3 -m citywalk --smoke --seed 11
    python3 -m unittest discover -s tests -v
    python3 tools/build.py
    python3 tools/build.py
    python3 /opt/g-harness/workspace/G11/node_1_step_93/repo/dist/lantern-survey.pyz --smoke --seed 11
    script -q -e -c 'python3 -m citywalk' ../foundation-launch.typescript
    git diff --check

All exited 0. Five unittest cases passed. Actual default source launch and Linux
pseudo-terminal launch printed the foundation banner and honest not-implemented
notice, then exited normally; no terminal control modes are used at this stage.
Zipapp smoke passed from a temporary directory outside the repository. Two
builds produced identical SHA-256:

    36f3fdd06e23d53de8422265ab880e42e655c97ac5cb1d4e51cda5d2441d41d2

The terminal transcript is a sibling workspace artifact, not a city rendering.
Commit identity/SHA, push read-back and fresh remote clone verification are
recorded by this worker in ../completion-evidence.json after committing, to
avoid the impossible requirement of a commit embedding its own SHA. Independently
identify the committed validation record with `git log -1 --format=fuller`.

Limits: no downstream city algorithms, renderer, movement, keyboard lifecycle,
or game rules have been implemented. No Windows runtime executed locally and
no remote CI result claimed. No beauty/fun assessment claimed. Future Windows
packaging/playtest and experiential gates remain necessary, as docs/design.md
specifies. Foundation completion is not mission completion.
