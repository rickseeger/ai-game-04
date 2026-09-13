"""Reproducible scored city walk, NOT an enjoyment assessment or app input loop."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from citywalk.camera import Perspective, camera_from_player
from citywalk.contracts import Actions, Viewport
from citywalk.gameplay import SurveyRules
from citywalk.movement import Walker, WALK_SPEED, TURN_SPEED, LOOK_SPEED
from citywalk.rendering import CityRenderer
from citywalk.spatial import CityGenerator

MAX_DT = .1


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Run:
    def __init__(self, seed, viewport=Viewport(100, 32)):
        self.world = CityGenerator().generate(seed)
        self.walker = Walker()
        self.renderer = CityRenderer(Perspective())
        self.rules = SurveyRules()
        self.viewport = viewport
        self.player = self.walker.spawn(self.world)
        self.state = self.rules.start(self.world.city)
        self.elapsed = 0.0
        self.distance = 0.0
        self.blocked_steps = 0
        self.tape = []
        self.events = []

    def tick(self, actions, dt):
        require(0 < dt <= MAX_DT, "simulation violates active integration step bound")
        require(self.state.phase == "playing", "route attempted to move after terminal phase")
        before = self.player
        motion = self.walker.step(self.world, before, actions, dt)
        self.player = motion.player  # sole player update: NEVER assign a waypoint pose
        distance = math.hypot(self.player.feet.x-before.feet.x,
                              self.player.feet.z-before.feet.z)
        require(distance <= WALK_SPEED*dt + 1e-8, "speed/teleport bound violated")
        require(self.world.walkable(self.player.feet, .3), "collision clearance violated")
        self.distance += distance
        self.blocked_steps += int(motion.blocked)
        sightings = self.renderer.sightings(self.world, camera_from_player(self.player), self.viewport)
        result = self.rules.step(self.world.city, self.state, self.player, actions, sightings, dt)
        self.state = result.state  # sole survey update: NEVER construct/inject photo records
        self.elapsed += dt
        default = asdict(Actions())
        self.tape.append([dt, {k: v for k, v in asdict(actions).items() if v != default[k]}])
        if result.messages:
            self.events.append({"tick": len(self.tape), "elapsed_s": self.elapsed,
                                "player": asdict(self.player), "state": asdict(self.state),
                                "sightings": [asdict(s) for s in sightings],
                                "messages": list(result.messages)})

    def orient(self, yaw, pitch):
        for _ in range(100):
            dy = (yaw-self.player.yaw+math.pi) % math.tau-math.pi
            dp = pitch-self.player.pitch
            seconds = max(abs(dy)/TURN_SPEED, abs(dp)/LOOK_SPEED)
            if seconds < 1e-10:
                return
            dt = min(MAX_DT, seconds)
            self.tick(Actions(turn=max(-1, min(1, dy/(TURN_SPEED*dt))),
                              look=max(-1, min(1, dp/(LOOK_SPEED*dt)))), dt)
        raise AssertionError("could not orient through Walker")

    def walk_to(self, feet):
        dx, dz = feet.x-self.player.feet.x, feet.z-self.player.feet.z
        if math.hypot(dx, dz) <= 1e-8:
            return
        self.orient(math.atan2(dx, dz), 0)
        for _ in range(2000):
            distance = math.hypot(feet.x-self.player.feet.x, feet.z-self.player.feet.z)
            if distance <= 1e-8:
                return
            self.tick(Actions(forward=1), min(MAX_DT, distance/WALK_SPEED))
            require(self.blocked_steps == 0, "route witness blocked by real movement collision")
        raise AssertionError("could not reach waypoint through Walker")

    def summary(self):
        depot = self.world.city.depot
        return {"seed": self.world.city.seed, "viewport": asdict(self.viewport),
                "elapsed_s": self.elapsed, "distance_m": self.distance,
                "steps": len(self.tape), "blocked_steps": self.blocked_steps,
                "depot_distance_m": math.hypot(self.player.feet.x-depot.x, self.player.feet.z-depot.z),
                "final_player": asdict(self.player), "final_state": asdict(self.state),
                "events": self.events}

    def check_success(self):
        require(self.state.phase == "won", "did not win the survey")
        require(len(self.state.photos) >= 3, "not enough distinct photographs")
        require(self.elapsed <= 420, "actual route exceeds 420 s design target")
        require(abs(self.state.remaining_s-(600-self.elapsed)) < 1e-8,
                "active movement/framing/shutter/submission time was not fully charged")
        require(self.summary()["depot_distance_m"] <= 3, "submission away from depot")


def simulate(seed, viewport=Viewport(100, 32)):
    run = Run(seed, viewport)
    route = run.world.survey_route()  # planning metadata only; NOT movement
    landmarks = {l.id: l for l in run.world.city.landmarks}
    todo = list(route.landmark_ids)
    for waypoint in route.points:
        run.walk_to(waypoint)
        if todo:
            landmark = landmarks[todo[0]]
            if math.hypot(waypoint.x-landmark.viewpoint.x, waypoint.z-landmark.viewpoint.z) < 1e-8:
                run.orient(landmark.view_yaw, landmark.view_pitch)
                run.tick(Actions(shutter=True), MAX_DT)
                require(landmark.id in dict(run.state.photos),
                        f"real renderer rejected viewpoint {landmark.id}")
                todo.pop(0)
    require(not todo, "route omitted photo opportunities")
    run.tick(Actions(interact=True), MAX_DT)
    run.check_success()
    return {"route_landmark_ids": list(route.landmark_ids),
            "waypoints": [asdict(p) for p in route.points],
            "summary": run.summary(), "tape": run.tape}


def replay(record):
    summary = record["summary"]
    run = Run(summary["seed"], Viewport(**summary["viewport"]))
    for dt, fields in record["tape"]:
        run.tick(Actions(**fields), dt)
    run.check_success()
    # JSON canonicalization accounts only for tuple/list serialization, never
    # tolerance-matches scores/poses or substitutes recorded state into the run.
    require(json.dumps(run.summary(), sort_keys=True) == json.dumps(summary, sort_keys=True),
            "fresh action-only replay diverged from recorded outcomes")
    return run.summary()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[11, 93, 2026])
    parser.add_argument("--output", type=Path, default=ROOT / "docs/gameplay-simulation.json")
    parser.add_argument("--replay", type=Path, help="verify committed tape without replanning or writing files")
    args = parser.parse_args()
    if args.replay:
        report = json.loads(args.replay.read_text())
        for record in report["runs"]:
            summary = replay(record)
            print(json.dumps({k: summary[k] for k in ("seed", "elapsed_s", "distance_m", "steps", "final_state")}))
        print("PASS: fresh action-only replays match all recorded outcomes")
    else:
        records = [simulate(seed) for seed in args.seeds]
        for record in records:
            replay(record)
            summary = record["summary"]
            print(json.dumps({k: summary[k] for k in ("seed", "elapsed_s", "distance_m", "steps", "final_state")}))
        report = {"schema": 1, "max_dt_s": MAX_DT, "replay_verified": True,
                  "limitations": "Headless planned route and action replay prove reachability, not enjoyment, keyboard usability or city beauty.",
                  "runs": records}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Record every Actions/dt pair, including all turns and framing time.
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print("PASS: complete routes <=420 s; independent fresh-state replay matched; evidence:", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
