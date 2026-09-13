# Appearance v1 - node 3 handoff

Implements the approved `FacadeAppearance.sample(city, hit) -> Cell` interface
on top of node 2 commit `2b310eb387f7e8d086151e20dd28d587d6f3feaa`.
`contracts.py`, `spatial.py`, foundation CLI and existing tests are unchanged.
No competing city generator, projection, renderer, motion, input or game rules.

## Renderer consumption

    from citywalk.appearance import FacadeAppearance, SKY_RGB
    from citywalk.contracts import Vec3
    from citywalk.spatial import CityGenerator
    spatial = CityGenerator().generate(11)
    appearance = FacadeAppearance()  # reuse per renderer, not per pixel
    hit = spatial.raycast(Vec3(0, 1.7, 0), Vec3(0, 0, 1), 500)
    if hit is not None:
        local_cell = appearance.sample(spatial.city, hit)

Only the existing frozen City, Building, Landmark and RayHit values are needed.
The appearance module imports contracts and stdlib only. City.buildings supplies
style/material_seed; City.landmarks membership identifies landmarks (not names,
ID prefixes or an assumed index). Ordinary buildings retain the spatial nodes
nearest-district assignment. Unknown custom styles use a neutral indigo/amber
fallback; unknown building IDs raise ValueError rather than camouflage a broken
spatial/rendering connection. No building ID is valid only for ground. Bad faces
and nonfinite material coordinates raise ValueError. Otherwise hits are trusted
surface points from Spatial, not re-raycast or checked for footprint containment.
Underside hits with ground face plus building ID receive a plain base material.

Reuse one FacadeAppearance per render worker. It indexes the last immutable City
by identity, O(buildings) on change and O(1) lookup thereafter. This avoids both
per-cell linear scans and stale IDs when restarting with the same seed and a new
City. No unbounded global cache, global RNG, time, filesystem or terminal access.
Use separate instances for concurrent threads (cache is deliberately not locked).

Cell contains a single printable ASCII glyph and integer RGB fg/bg tuples. These
are LOCAL MATERIAL colors, not ANSI strings or pre-lit display pixels. Face
chooses UV axes; normal and distance do not change material. Renderer owns face
lighting, distance fog, sky on ray miss, clipping, projection, occlusion, sampling
rate and eventual alias control. SKY_RGB=(12,16,38) is an optional palette anchor,
not a sky geometry implementation. There is no new emissive field: window/accent
colors suggest illumination, but renderer must choose how to preserve their
contrast when applying lighting without silently changing Cell contracts.

## Metres and architectural rules

x east, y up, z north, unchanged. North/south use u=x-footprint.xmin;
east/west use u=z-footprint.zmin. Both opposing faces follow the positive world
axis, not mirrored screen orientation. Floors use y from ground at a fixed 3 m
cadence (never normalized by tower height). Roof and ground use x/z. Styles are
attached to building footprints, so different hit distances and sample ordering
do not move the patterns. Geometry translations preserve facade rhythm.

A specified integer mixer, masked to 64 bits, derives a single building tint
(-8,-4,0,+4,+8 RGB channels), nominal bay (2.5/3/3.5 m) and glazing variant.
Fit an integer count of equal complete bays across each face, by rounding
span/nominal to nearest integer (half upward). Generated spans >=9 m yield
2-4 m bays; tiny custom buildings use at least one bay and do not promise the
human-scale limits of generated buildings. Tint is building-wide, not per pixel.
Window occupancy is keyed only by material_seed, face, floor and bay; about
three of seven panes light up, with no per-frame or subpane random speckle.

Corners have 0.35 m vertical trim. Storey lines occupy first 0.18 m of each 3 m
floor. Upper-floor glazing spans y%3 in [0.8,2.35), width 44/52/64 percent of a
bay depending on the building. Glass, deco and metal add narrow vertical ribs.
Ground floors remain masonry with one centered decorative entry on every face:
1.6 m wide, y in [0.1,2.1), central mullion, lintel y [2.1,2.35), cyan sign at
[2.5,2.85), stone plinth below 0.45 m. Entries are MATERIAL MARKS, not walkable
openings; solid footprints/collision are not changed.

