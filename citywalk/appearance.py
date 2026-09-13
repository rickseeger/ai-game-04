"""World-anchored local materials, appearance v1. No projection, I/O or motion."""
from dataclasses import dataclass
import math
from types import MappingProxyType

from .contracts import Building, Cell, City, RayHit, RGB

FLOOR_M = 3.0
DOOR_HEIGHT_M = 2.1
SKY_RGB: RGB = (12, 16, 38)  # optional renderer background; sample handles hits only


@dataclass(frozen=True)
class Palette:
    district: str
    wall: RGB
    trim: RGB
    window: RGB
    dark: RGB
    accent: RGB
    masonry: str


PALETTES = MappingProxyType({
    "amber-brick": Palette("Foundry", (82, 47, 57), (153, 103, 87),
                           (255, 192, 99), (28, 29, 49), (91, 208, 216), ":"),
    "cyan-glass": Palette("Harbor", (28, 61, 82), (79, 147, 168),
                          (158, 228, 230), (18, 34, 57), (250, 190, 108), "."),
    "violet-artdeco": Palette("Civic", (61, 47, 88), (157, 137, 181),
                              (252, 207, 141), (26, 25, 51), (112, 213, 225), ":"),
    "rose-stone": Palette("Old Quarter", (93, 54, 78), (186, 127, 147),
                          (255, 209, 147), (37, 27, 49), (112, 209, 209), ","),
    "emerald-metal": Palette("Gardens", (29, 65, 63), (95, 151, 133),
                             (246, 209, 127), (19, 35, 46), (108, 227, 173), ";"),
})
NEUTRAL = Palette("Unclassified", (54, 54, 73), (131, 133, 151),
                  (249, 199, 128), (24, 27, 44), (106, 207, 219), ".")
_FACES = ("north", "south", "east", "west", "roof", "ground")


def _mix(seed: int, *coordinates: int) -> int:
    """Specified 64-bit integer mixer, never Python hash or per-sample RNG."""
    mask = (1 << 64) - 1
    value = seed & mask
    for coordinate in coordinates:
        value = (value + (coordinate & mask) + 0x9E3779B97F4A7C15) & mask
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        value ^= value >> 31
    return value


def _tone(rgb: RGB, delta: int) -> RGB:
    return tuple(max(0, min(255, channel + delta)) for channel in rgb)


@dataclass(frozen=True)
class _Material:
    building: Building
    palette: Palette
    wall: RGB
    nominal_bay: float
    variant: int
    landmark: bool


def _material(building: Building, landmark: bool) -> _Material:
    key = _mix(building.material_seed, 71)
    palette = PALETTES.get(building.style, NEUTRAL)
    return _Material(building, palette, _tone(palette.wall, (key % 5 - 2) * 4),
                     (2.5, 3.0, 3.5)[(key >> 8) % 3], (key >> 16) % 3, landmark)


def _bay_width(span: float, nominal: float) -> float:
    # Complete bays fit between footprint corners, not a stretched window texture.
    # Generated spans >=9 m guarantee 2..4 m bays. Small custom boxes get one bay.
    return span / max(1, math.floor(span / nominal + 0.5))


