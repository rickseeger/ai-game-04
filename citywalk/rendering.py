"""Opaque per-cell city rays, lighting and atmospheric perspective; no terminal I/O.

Inject the validated Projection; only shared contracts are required. Optional
Projection.prepare is used when available. One ray-geometry cache, no frame cache.
"""
from dataclasses import replace
import math

from .contracts import (Appearance, Camera, Cell, Frame, Projection, RayHit,
                        Sighting, Spatial, Vec3, Viewport)

FOG_RGB = (24, 30, 53)
CLIP_EPS_M = 1e-8
_FACE_LIGHT = {"south": 1.05, "west": .72, "north": .80,
               "east": .95, "roof": 1.12, "ground": .90}


def _along(origin, direction, distance):
    return Vec3(origin.x+direction.x*distance, origin.y+direction.y*distance,
                origin.z+direction.z*distance)


def _forward(camera):
    cp = math.cos(camera.pitch)
    return Vec3(math.sin(camera.yaw)*cp, math.sin(camera.pitch), math.cos(camera.yaw)*cp)


def _dot(a, b):
    return a.x*b.x+a.y*b.y+a.z*b.z


def _pose(camera):
    # Same public pose convention as Projection; no new lens/scale defaults.
    return replace(camera, yaw=camera.yaw % math.tau,
                   pitch=max(-math.pi/3, min(math.pi/3, camera.pitch)))


def _sky(direction):
    # World-elevation gradient moves with pitch. No invented skyline or stars.
    haze = math.exp(-max(0, direction.y)*5)
    rgb = tuple(round(a+(b-a)*haze) for a, b in zip((9, 12, 30), FOG_RGB))
    return Cell(" ", rgb, rgb)


def shade(cell: Cell, hit: RayHit) -> Cell:
    """Preserve local palette; compass lighting and eye-relative distance fog.

    Bright material foregrounds retain illumination without a new emissive field.
    Distant fine glyphs fade into coherent colored planes, not random dithering.
    """
    light = _FACE_LIGHT[hit.face]
    transmission = math.exp(-max(0, hit.distance-12)/145)
    glow = max(light, .98) if max(cell.fg) >= 190 else light
    def color(rgb, factor):
        return tuple(max(0, min(255, round(fog+(value*factor-fog)*transmission)))
                     for value, fog in zip(rgb, FOG_RGB))
    fg, bg = color(cell.fg, glow), color(cell.bg, light)
    glyph = cell.glyph
    if hit.building_id is None:
        # Fine paving is below cell resolution at distance; fade rather than
        # turning sparse aliased joints into bright horizontal noise.
        fade = min(1, 18/max(18, hit.distance))
        fg = tuple(round(b+(f-b)*fade) for f, b in zip(fg, bg))
        if hit.distance > 40:
            glyph = "."
    elif hit.distance > 190:
        glyph = "."
    elif hit.distance > 110 and glyph not in "|=-":
        glyph = ":"
    return Cell(glyph, fg, bg)