Actual height anchors the top 0.45 m cornice. Roof perimeter trim is 0.55 m;
ordinary roofs have dark planes and 3 m world-grid seams. Landmark crowns use
the upper 6 m and patterned roof materials, not extra geometry or fake setbacks.
Ground is a quiet indigo paving plane: 2 m joints with a 6 m accent repeat,
including negative coordinates. A 0.6 m edge stripe marks the existing city
bounds. It is not a rail, sidewalk classifier or complete boundary presentation.
The shared City intentionally contains no PublicSpace material regions; this
module does not reconstruct another set of roads or depend on concrete SpatialWorld
metadata. A future spatial/renderer handoff is needed for distinct plaza/asphalt
regions or geometric boundary rails.

## Palette and recognizable landmarks

Palette values are immutable and inspectable in PALETTES and atlas.json.
Dark blue/indigo recesses unify colored masses; amber windows and restrained
cyan signs contrast with the wall rather than fill it with random bright cells.

| Existing style | District | Wall family | Landmark treatment |
| --- | --- | --- | --- |
| amber-brick | Foundry | muted amber/rose brick | Amber Spire: continuous central rib, gold/cyan fin crown |
| cyan-glass | Harbor | blue/cyan glass | Tidal Beacon: turquoise wave belt at midheight, horizontal crown |
| violet-artdeco | Civic | violet stone and pale trim | Violet Clock: 5.6 m fixed clock rim/hands at aim height, diagonal deco crown |
| rose-stone | Old Quarter | rose stone | Rose Lantern: diamond lantern badge, star/plus crown |
| emerald-metal | Gardens | sparse emerald/teal metal | Emerald Crown: chevron badge and alternating leaf/fin crown |

Ordinary buildings differ in tint, bay cadence, glazing proportions and occupancy
within those families. Landmark badges are centered at half-height on each wall
and fixed in metres; the clock is decorative and does not track gameplay time.
All silhouettes/height variation remain those supplied by spatial generation.
These are recognizable material motifs, not proof of recognition in perspective.

## Reproducible component fixtures

    python3 tools/preview_appearance.py --seed 11
    python3 tools/preview_appearance.py --seed 11 --check
    python3 -m unittest discover -s tests -v
    python3 tools/build.py
    python3 dist/lantern-survey.pyz --smoke --seed 11

Windows with Python 3.11+: replace python3 with py -3. No packages required.
For another seed use --seed 93 --output <scratch-directory>; the committed
regression atlas intentionally stays seed 11. --check compares all three files
byte for byte without writing, and fails if any are missing or stale.

Open `docs/appearance-fixtures/atlas.html` in a browser for real sampled RGB
swatches. `atlas.txt` has the same glyph rows, without colors. `atlas.json`
is the machine fixture: full selected Building records (footprints, heights,
styles, material seeds), Landmark metadata, palette values and a deduplicated
Cell table. Every panel stores face, origin, column_step and row_step in metres:
point = origin + column*column_step + row*row_step. Cell rows index cell_table.
No camera position or invented screenshot is implied by these sample planes.

The tool selects the first ordinary building in stable city order per style
and its district landmark. Full south elevations sample every 0.5 m horizontally
and 1 m vertically at floor offsets near 0.1,1.1,2.1 m. This coarse view misses
some thin details; entry panels sample 0.25 m and roofline strips sample 0.25 m
vertically, including the top cornice. Roof plans use 0.5 m steps. Landmark
emblems have 0.25 m closeups. Two world-ground panels cover depot paving and the
eastern bounds. Every chosen coordinate is recorded, not reconstructed by eye.
The HTML uses fixed-width text and per-Cell CSS, no external assets or scripting.
It is a material atlas, with differing panel sample aspect ratios, not a 3D
renderer. All outputs prominently say COMPONENT PREVIEW ONLY.

## Validation and limitations

`docs/appearance-run.json` captures commands, exit codes, stdout/stderr, platform,
source hashes and observed fixture statistics. Tests pin the canonical atlas
hash, regenerate all output, and test determinism in fresh processes with
PYTHONHASHSEED=1 and 917. Seeds 11,93,2026,-1 cover valid colors/glyphs for every
building and face. Physical probes verify floor spacing, fitted bay width,
window height, door height, cornice position, corner continuity, coherent pane
occupancy, building/district variation and all five distinct landmark crowns.
They also exercise real SpatialWorld ray hits on all faces and every generated
landmark target for seeds 11,93,2026. Original geometry goldens remain unchanged.

Only local Linux/Python execution is evidenced. The zipapp smoke remains the
honest informational foundation; it is not a city/game integration test. No
Windows runtime, perspective quality, frame-rate guarantee, terminal rendering,
anti-aliasing, complete boundary affordance, beauty or gameplay enjoyment is
validated here. No human decision is needed to consume this interface; renderer
and independent play/visual gates remain with their designated later nodes.
