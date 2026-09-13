"""Deterministic ground walking; injected Actions/Spatial, never terminal state."""
import math

from .contracts import Actions, MotionResult, Player, Spatial, Vec3

WALK_SPEED = 4.0  # metres/second
TURN_SPEED = math.pi / 2  # radians/second
LOOK_SPEED = math.pi / 3
MAX_PITCH = math.pi / 3
PLAYER_RADIUS = 0.30
MAX_STEP_SECONDS = 0.025  # <= 0.10 m at full walking speed
CONTACT_ITERATIONS = 30  # safe-side bisection error <= 0.10 / 2**30 metres


def _finite(*values):
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in values)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("motion inputs/results must be finite real numbers")


def _yaw(value):
    result = value % math.tau
    return 0.0 if result == math.tau else result


def _pitch(value):
    return max(-MAX_PITCH, min(MAX_PITCH, value))


def _axis(spatial, feet, amount, x_axis):
    if amount == 0:
        return feet, False

    def at(fraction):
        return Vec3(feet.x + amount*fraction if x_axis else feet.x, 0,
                    feet.z if x_axis else feet.z + amount*fraction)

    target = at(1.0)
    if spatial.segment_clear(feet, target, PLAYER_RADIUS):
        return target, False
    # The clear prefix of a straight sweep is monotone even if its endpoint
    # emerges on the far side of an obstacle. Never binary-search walkable().
    low, high = 0.0, 1.0
    for _ in range(CONTACT_ITERATIONS):
        middle = (low + high) / 2
        if spatial.segment_clear(feet, at(middle), PLAYER_RADIUS):
            low = middle
        else:
            high = middle
    return at(low), True


class Walker:
    """Implements Movement; stateless and reusable across players/worlds.

    Spatial.segment_clear is the existing city sweep, now explicit in the
    shared protocol. No duplicate geometry model or concrete peer dependency.
    """

    def spawn(self, spatial: Spatial) -> Player:
        """Return the approved city spawn or fail; never relocate it silently."""
        return self.step(spatial, Player(spatial.city.spawn), Actions(), 0).player

    def step(self, spatial: Spatial, player: Player, actions: Actions,
             dt: float) -> MotionResult:
        _finite(dt, player.feet.x, player.feet.y, player.feet.z,
                player.yaw, player.pitch,
                actions.forward, actions.strafe, actions.turn, actions.look)
        if dt < 0:
            raise ValueError("dt must be nonnegative seconds")
        if any(abs(v) > 1 for v in (actions.forward, actions.strafe,
                                    actions.turn, actions.look)):
            raise ValueError("motion action axes must be in [-1,1]")
        if not spatial.walkable(player.feet, PLAYER_RADIUS):
            raise ValueError("player/spawn must have ground-level disc clearance")

        yaw, pitch = _yaw(player.yaw), _pitch(player.pitch)
        omega = actions.turn * TURN_SPEED
        yaw_delta, pitch_delta = omega * dt, actions.look * LOOK_SPEED * dt
        _finite(yaw_delta, pitch_delta)
        final_yaw, final_pitch = _yaw(yaw + yaw_delta), _pitch(pitch + pitch_delta)
        forward, right = actions.forward, actions.strafe
        scale = max(1.0, math.hypot(forward, right))
        forward, right = forward / scale, right / scale
        feet, blocked = player.feet, False
        if dt and (forward or right):
            count_float = dt / MAX_STEP_SECONDS
            _finite(count_float)
            count = max(1, math.ceil(count_float))
            h = dt / count
            # Exact free-space integral of a constant local velocity rotating
            # at constant yaw rate. Midpoint/sinc avoids subtracting near-equal
            # cosines; repeated free-space calls agree for different frame rates.
            half_angle = omega * h / 2
            sinc = math.sin(half_angle) / half_angle if half_angle else 1.0
            distance = WALK_SPEED * h * sinc
            for i in range(count):
                middle_yaw = _yaw(yaw + omega * ((i + 0.5) * h))
                sy, cy = math.sin(middle_yaw), math.cos(middle_yaw)
                dx = distance * (forward * sy + right * cy)
                dz = distance * (forward * cy - right * sy)
                # Resolve world x first, then z from the updated feet. A blocked
                # normal component is discarded, not converted to extra speed.
                feet, bx = _axis(spatial, feet, dx, True)
                feet, bz = _axis(spatial, feet, dz, False)
                blocked = blocked or bx or bz
        return MotionResult(Player(feet, final_yaw, final_pitch), blocked)
