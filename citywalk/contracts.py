"""Shared immutable values and structural interfaces. No downstream algorithms."""
from dataclasses import dataclass
from typing import Literal, Protocol

RGB = tuple[int, int, int]
Face = Literal["north", "south", "east", "west", "roof", "ground"]


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Rect:
    xmin: float
    zmin: float
    xmax: float
    zmax: float


@dataclass(frozen=True)
class Building:
    id: str
    footprint: Rect
    height: float
    style: str
    material_seed: int


@dataclass(frozen=True)
class Landmark:
    id: str
    building_id: str
    name: str
    district: str
    target: Vec3
    viewpoint: Vec3  # known valid reachable eye pose; x/z is walking position
    view_yaw: float
    view_pitch: float


@dataclass(frozen=True)
class City:
    seed: int
    bounds: Rect
    buildings: tuple[Building, ...]
    landmarks: tuple[Landmark, ...]
    spawn: Vec3  # feet, y=0
    depot: Vec3  # feet, y=0


@dataclass(frozen=True)
class RayHit:
    distance: float  # metres along normalized ray
    point: Vec3
    normal: Vec3
    face: Face
    building_id: str | None  # None for ground


@dataclass(frozen=True)
class Cell:
    glyph: str  # exactly one printable ASCII character
    fg: RGB
    bg: RGB


@dataclass(frozen=True)
class Camera:
    eye: Vec3
    yaw: float = 0.0
    pitch: float = 0.0
    hfov: float = 1.3962634015954636  # 80 degrees
    near: float = 0.10
    far: float = 500.0


@dataclass(frozen=True)
class Viewport:
    columns: int
    rows: int  # scene rows only, excludes HUD
    cell_aspect: float = 0.5  # character width / height


@dataclass(frozen=True)
class Projected:
    column: float
    row: float
    depth: float  # forward camera-space metres, not ray length


@dataclass(frozen=True)
class Frame:
    columns: int
    rows: int
    cells: tuple[Cell, ...]  # row-major; no embedded ANSI
    depth: tuple[float, ...]  # ray distance; infinity is sky


@dataclass(frozen=True)
class Player:
    feet: Vec3
    yaw: float = 0.0
    pitch: float = 0.0


@dataclass(frozen=True)
class Actions:
    forward: float = 0.0  # [-1,1]
    strafe: float = 0.0  # [-1,1], positive right
    turn: float = 0.0  # [-1,1], positive yaw
    look: float = 0.0  # [-1,1], positive pitch
    shutter: bool = False  # edges, never auto-repeat
    interact: bool = False
    pause: bool = False
    help: bool = False
    restart: bool = False
    new_seed: bool = False
    quit: bool = False


@dataclass(frozen=True)
class MotionResult:
    player: Player
    blocked: bool


@dataclass(frozen=True)
class Sighting:
    landmark_id: str
    visible: bool
    range_m: float
    bearing_error: float  # radians
    crown_visible: bool  # bonus: crown projects in scene and is unoccluded


@dataclass(frozen=True)
class SurveyState:
    phase: Literal["playing", "won", "lost"]
    remaining_s: float
    photos: tuple[tuple[str, int], ...]  # unique landmark id, awarded score
    score: int


@dataclass(frozen=True)
class GameResult:
    state: SurveyState
    messages: tuple[str, ...]


class Spatial(Protocol):
    city: City

    def raycast(self, origin: Vec3, direction: Vec3, max_distance: float) -> RayHit | None:
        """Normalized direction; nearest positive hit on buildings/ground, else None."""
        ...

    def walkable(self, feet: Vec3, radius: float) -> bool:
        """Closed player disc wholly within city bounds and separated from buildings."""
        ...

    def nearby(self, rect: Rect) -> tuple[Building, ...]:
        """All overlapping closed footprints, stable building-id order."""
        ...


class Generator(Protocol):
    def generate(self, seed: int) -> Spatial: ...


class Appearance(Protocol):
    def sample(self, city: City, hit: RayHit) -> Cell:
        """World-anchored deterministic glyph/color; no camera or terminal access."""
        ...


class Projection(Protocol):
    def project(self, point: Vec3, camera: Camera, viewport: Viewport) -> Projected | None: ...
    def ray(self, column: int, row: int, camera: Camera, viewport: Viewport) -> Vec3: ...


class Renderer(Protocol):
    def render(self, spatial: Spatial, appearance: Appearance, camera: Camera,
               viewport: Viewport) -> Frame: ...
    def sightings(self, spatial: Spatial, camera: Camera, viewport: Viewport) -> tuple[Sighting, ...]: ...


class Movement(Protocol):
    def step(self, spatial: Spatial, player: Player, actions: Actions, dt: float) -> MotionResult: ...


class Terminal(Protocol):
    def __enter__(self) -> "Terminal": ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def size(self) -> tuple[int, int]:
        """Actual columns and total rows."""
        ...
    def poll(self, now: float) -> Actions: ...
    def present(self, frame: Frame, hud: tuple[str, ...]) -> None: ...


class Gameplay(Protocol):
    def start(self, city: City) -> SurveyState: ...
    def step(self, city: City, state: SurveyState, player: Player, actions: Actions,
             sightings: tuple[Sighting, ...], dt: float) -> GameResult:
        """Pure rule transition; integration sends only active-play elapsed time."""
        ...
