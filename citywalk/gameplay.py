"""Lantern Survey: pure deterministic rules over the shared immutable values."""
import math

from .contracts import Actions, City, GameResult, Player, Sighting, SurveyState

SURVEY_SECONDS = 600.0
REQUIRED_PHOTOS = 3
MIN_RANGE_M = 18.0
MAX_RANGE_M = 65.0
MAX_BEARING_ERROR = math.radians(12)
DEPOT_RADIUS_M = 3.0
PHOTO_POINTS = 100
CROWN_POINTS = 40


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _landmarks(city):
    result = {landmark.id: landmark for landmark in city.landmarks}
    if len(result) != len(city.landmarks) or any(not key for key in result):
        raise ValueError("city landmark ids must be nonempty and unique")
    return result


def _records(state, landmarks):
    # State is owned by these rules, not input. Fail closed if a consumer passes
    # forged/foreign records: never count duplicate or unknown ids toward a win.
    photos = {}
    for key, points in state.photos:
        if (key not in landmarks or key in photos or type(points) is not int or
                points not in (PHOTO_POINTS, PHOTO_POINTS + CROWN_POINTS)):
            raise ValueError("invalid survey photo records")
        photos[key] = points
    if type(state.score) is not int or state.score != sum(photos.values()):
        raise ValueError("score must equal the unique photo awards")
    if not _finite(state.remaining_s) or not 0 <= state.remaining_s <= SURVEY_SECONDS:
        raise ValueError("invalid remaining survey time")
    return photos


def _rejection(sighting):
    if not (_finite(sighting.range_m) and _finite(sighting.bearing_error)):
        return "invalid sighting geometry"
    if sighting.range_m < MIN_RANGE_M:
        return "too near; step back to at least 18 m"
    if sighting.range_m > MAX_RANGE_M:
        return "too far; approach within 65 m"
    if abs(sighting.bearing_error) > MAX_BEARING_ERROR:
        return "off-center; aim within 12 degrees"
    # Renderer.visible already includes target projection and clip tests. The
    # shared Sighting cannot distinguish occlusion from vertical screen clipping.
    if not sighting.visible:
        return "target occluded or outside the scene; seek a clear view and adjust pitch"
    return None


class SurveyRules:
    """Gameplay implementation; stateless and safe to share across sessions.

    Application owns UI gates and edge detection. start(city) is the ONLY reset;
    no carried photos, implicit restart, clock, random state or peer imports.
    Invalid elapsed time raises ValueError even in an otherwise inert phase.
    """

    def start(self, city: City) -> SurveyState:
        _landmarks(city)
        return SurveyState("playing", SURVEY_SECONDS, (), 0)

    def step(self, city: City, state: SurveyState, player: Player, actions: Actions,
             sightings: tuple[Sighting, ...], dt: float) -> GameResult:
        if not _finite(dt) or dt < 0:
            raise ValueError("dt must be finite nonnegative seconds")
        if state.phase in ("won", "lost"):
            return GameResult(state, ())
        if state.phase != "playing":
            raise ValueError("unknown survey phase")
        landmarks = _landmarks(city)
        photos = _records(state, landmarks)
        remaining = max(0.0, state.remaining_s - dt)
        if remaining == 0:
            return GameResult(SurveyState("lost", 0.0, state.photos, state.score),
                              ("Survey closed — time expired. R: restart; N: new city.",))
        messages = []
        before_count = len(photos)
        if actions.shutter:
            known = [s for s in sightings if s.landmark_id in landmarks]
            eligible = [s for s in known if _rejection(s) is None]
            if eligible:
                # Additional tie-break only handles duplicate records for the
                # SAME id/error (real renderer emits each id once). Prefer a
                # crown consistently, independent of tuple order; award once.
                chosen = min(eligible, key=lambda s: (abs(s.bearing_error),
                             s.landmark_id, not s.crown_visible))
                key = chosen.landmark_id
                award = PHOTO_POINTS + (CROWN_POINTS if chosen.crown_visible else 0)
                old = photos.get(key, 0)
                delta = max(0, award - old)
                photos[key] = max(old, award)
                name = landmarks[key].name
                if delta:
                    label = "composition upgrade" if old else "photo recorded"
                    messages.append(f"{name}: {label}, +{delta} points.")
                else:
                    messages.append(f"{name}: already recorded; no additional points.")
            else:
                finite = [s for s in known if _finite(s.bearing_error)]
                closest = min(finite, key=lambda s: (abs(s.bearing_error), s.landmark_id),
                              default=None)
                reason = _rejection(closest) if closest else "no valid landmark sighting"
                messages.append(f"No photo: {reason}.")
            if before_count < REQUIRED_PHOTOS <= len(photos):
                messages.append("Survey ready — return to depot or risk another view.")
        phase = "playing"
        if actions.interact:
            values = (player.feet.x, player.feet.z, city.depot.x, city.depot.z)
            if not all(_finite(v) for v in values):
                raise ValueError("submission position must be finite")
            distance = math.hypot(player.feet.x-city.depot.x, player.feet.z-city.depot.z)
            if distance > DEPOT_RADIUS_M:
                messages.append("Submission rejected: return within 3 m of the depot and press E.")
            elif len(photos) < REQUIRED_PHOTOS:
                messages.append(f"Submission rejected: {len(photos)}/3 distinct landmarks; keep exploring.")
            else:
                phase = "won"
                messages.append(f"Survey submitted — {len(photos)} landmarks, {sum(photos.values())} points. "
                                "R: restart; N: new city.")
        return GameResult(SurveyState(phase, remaining, tuple(sorted(photos.items())),
                                      sum(photos.values())), tuple(messages))
