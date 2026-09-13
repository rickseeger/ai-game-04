"""Renderer-independent metre-scale city, static queries and route witnesses.

Shared contracts remain unchanged. Geometry is closed; player contact blocks.
No camera projection, movement, rendering, terminal or gameplay dependencies.
"""
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import permutations
import math

from .contracts import Building, City, Landmark, RayHit, Rect, Vec3

EPS = 1e-6
PLAYER_RADIUS = 0.30
EYE_HEIGHT = 1.7
GRID_SIZE = 24.0


def _finite(*values):
    if not all(math.isfinite(v) for v in values):
        raise ValueError("coordinates and distances must be finite")


def _rect(r):
    _finite(r.xmin, r.zmin, r.xmax, r.zmax)
    if r.xmin > r.xmax or r.zmin > r.zmax:
        raise ValueError("inverted rectangle")


def _overlap(a, b):
    return (a.xmin <= b.xmax and a.xmax >= b.xmin and
            a.zmin <= b.zmax and a.zmax >= b.zmin)


def _point_rect_sq(x, z, r):
    return max(r.xmin - x, 0, x - r.xmax)**2 + max(r.zmin - z, 0, z - r.zmax)**2


def _point_segment_sq(x, z, a, b):
    dx, dz = b.x - a.x, b.z - a.z
    length_sq = dx*dx + dz*dz
    t = 0 if length_sq == 0 else max(0, min(1, ((x-a.x)*dx + (z-a.z)*dz)/length_sq))
    return (x-a.x-t*dx)**2 + (z-a.z-t*dz)**2


def _segment_rect_sq(a, b, r):
    # Segment/AABB interval test, then minimum among endpoint/edge distances.
    enter, leave = 0.0, 1.0
    for p, d, low, high in ((a.x, b.x-a.x, r.xmin, r.xmax),
                            (a.z, b.z-a.z, r.zmin, r.zmax)):
        if d == 0:
            if not low <= p <= high:
                break
        else:
            t0, t1 = sorted(((low-p)/d, (high-p)/d))
            enter, leave = max(enter, t0), min(leave, t1)
            if enter > leave:
                break
    else:
        return 0.0
    return min(_point_rect_sq(a.x, a.z, r), _point_rect_sq(b.x, b.z, r),
               *(_point_segment_sq(x, z, a, b)
                 for x in (r.xmin, r.xmax) for z in (r.zmin, r.zmax)))


_NORMALS = {"west": Vec3(-1, 0, 0), "east": Vec3(1, 0, 0),
            "south": Vec3(0, 0, -1), "north": Vec3(0, 0, 1),
            "ground": Vec3(0, -1, 0), "roof": Vec3(0, 1, 0)}


def _box_hit(building, origin, direction, limit):
    r = building.footprint
    enter, leave = -math.inf, math.inf
    enter_face, leave_face = "", ""
    for p, d, low, high, low_face, high_face in (
            (origin.x, direction.x, r.xmin, r.xmax, "west", "east"),
            (origin.y, direction.y, 0, building.height, "ground", "roof"),
            (origin.z, direction.z, r.zmin, r.zmax, "south", "north")):
        if d == 0:
            if not low <= p <= high:
                return None
            continue
        t0, t1 = (low-p)/d, (high-p)/d
        f0, f1 = low_face, high_face
        if t0 > t1:
            t0, t1, f0, f1 = t1, t0, f1, f0
        if t0 > enter or (t0 == enter and f0 < enter_face):
            enter, enter_face = t0, f0
        if t1 < leave or (t1 == leave and f1 < leave_face):
            leave, leave_face = t1, f1
        if enter > leave:
            return None
    distance, face = (enter, enter_face) if enter > 0 else (leave, leave_face)
    if not 0 < distance <= limit:
        return None
    return RayHit(distance, Vec3(origin.x+direction.x*distance,
                                origin.y+direction.y*distance,
                                origin.z+direction.z*distance),
                  _NORMALS[face], face, building.id)


