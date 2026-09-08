from plot import *
from partition import *
from merge import optimize_rectangles, merge_greedy, merge_optimal_fast
from lights import layoutLights, actualGaps
import sys
import matplotlib.pyplot as plt
from matplotlib.path import Path


# Example polygon points - this will eventually come from the fdf extractor once they're integrated together and this program stops shitting it's pants
# Every shape in here has to be rectilinear, simple (no holes, no self-touching)
# and wound COUNTER-CLOCKWISE - is_reflex_vertex() in partition.py assumes CCW,
# so a clockwise polygon will have all its reflex vertices flipped and the
# partition will come out garbage.
SHAPES = {
    # 1) Simple rectangle
    "rectangle": [(0,0), (14,0), (14,10), (0,10)],

    # 2) L-shape
    "l-shape": [(0,0), (14,0), (14,4), (6,4), (6,10), (0,10)],

    # 3) U-shape (deep notch from the top, thin arms)
    "u-shape": [(0,0), (14,0), (14,10), (10,10), (10,4), (4,4), (4,10), (0,10)],

    # 4) Notched rectangle (single inward notch, cut into the right edge)
    "notched": [(0,0), (14,0), (14,4), (10,4), (10,6), (14,6), (14,10), (0,10)],

    # 5) Staircase (monotone up-right)
    "staircase": [(0,0), (12,0), (12,3), (9,3), (9,6), (6,6), (6,9), (3,9),
                  (3,12), (0,12)],

    # 6) Corridor with bays (spine at y 4..6, two bays down, one bay up)
    "corridor": [(0,4), (3,4), (3,0), (6,0), (6,4), (10,4), (10,0), (13,0),
                 (13,4), (16,4), (16,6), (10,6), (10,10), (6,10), (6,6), (0,6)],

    # 7) Zigzag notch along top (three notches of differing widths)
    "zigzag": [(0,0), (12,0), (12,8), (10,8), (10,5), (8,5), (8,8), (7,8),
               (7,5), (5,5), (5,8), (4,8), (4,5), (2,5), (2,8), (0,8)],

    # 8) "C" shape (thick frame with one open side, opening to the right)
    "c-shape": [(0,0), (12,0), (12,3), (3,3), (3,9), (12,9), (12,12), (0,12)],

    # 9) Double-notch rectangle (one notch up from the bottom, one down from the top)
    "double-notch": [(0,0), (3,0), (3,4), (6,4), (6,0), (14,0), (14,10),
                     (11,10), (11,6), (8,6), (8,10), (0,10)],

    # 10) "E" shape (three prongs)
    "e-shape": [(0,0), (14,0), (14,2), (6,2), (6,4), (12,4), (12,6),
                (6,6), (6,8), (14,8), (14,10), (0,10)],

    # 11) Box with internal courtyard mouth (concave - the courtyard is joined to
    #     the outside by a narrow mouth, so it stays a hole-free simple polygon)
    "courtyard": [(0,0), (6,0), (6,3), (3,3), (3,9), (11,9), (11,3), (8,3),
                  (8,0), (14,0), (14,12), (0,12)],

    # 12) Complex rectilinear (multiple steps and bays)
    "complex": [(0,0), (5,0), (5,3), (9,3), (9,0), (16,0), (16,5), (13,5),
                (13,8), (16,8), (16,12), (11,12), (11,9), (7,9), (7,12),
                (3,12), (3,7), (0,7)],
}

# Which one to run. Override from the shell with e.g. `python main.py u-shape`.
SHAPE = "rectangle"

# Always renders three figures for one shape - the pipeline stages, not a toggle:
#   1. Partition cuts   - outline + the blue internal cuts the partition works from
#   2. Merged + lights   - outline + green merged-rectangle boundaries + light dots
#   3. Final layout      - outline + light dots only, no rectangle lines at all

# Light layout. Target gap between lights AND from each light to the wall - the
# two are the same number, so there is no separate margin. The actual gap shrinks
# to whatever divides the rectangle evenly, so it never exceeds this.
LIGHT_SPACING = 2.0