class FacadeAppearance:
    """Implements Appearance.sample(City, RayHit)->Cell without changing City.

    Cache holds only the last immutable City by identity, with O(1) ID lookup.
    One instance per render worker; alternating cities is correct but rebuilds.
    Face selects coordinates; normal/distance are intentionally not lighting inputs.
    """

    def __init__(self):
        self._city = None
        self._materials = {}

    def sample(self, city: City, hit: RayHit) -> Cell:
        if hit.face not in _FACES:
            raise ValueError("unknown surface face")
        p = hit.point
        if not all(math.isfinite(v) for v in (p.x, p.y, p.z)):
            raise ValueError("material coordinates must be finite")
        if hit.building_id is None:
            if hit.face != "ground":
                raise ValueError("only ground can have no building_id")
            return self._ground(city, p.x, p.z)
        if city is not self._city:
            landmarks = {landmark.building_id for landmark in city.landmarks}
            self._materials = {b.id: _material(b, b.id in landmarks) for b in city.buildings}
            self._city = city
        try:
            m = self._materials[hit.building_id]
        except KeyError:
            raise ValueError("unknown building_id: " + hit.building_id) from None
        b, palette = m.building, m.palette
        r = b.footprint
        if hit.face == "ground":  # building underside from below-ground custom rays
            return Cell(".", palette.trim, m.wall)
        if hit.face == "roof":
            edge = min(p.x-r.xmin, r.xmax-p.x, p.z-r.zmin, r.zmax-p.z)
            if edge < 0.55:
                return Cell("=", palette.accent if m.landmark else palette.trim, m.wall)
            if m.landmark:
                return Cell(self._crown_glyph(m, p.x-r.xmin, p.z-r.zmin),
                            palette.accent, palette.dark)
            seam = p.x % 3 < 0.12 or p.z % 3 < 0.12
            return Cell("+" if seam else ".", palette.trim, palette.dark)
        if hit.face in ("north", "south"):
            u, span = p.x-r.xmin, r.xmax-r.xmin
        else:
            u, span = p.z-r.zmin, r.zmax-r.zmin
        y = p.y
        # Shared horizontal bands meet at corners and follow actual building height.
        if b.height-y < 0.45:
            return Cell("=", palette.accent if m.landmark else palette.trim, m.wall)
        if m.landmark and b.height-y < 6:
            return Cell(self._crown_glyph(m, u, b.height-y), palette.accent, palette.dark)
        if min(u, span-u) < 0.35:
            return Cell("|", palette.trim, m.wall)
        center = u-span/2
        if abs(center) < 0.8 and 0.1 <= y < DOOR_HEIGHT_M:
            return Cell("|" if abs(center) < 0.10 else "#", palette.window, palette.dark)
        if abs(center) < 1.1 and DOOR_HEIGHT_M <= y < 2.35:
            return Cell("=", palette.trim, m.wall)
        if abs(center) < 1.6 and 2.5 <= y < 2.85:
            return Cell("-", (104, 218, 225), palette.dark)
        if y < 0.45:
            return Cell("_", palette.trim, m.wall)
        if m.landmark:
            emblem = self._emblem(m, center, y-b.height/2)
            if emblem is not None:
                return emblem
        bay = _bay_width(span, m.nominal_bay)
        column = math.floor(u/bay)
        fraction = (u/bay)-column
        floor = math.floor(y/FLOOR_M)
        level = y-floor*FLOOR_M
        if level < 0.18:
            return Cell("-", palette.trim, m.wall)
        # Glazing remains entire coherent panes; occupancy varies by floor/bay only.
        width = (0.26, 0.32, 0.22)[m.variant]
        if floor >= 1 and abs(fraction-0.5) < width and 0.8 <= level < 2.35:
            lit = _mix(b.material_seed, _FACES.index(hit.face), floor, column) % 7 < 3
            glyph = ("+", "=", "|")[m.variant] if lit else ":"
            return Cell(glyph, palette.window if lit else palette.trim, palette.dark)
        if b.style in ("cyan-glass", "violet-artdeco", "emerald-metal") and fraction < 0.08:
            return Cell("|", palette.trim, m.wall)
        # Quiet walls: material identity and building-wide tint, not pixel noise.
        return Cell(palette.masonry, _tone(m.wall, 16), m.wall)

    @staticmethod
    def _crown_glyph(m: _Material, u: float, v: float) -> str:
        style = m.building.style
        if style == "amber-brick":
            return "|" if u % 3 < 1 else "^"
        if style == "cyan-glass":
            return "~" if v % 2 < 1 else "="
        if style == "violet-artdeco":
            return "/" if u % 4 < 2 else "\\"
        if style == "rose-stone":
            return "*" if u % 3 < 1.5 else "+"
        return "^" if (u+v) % 4 < 2 else "/"

    @staticmethod
    def _emblem(m: _Material, u: float, v: float) -> Cell | None:
        # Fixed metre-sized architectural badges, centered on landmark aim height.
        p, style = m.palette, m.building.style
        glyph = None
        if style == "violet-artdeco":  # clock rim + hands (fixed at 12:15)
            radius = math.hypot(u, v)
            if 2.15 <= radius < 2.8:
                glyph = "O"
            elif radius < 2.15:
                glyph = "|" if abs(u) < .22 and v >= 0 else "-" if abs(v) < .22 and u >= 0 else "."
        elif style == "amber-brick" and abs(u) < 0.6:
            glyph = "|"  # spire rib, full height outside the crown
        elif style == "cyan-glass" and abs(v) < 1.1:
            glyph = "~"  # continuous tidal belt
        elif style == "rose-stone" and abs(u)/2.5+abs(v)/3 < 1:
            glyph = "*" if abs(u) < .4 else "/" if u < 0 else "\\"
        elif style == "emerald-metal" and abs(v-abs(u)*0.6) < .4 and abs(u) < 4:
            glyph = "\\" if u < 0 else "/"
        return None if glyph is None else Cell(glyph, p.accent, p.dark)

    @staticmethod
    def _ground(city: City, x: float, z: float) -> Cell:
        r = city.bounds
        edge = min(x-r.xmin, r.xmax-x, z-r.zmin, r.zmax-z)
        if edge < .6:
            return Cell("=", (111, 176, 187), (31, 45, 64))
        # City has no public-space material field: do not invent road geometry.
        # Metre paving joints plus a sparse 6 m cadence, also at negative coords.
        joint = x % 2 < .08 or z % 2 < .08
        accent = math.floor(x/2) % 3 == 0 and math.floor(z/2) % 3 == 0
        return Cell("+" if joint else ".", (68, 87, 112) if accent else (49, 61, 86),
                    (22, 28, 46))
