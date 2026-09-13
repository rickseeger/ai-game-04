"""Street-level rectilinear projection. Metres/radians, x east/y up/z north.

Only stdlib and shared contracts are imported. No rendering or spatial queries.
"""
from dataclasses import dataclass, replace
import math

from .contracts import Camera, Player, Projected, Vec3, Viewport

EYE_HEIGHT = 1.7
MAX_PITCH = math.pi / 3


def _finite(*values):
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in values)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("numeric inputs/results must be finite real numbers")


def _vector(v):
    _finite(v.x, v.y, v.z)


def _dot(a, b):
    return a.x*b.x + a.y*b.y + a.z*b.z


def _pose(camera):
    _vector(camera.eye)
    _finite(camera.yaw, camera.pitch, camera.hfov, camera.near, camera.far)
    if not 0 < camera.hfov < math.pi:
        raise ValueError("horizontal FOV must be strictly between 0 and pi")
    if not 0 < camera.near < camera.far:
        raise ValueError("clip range must satisfy 0 < near < far")
    yaw = camera.yaw % math.tau
    # Tiny negative angles can round modulo tau UP to tau in binary64.
    if yaw == math.tau:
        yaw = 0.0
    return replace(camera, yaw=yaw,
                   pitch=max(-MAX_PITCH, min(MAX_PITCH, camera.pitch)))


def camera_from_player(player: Player, *, hfov: float = Camera.hfov,
                       near: float = Camera.near, far: float = Camera.far) -> Camera:
    """Eye = feet + (0,1.7,0); normalize yaw and clamp pitch, without motion.

    Feet must lie on the approved flat ground y=0. For non-player diagnostic
    poses construct Camera(eye, ...) directly instead.
    """
    _vector(player.feet)
    if player.feet.y != 0:
        raise ValueError("player feet must lie on ground y=0")
    return _pose(Camera(Vec3(player.feet.x, player.feet.y + EYE_HEIGHT, player.feet.z),
                        player.yaw, player.pitch, hfov, near, far))


@dataclass(frozen=True)
class PreparedPerspective:
    """Validated immutable frame geometry; obtain via Perspective.prepare.

    project_unclipped omits SCREEN clipping only; near/far still apply.
    ray_clip_range returns distances from the original eye, not a shifted origin.
    """
    camera: Camera
    viewport: Viewport
    right: Vec3
    up: Vec3
    forward: Vec3
    focal_columns: float
    focal_rows: float
    vfov: float

    def project_unclipped(self, point: Vec3) -> Projected | None:
        _vector(point)
        eye = self.camera.eye
        delta = Vec3(point.x-eye.x, point.y-eye.y, point.z-eye.z)
        _vector(delta)
        x, y, depth = (_dot(delta, axis) for axis in (self.right, self.up, self.forward))
        _finite(x, y, depth)
        if depth < self.camera.near or depth > self.camera.far:
            return None
        column = self.viewport.columns/2 + (x/depth)*self.focal_columns
        row = self.viewport.rows/2 - (y/depth)*self.focal_rows
        _finite(column, row)
        return Projected(column, row, depth)

    def project(self, point: Vec3) -> Projected | None:
        p = self.project_unclipped(point)
        if p is None or not (0 <= p.column < self.viewport.columns and
                             0 <= p.row < self.viewport.rows):
            return None
        return p

    def ray(self, column: int, row: int) -> Vec3:
        if (type(column) is not int or type(row) is not int or
                not 0 <= column < self.viewport.columns or not 0 <= row < self.viewport.rows):
            raise ValueError("ray indices must be integers inside the scene viewport")
        x = (column + 0.5 - self.viewport.columns/2) / self.focal_columns
        y = (self.viewport.rows/2 - row - 0.5) / self.focal_rows
        # Normalize in camera space before rotating: no angular-column sampling
        # and no huge intermediate world vector for wide (but valid) FOVs.
        length = math.hypot(x, y, 1)
        x, y, z = x/length, y/length, 1/length
        r, u, f = self.right, self.up, self.forward
        return Vec3(r.x*x+u.x*y+f.x*z, r.y*x+u.y*y+f.y*z, r.z*x+u.z*y+f.z*z)

    def ray_clip_range(self, column: int, row: int) -> tuple[float, float]:
        """Inclusive [near/cos(theta), far/cos(theta)] in normalized-ray metres."""
        # Camera-space cosine avoids cancellation in world dot products at
        # extreme FOV. ray validates indices, using the exact same cell center.
        self.ray(column, row)
        x = (column + 0.5 - self.viewport.columns/2) / self.focal_columns
        y = (self.viewport.rows/2 - row - 0.5) / self.focal_rows
        scale = math.hypot(x, y, 1)
        return self.camera.near*scale, self.camera.far*scale


class Perspective:
    """Implements the unchanged contracts.Projection protocol.

    Convenience methods prepare on each call. A renderer can prepare once per
    pose/resize and reuse the returned immutable object for all cells/points.
    """

    def prepare(self, camera: Camera, viewport: Viewport) -> PreparedPerspective:
        camera = _pose(camera)
        if (type(viewport.columns) is not int or type(viewport.rows) is not int or
                viewport.columns <= 0 or viewport.rows <= 0):
            raise ValueError("scene dimensions must be positive integers")
        _finite(viewport.columns, viewport.rows, viewport.cell_aspect)
        if viewport.cell_aspect <= 0:
            raise ValueError("cell width/height ratio must be positive")
        try:
            fx = (viewport.columns/2) / math.tan(camera.hfov/2)
            fy = fx * viewport.cell_aspect
            _finite(fx, fy)
            if fx <= 0 or fy <= 0:
                raise ValueError("unrepresentable focal scale")
            half_x, half_y = viewport.columns/2/fx, viewport.rows/2/fy
            _finite(half_x, half_y, camera.far*math.hypot(half_x, half_y, 1))
        except (OverflowError, ZeroDivisionError):
            raise ValueError("unrepresentable projection scale") from None
        sy, cy = math.sin(camera.yaw), math.cos(camera.yaw)
        sp, cp = math.sin(camera.pitch), math.cos(camera.pitch)
        return PreparedPerspective(camera, viewport, Vec3(cy, 0, -sy),
                                   Vec3(-sy*sp, cp, -cy*sp), Vec3(sy*cp, sp, cy*cp),
                                   fx, fy, 2*math.atan(half_y))

    def project(self, point: Vec3, camera: Camera, viewport: Viewport) -> Projected | None:
        return self.prepare(camera, viewport).project(point)

    def ray(self, column: int, row: int, camera: Camera, viewport: Viewport) -> Vec3:
        return self.prepare(camera, viewport).ray(column, row)