class CityRenderer:
    """Renderer protocol implementation; reuse with one injected Projection.

    A single cell-center sample defines both opaque color and depth. Near/far
    are inclusive forward-depth planes, within CLIP_EPS_M ray-distance roundoff.
    Near clipping exposes the next surface (including an inside-box exit), not
    a fabricated cap. Scene size contains no implicit HUD rows.
    """

    def __init__(self, projection: Projection):
        self.projection = projection
        self._key = None
        self._rays = ()
        self._lens_key = None
        self._clips = ()

    def _geometry(self, camera, viewport):
        key = (camera, viewport)
        if key == self._key:
            return self._rays
        prepare = getattr(self.projection, "prepare", None)
        prepared = prepare(camera, viewport) if prepare is not None else None
        pose = prepared.camera if prepared is not None else _pose(camera)
        forward = _forward(pose)
        if prepared is not None:
            lens_key = (viewport, pose.hfov, pose.near, pose.far)
            if lens_key != self._lens_key:
                # Clip distances depend on lens/cell only, never position or
                # orientation. Avoid duplicate ray construction on every turn.
                self._clips = tuple(prepared.ray_clip_range(column, row)
                                    for row in range(viewport.rows)
                                    for column in range(viewport.columns))
                self._lens_key = lens_key
        rays = []
        for row in range(viewport.rows):
            for column in range(viewport.columns):
                direction = (prepared.ray(column, row) if prepared is not None else
                             self.projection.ray(column, row, camera, viewport))
                if prepared is not None:
                    near, far = self._clips[row*viewport.columns+column]
                else:
                    cosine = _dot(direction, forward)
                    near, far = pose.near/cosine, pose.far/cosine
                shift = max(0, near-CLIP_EPS_M)
                rays.append((direction, _along(pose.eye, direction, shift),
                             shift, near, far, _sky(direction)))
        if not rays:
            raise ValueError("scene dimensions must be positive")
        self._key, self._rays = key, tuple(rays)
        return self._rays

    def render(self, spatial: Spatial, appearance: Appearance, camera: Camera,
               viewport: Viewport) -> Frame:
        cells, depths = [], []
        raycast, sample = spatial.raycast, appearance.sample
        city = spatial.city
        for direction, origin, shift, near, far, sky in self._geometry(camera, viewport):
            hit = raycast(origin, direction, far-shift+CLIP_EPS_M)
            if hit is None:
                cells.append(sky)
                depths.append(math.inf)
                continue
            distance = hit.distance+shift
            if not near-CLIP_EPS_M <= distance <= far+CLIP_EPS_M:
                raise ValueError("Spatial returned a hit outside the requested interval")
            hit = RayHit(distance, hit.point, hit.normal, hit.face, hit.building_id)
            cells.append(shade(sample(city, hit), hit))
            depths.append(distance)
        return Frame(viewport.columns, viewport.rows, tuple(cells), tuple(depths))

    def sightings(self, spatial: Spatial, camera: Camera,
                  viewport: Viewport) -> tuple[Sighting, ...]:
        prepare = getattr(self.projection, "prepare", None)
        prepared = prepare(camera, viewport) if prepare is not None else None
        pose = prepared.camera if prepared is not None else _pose(camera)
        project = (prepared.project if prepared is not None else
                   lambda point: self.projection.project(point, camera, viewport))
        buildings = {b.id: b for b in spatial.city.buildings}
        def visible(point, building_id, surface_target):
            if project(point) is None:
                return False
            delta = Vec3(point.x-pose.eye.x, point.y-pose.eye.y, point.z-pose.eye.z)
            distance = math.hypot(delta.x, delta.y, delta.z)
            if distance == 0:
                return False
            direction = Vec3(delta.x/distance, delta.y/distance, delta.z/distance)
            # Eye-origin ray, deliberately NOT near-clipped: foreground solids
            # still block photography even if the rendering near plane cuts them.
            hit = spatial.raycast(pose.eye, direction, distance+CLIP_EPS_M)
            return (hit is not None and hit.building_id == building_id and
                    (not surface_target or abs(hit.distance-distance) <= .05))
        result = []
        for landmark in sorted(spatial.city.landmarks, key=lambda item: item.id):
            b = buildings[landmark.building_id]
            r = b.footprint
            crown = Vec3((r.xmin+r.xmax)/2, b.height-1, (r.zmin+r.zmax)/2)
            dx, dz = landmark.target.x-pose.eye.x, landmark.target.z-pose.eye.z
            error = (math.atan2(dx, dz)-pose.yaw+math.pi) % math.tau-math.pi
            result.append(Sighting(landmark.id, visible(landmark.target, b.id, True),
                                   math.hypot(dx, dz), error, visible(crown, b.id, False)))
        return tuple(result)