def _hit_key(hit):
    return (hit.distance, hit.building_id is not None, hit.building_id or "", hit.face)


@dataclass(frozen=True)
class PublicSpace:
    id: str
    kind: str  # avenue, street, promenade, plaza, lane
    rect: Rect


@dataclass(frozen=True)
class RouteWitness:
    landmark_ids: tuple[str, ...]
    points: tuple[Vec3, ...]  # feet; includes depot at start and finish
    distance_m: float
    walking_seconds: float  # at design speed 4 m/s, not a gameplay run
    positioning_seconds: float = 45.0  # allowance: 15 s for each of three photos


class SpatialWorld:
    """Spatial Protocol implementation with immutable City and 24 m grid index."""

    def __init__(self, city, public_spaces=(), navigation_points=(), navigation_edges=(),
                 destination_nodes=()):
        _rect(city.bounds)
        if city.bounds.xmin == city.bounds.xmax or city.bounds.zmin == city.bounds.zmax:
            raise ValueError("empty city bounds")
        self._city = city
        self.public_spaces = tuple(public_spaces)
        self.navigation_points = tuple(navigation_points)
        self.navigation_edges = tuple(navigation_edges)
        # id -> graph node mapping stored as immutable pairs (depot is node 0).
        self.destination_nodes = tuple(destination_nodes)
        self._grid = {}
        ids = set()
        for b in sorted(city.buildings, key=lambda b: b.id):
            _rect(b.footprint)
            _finite(b.height)
            r, bounds = b.footprint, city.bounds
            if (b.id in ids or not b.id or b.height <= 0 or
                    r.xmin == r.xmax or r.zmin == r.zmax or
                    not (bounds.xmin <= r.xmin < r.xmax <= bounds.xmax and
                         bounds.zmin <= r.zmin < r.zmax <= bounds.zmax)):
                raise ValueError("invalid building geometry or duplicate id")
            ids.add(b.id)
            for key in self._cells(r):
                self._grid.setdefault(key, []).append(b)
        self._grid = {key: tuple(value) for key, value in self._grid.items()}

    @property
    def city(self):
        return self._city

    @staticmethod
    def _cells(r):
        for x in range(math.floor(r.xmin/GRID_SIZE), math.floor(r.xmax/GRID_SIZE)+1):
            for z in range(math.floor(r.zmin/GRID_SIZE), math.floor(r.zmax/GRID_SIZE)+1):
                yield x, z

    def nearby(self, rect):
        _rect(rect)
        bounds = self.city.bounds
        if not _overlap(rect, bounds):
            return ()
        clipped = Rect(max(rect.xmin, bounds.xmin), max(rect.zmin, bounds.zmin),
                       min(rect.xmax, bounds.xmax), min(rect.zmax, bounds.zmax))
        candidates = {b.id: b for key in self._cells(clipped) for b in self._grid.get(key, ())}
        return tuple(candidates[key] for key in sorted(candidates)
                     if _overlap(candidates[key].footprint, rect))

    def _within_bounds(self, feet, radius):
        _finite(feet.x, feet.y, feet.z, radius)
        if radius < 0:
            raise ValueError("radius must be nonnegative")
        r, padding = self.city.bounds, radius + EPS
        return (feet.y == 0 and r.xmin+padding < feet.x < r.xmax-padding and
                r.zmin+padding < feet.z < r.zmax-padding)

    def walkable(self, feet, radius):
        if not self._within_bounds(feet, radius):
            return False
        padding = radius + EPS
        query = Rect(feet.x-padding, feet.z-padding, feet.x+padding, feet.z+padding)
        return all(_point_rect_sq(feet.x, feet.z, b.footprint) > padding**2
                   for b in self.nearby(query))

    def segment_clear(self, start, end, radius=PLAYER_RADIUS):
        """Exact static closed-disc sweep, NOT a movement/wall-slide implementation."""
        start_valid = self._within_bounds(start, radius)
        end_valid = self._within_bounds(end, radius)
        if not start_valid or not end_valid:
            return False
        padding = radius + EPS
        r = Rect(min(start.x, end.x)-padding, min(start.z, end.z)-padding,
                 max(start.x, end.x)+padding, max(start.z, end.z)+padding)
        return all(_segment_rect_sq(start, end, b.footprint) > padding**2
                   for b in self.nearby(r))

    def raycast(self, origin, direction, max_distance):
        _finite(origin.x, origin.y, origin.z, direction.x, direction.y, direction.z, max_distance)
        if max_distance <= 0 or abs(math.hypot(direction.x, direction.y, direction.z)-1) > 1e-6:
            raise ValueError("ray requires unit direction and positive max_distance")
        best = None
        if direction.y != 0:
            distance = -origin.y/direction.y
            if 0 < distance <= max_distance:
                point = Vec3(origin.x+distance*direction.x, 0, origin.z+distance*direction.z)
                b = self.city.bounds
                if b.xmin <= point.x <= b.xmax and b.zmin <= point.z <= b.zmax:
                    best = RayHit(distance, point, Vec3(0, 1, 0), "ground", None)
        # Clip projected ray to finite city before DDA. Bounds themselves are not ray walls.
        start, stop = 0.0, max_distance
        b = self.city.bounds
        for p, d, low, high in ((origin.x, direction.x, b.xmin, b.xmax),
                                (origin.z, direction.z, b.zmin, b.zmax)):
            if d == 0:
                if not low <= p <= high:
                    return best
            else:
                t0, t1 = sorted(((low-p)/d, (high-p)/d))
                start, stop = max(start, t0), min(stop, t1)
                if start > stop:
                    return best
        x, z = origin.x+direction.x*start, origin.z+direction.z*start
        ix, iz = math.floor(x/GRID_SIZE), math.floor(z/GRID_SIZE)
        sx = 1 if direction.x > 0 else -1
        sz = 1 if direction.z > 0 else -1
        tx = (((ix+(sx > 0))*GRID_SIZE-origin.x)/direction.x
              if direction.x else math.inf)
        tz = (((iz+(sz > 0))*GRID_SIZE-origin.z)/direction.z
              if direction.z else math.inf)
        dx = GRID_SIZE/abs(direction.x) if direction.x else math.inf
        dz = GRID_SIZE/abs(direction.z) if direction.z else math.inf
        seen = set()
        while start <= stop:
            for building in self._grid.get((ix, iz), ()):
                if building.id in seen:
                    continue
                seen.add(building.id)
                hit = _box_hit(building, origin, direction, max_distance)
                if hit is not None and (best is None or _hit_key(hit) < _hit_key(best)):
                    best = hit
            crossing = min(tx, tz)
            # Visit equal-distance cells too: closed faces and stable ray ties.
            if crossing > stop or (best is not None and crossing > best.distance):
                break
            if math.isinf(crossing):
                break
            # Equal crossings step one axis at a time. Closed indexing includes
            # every corner-touching box in the diagonal cell as well.
            if tx <= tz:
                ix, tx = ix+sx, tx+dx
            else:
                iz, tz = iz+sz, tz+dz
            start = crossing
        return best

    def path_to(self, landmark_id):
        """Depot-to-viewpoint graph route, all points at feet height."""
        return self._path(0, dict(self.destination_nodes)[landmark_id])

    def _path(self, source, target):
        graph = [[] for _ in self.navigation_points]
        for a, b in self.navigation_edges:
            pa, pb = self.navigation_points[a], self.navigation_points[b]
            length = math.hypot(pa.x-pb.x, pa.z-pb.z)
            graph[a].append((b, length))
            graph[b].append((a, length))
        queue, distance, previous = [(0.0, source)], {source: 0.0}, {}
        while queue:
            cost, node = heappop(queue)
            if cost != distance[node]:
                continue
            if node == target:
                nodes = [node]
                while node != source:
                    node = previous[node]
                    nodes.append(node)
                return tuple(self.navigation_points[n] for n in reversed(nodes))
            for neighbor, length in graph[node]:
                candidate = cost+length
                if candidate < distance.get(neighbor, math.inf):
                    distance[neighbor], previous[neighbor] = candidate, node
                    heappush(queue, (candidate, neighbor))
        raise ValueError("no route to destination")

    def survey_route(self):
        """Shortest graph tour of three distinct viewpoints and depot (geometry only)."""
        destinations = dict(self.destination_nodes)
        ids = tuple(sorted(destinations))
        if len(ids) < 3:
            raise ValueError("three destinations required")
        nodes = (0,) + tuple(destinations[key] for key in ids)
        paths = {(a, b): self._path(a, b) for a in nodes for b in nodes if a != b}
        lengths = {key: path_length(value) for key, value in paths.items()}
        best = None
        for visit in permutations(ids, 3):
            sequence = (0,) + tuple(destinations[key] for key in visit) + (0,)
            pairs = tuple(zip(sequence, sequence[1:]))
            length = sum(lengths[pair] for pair in pairs)
            candidate = (length, visit, pairs)
            if best is None or candidate < best:
                best = candidate
        length, visit, pairs = best
        points = paths[pairs[0]] + tuple(p for pair in pairs[1:] for p in paths[pair][1:])
        return RouteWitness(visit, points, length, length/4.0)