def pickShape(argv):
    """Resolve the shape name from argv, falling back to SHAPE."""
    name = argv[1] if len(argv) > 1 else SHAPE
    if name not in SHAPES:
        print(f"Unknown shape {name!r}. Available: {', '.join(SHAPES)}")
        sys.exit(1)
    return name, SHAPES[name]


def _drawOutline(ax, points):
    """Fresh Polygon patch for one ax - an Artist can't be shared across axes."""
    ax.add_patch(createPolygon(points, edgecolor='r', fill=None))


def _drawLights(ax, allLights):
    if allLights:
        xs, ys = zip(*allLights)
        ax.plot(xs, ys, 'o', color='orange', markeredgecolor='k',
                markersize=5, linestyle='none', zorder=5)


def main():
    name, points = pickShape(sys.argv)
    print(f"Shape: {name} ({len(points)} vertices)")

    # NOTE: Path(points, closed=True) OVERWRITES the last vertex with a CLOSEPOLY
    # code instead of appending one, so the final vertex gets silently dropped and
    # the polygon closes on a diagonal. Repeat the first point so CLOSEPOLY has its
    # own slot to eat and the real outline survives.
    polyPath = Path(list(points) + [points[0]], closed=True)
    polySides = cutPolyPath(points)

    # --- Output 1: initial partition - outline + the blue cut lines it works from ---
    ax1 = plotInit(points, xLim=None, yLim=None, title=f"{name} - Partition cuts")
    # ax is purely a drawing sink inside dividePolygon - passing it makes the
    # internal cut lines visible, the returned rectangles are identical either way.
    rectangles = dividePolygon(points, polyPath, polySides,
                               ax=ax1, return_rectangles=True)
    _drawOutline(ax1, points)

    print(f"\nInitial partition: {len(rectangles)} rectangles")

    # Optimize using fast algorithms:
    # - merge_optimal_fast: Fastest, applies multiple merges per iteration (RECOMMENDED)
    # - merge_greedy: Fast, applies one merge per iteration
    # - optimize_rectangles: Slowest, explores full tree (use with caution on large datasets)
    optimized_rectangles = merge_optimal_fast(rectangles, verbose=True)

    print(f"\nFinal result: {len(optimized_rectangles)} rectangles")
    print(f"Reduction: {len(rectangles) - len(optimized_rectangles)} rectangles merged")

    # Print rectangles sorted by area (largest first)
    print("\nRectangles (sorted by area):")
    rect_areas = []
    for (x0, y0), (x1, y1) in optimized_rectangles:
        area = abs(x1 - x0) * abs(y1 - y0)
        width = abs(x1 - x0)
        height = abs(y1 - y0)
        rect_areas.append((area, width, height, (x0, y0), (x1, y1)))

    rect_areas.sort(reverse=True)
    for i, (area, w, h, p0, p1) in enumerate(rect_areas, 1):
        print(f"  {i}. Area: {area:.1f}, Size: {w:.1f}x{h:.1f}, From {p0} to {p1}")

    allLights, perRect = layoutLights(optimized_rectangles, LIGHT_SPACING)
    print(f"\nLights (target gap {LIGHT_SPACING}, walls included): "
          f"{len(allLights)} total")
    for i, (rect, pts) in enumerate(zip(optimized_rectangles, perRect), 1):
        gx, gy = actualGaps(rect, pts)
        print(f"  rect {i}: {len(pts):3d} lights, gap {gx:.2f} x {gy:.2f}")

    # --- Output 2: merged rectangles + lights (green rectangle boundaries) ---
    ax2 = plotInit(points, xLim=None, yLim=None, title=f"{name} - Merged + lights")
    for (x0, y0), (x1, y1) in optimized_rectangles:
        ax2.add_patch(plt.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            fill=False, edgecolor='g', linestyle='-', linewidth=1.5
        ))
    _drawOutline(ax2, points)
    _drawLights(ax2, allLights)  # lights last so they sit above the rectangles

    # --- Output 3: final layout - outline and lights only, no rectangle lines ---
    ax3 = plotInit(points, xLim=None, yLim=None, title=f"{name} - Final layout")
    _drawOutline(ax3, points)
    _drawLights(ax3, allLights)

    plt.show()


if __name__ == "__main__":
    main()