def path_length(points):
    return sum(math.hypot(a.x-b.x, a.z-b.z) for a, b in zip(points, points[1:]))


class _Random:
    """Specified SplitMix64 stream: no hash(), global RNG, or runtime-dependent sampling."""
    MASK = (1 << 64)-1

    def __init__(self, seed):
        self.state = seed & self.MASK

    def integer(self, low, high):
        self.state = (self.state + 0x9E3779B97F4A7C15) & self.MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self.MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self.MASK
        z ^= z >> 31
        return low + z % (high-low+1)


class CityGenerator:
    """Generation v1, 480 m square / ten blocks per axis / five plaza landmarks."""

    def generate(self, seed):
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        rng = _Random(seed)
        lines = (-231.0,) + tuple(float(-240+48*i) for i in range(1, 10)) + (231.0,)
        xhalf = (9,) + tuple(rng.integer(6, 9) for _ in range(9)) + (9,)
        zhalf = (9,) + tuple(rng.integer(6, 9) for _ in range(9)) + (9,)
        sites = ((2, 2), (7, 2), (4, 5), (2, 7), (7, 7))
        plazas = {(i, j-1) for i, j in sites} | {(0, 4), (8, 8), (5, 0)}
        names = ("Amber Spire", "Tidal Beacon", "Violet Clock", "Rose Lantern", "Emerald Crown")
        districts = ("Foundry", "Harbor", "Civic", "Old Quarter", "Gardens")
        styles = ("amber-brick", "cyan-glass", "violet-artdeco", "rose-stone", "emerald-metal")
        buildings, landmarks, spaces = [], [], []
        for axis, halves in (("x", xhalf), ("z", zhalf)):
            for i, (line, half) in enumerate(zip(lines, halves)):
                rect = (Rect(line-half, -240, line+half, 240) if axis == "x" else
                        Rect(-240, line-half, 240, line+half))
                kind = "promenade" if i in (0, 10) else "avenue" if half >= 8 else "street"
                spaces.append(PublicSpace(f"{axis}-road-{i:02}", kind, rect))
        for j in range(10):
            for i in range(10):
                lot = Rect(lines[i]+xhalf[i]+2, lines[j]+zhalf[j]+2,
                           lines[i+1]-xhalf[i+1]-2, lines[j+1]-zhalf[j+1]-2)
                if (i, j) in plazas:
                    spaces.append(PublicSpace(f"plaza-{i}-{j}", "plaza", lot))
                    continue
                if (i, j) in sites:
                    k = sites.index((i, j))
                    inset = rng.integer(0, 2)
                    r = Rect(lot.xmin+inset, lot.zmin+inset, lot.xmax-inset, lot.zmax-inset)
                    b = Building(f"landmark-{k}", r, float(rng.integer(84, 120)), styles[k],
                                 rng.integer(0, (1 << 32)-1))
                    buildings.append(b)
                    target = Vec3((r.xmin+r.xmax)/2, b.height/2, r.zmin)
                    eye = Vec3(target.x, EYE_HEIGHT, lines[j-1]+zhalf[j-1]+3)
                    pitch = math.atan2(target.y-eye.y, target.z-eye.z)
                    landmarks.append(Landmark(f"sight-{k}", b.id, names[k], districts[k],
                                              target, eye, 0.0, pitch))
                    continue
                # Split variable-size lots around a genuinely walkable 6 m lane.
                xs, zs = [(lot.xmin, lot.xmax)], [(lot.zmin, lot.zmax)]
                mode = rng.integer(0, 3)
                if mode & 1 and lot.xmax-lot.xmin >= 26:
                    middle = (lot.xmin+lot.xmax)/2 + rng.integer(-1, 1)
                    xs = [(lot.xmin, middle-3), (middle+3, lot.xmax)]
                    spaces.append(PublicSpace(f"lane-x-{i}-{j}", "lane",
                                             Rect(middle-3, lot.zmin, middle+3, lot.zmax)))
                if mode & 2 and lot.zmax-lot.zmin >= 26:
                    middle = (lot.zmin+lot.zmax)/2 + rng.integer(-1, 1)
                    zs = [(lot.zmin, middle-3), (middle+3, lot.zmax)]
                    spaces.append(PublicSpace(f"lane-z-{i}-{j}", "lane",
                                             Rect(lot.xmin, middle-3, lot.xmax, middle+3)))
                district = min(range(5), key=lambda k: (sites[k][0]-i)**2+(sites[k][1]-j)**2)
                for a, (xmin, xmax) in enumerate(xs):
                    for b, (zmin, zmax) in enumerate(zs):
                        buildings.append(Building(f"block-{i:02}-{j:02}-{a}-{b}",
                                                  Rect(xmin, zmin, xmax, zmax),
                                                  float(rng.integer(4, 33)*3), styles[district],
                                                  rng.integer(0, (1 << 32)-1)))
        depot = Vec3(0, 0, 0)
        city = City(seed, Rect(-240, -240, 240, 240), tuple(sorted(buildings, key=lambda b: b.id)),
                    tuple(landmarks), depot, depot)
        # Explicit avenue lattice plus safe orthogonal plaza connections.
        points = [depot]
        index = {(5, 5): 0}
        for j, z in enumerate(lines):
            for i, x in enumerate(lines):
                if (i, j) not in index:
                    index[i, j] = len(points)
                    points.append(Vec3(x, 0, z))
        edges = []
        for j in range(11):
            for i in range(11):
                for di, dj in ((1, 0), (0, 1)):
                    if i+di < 11 and j+dj < 11:
                        edges.append((index[i, j], index[i+di, j+dj]))
        destinations = []
        for landmark, (i, j) in zip(landmarks, sites):
            corner, end = len(points), len(points)+1
            points.extend((Vec3(lines[i], 0, landmark.viewpoint.z),
                           Vec3(landmark.viewpoint.x, 0, landmark.viewpoint.z)))
            edges.extend(((index[i, j-1], corner), (corner, end)))
            destinations.append((landmark.id, end))
        return SpatialWorld(city, spaces, points, edges, destinations)
