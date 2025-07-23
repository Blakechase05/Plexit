#!/usr/bin/env python3
"""
dot_filler_with_margin.py
-------------------------
Fill any 2-D shape on a 500 × 500 px canvas with regularly spaced
dots in a square lattice, with a ~10% margin from canvas edges and
polygon edges. Each polygon/lobe gets its own centered grid.

• Supports:
    – Closed polygons (e.g. triangle, irregular area)
    – Open "snake" paths (buffered into corridors)
• Dependencies: numpy, matplotlib, shapely
"""

from typing import List, Tuple
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon, LineString
from shapely.geometry.base import BaseGeometry

# ─────────── CONFIG ───────────
CANVAS_SIZE_PX: int             = 500       # width == height
SPACING_PX: int                 = 50        # grid pitch
DOT_MARKER_SIZE: int            = 4         # matplotlib “markersize”
DOT_COLOR: str                  = "tab:blue"
SHAPE_EDGE_COLOR: str           = "black"

SHAPE_TYPE: str                 = "polygon"     # "polygon" | "snake"

SHAPE_COORDS: List[Tuple[int, int]] = [
    (100, 300),   # Bottom left
    (100, 400),   # Top left
    (250, 400),   # Top middle
    (250, 500),   # Top right
    (400, 500),   # Far top right
    (400, 300),   # Far bottom right
    (250, 300),   # Back down to inner join
    (250, 200),   # Down to inner bottom
    (100, 200)    # Close on far left
]



SNAKE_BUFFER_PX: int            = 15
BORDER_RATIO: float             = 0.01      # 10% canvas/polygon margin
# ──────────────────────────────


# ─────────── HELPERS ──────────
def buildShape(shapeType: str, coords: List[Tuple[int, int]]) -> BaseGeometry:
    """Return a Shapely geometry representing the region to fill."""
    if shapeType.lower() == "polygon":
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]  # Close loop
        return Polygon(coords)
    elif shapeType.lower() == "snake":
        line = LineString(coords)
        return line.buffer(SNAKE_BUFFER_PX)
    else:
        raise ValueError("SHAPE_TYPE must be 'polygon' or 'snake'")


def generateLocalGrid(region: Polygon, spacingPx: int, marginPx: float) -> List[Point]:
    """Generate a grid centered inside a polygon's bounding box with margin."""
    minx, miny, maxx, maxy = region.bounds
    minx += marginPx
    miny += marginPx
    maxx -= marginPx
    maxy -= marginPx

    width = maxx - minx
    height = maxy - miny

    if width <= 0 or height <= 0 or spacingPx <= 0:
        return []

    # Align grid origin to center in bounding box
    x0 = minx + (width % spacingPx) / 2
    y0 = miny + (height % spacingPx) / 2

    try:
        xs = np.arange(x0, maxx, spacingPx)
        ys = np.arange(y0, maxy, spacingPx)
    except ValueError:
        return []

    return [Point(x, y) for x in xs for y in ys]


def filterPointsInRegion(points: List[Point], region: BaseGeometry) -> List[Point]:
    """Return only those grid points that are strictly inside the region."""
    return [p for p in points if region.contains(p)]


# ─────────── MAIN ─────────────
def main() -> None:
    marginPx = CANVAS_SIZE_PX * BORDER_RATIO

    # 1) Build original region
    region = buildShape(SHAPE_TYPE, SHAPE_COORDS)

    # 2) Shrink region to avoid placing dots near edges
    insetRegion = region.buffer(-marginPx)

    # 3) Handle single or multi-part geometries
    subRegions = getattr(insetRegion, "geoms", [insetRegion])
    insidePts: List[Point] = []

    for sub in subRegions:
        localGrid = generateLocalGrid(sub, SPACING_PX, 0)  # 0 because margin is already buffered
        filtered = filterPointsInRegion(localGrid, sub)
        insidePts.extend(filtered)

    # 4) Plot result
    fig, ax = plt.subplots()
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(0, CANVAS_SIZE_PX)
    ax.set_ylim(0, CANVAS_SIZE_PX)

    # Draw original shape
    xShape, yShape = zip(*SHAPE_COORDS)
    if SHAPE_TYPE == "polygon":
        ax.plot(xShape + (xShape[0],), yShape + (yShape[0],), color=SHAPE_EDGE_COLOR)
    else:  # snake
        ax.plot(xShape, yShape, color=SHAPE_EDGE_COLOR, linestyle="--")
        xs, ys = region.exterior.xy
        ax.plot(xs, ys, color=SHAPE_EDGE_COLOR, alpha=0.3)

    # Draw inset boundary for debug
    for sub in subRegions:
        xs, ys = sub.exterior.xy
        ax.plot(xs, ys, color='grey', linestyle=':', alpha=0.5)

    # Draw dots
    ax.plot(
        [p.x for p in insidePts],
        [p.y for p in insidePts],
        linestyle="",
        marker="o",
        markersize=DOT_MARKER_SIZE,
        color=DOT_COLOR,
    )

    ax.invert_yaxis()
    ax.set_title(
        f"{SHAPE_TYPE.capitalize()} filled with {len(insidePts)} dots @ {SPACING_PX}px pitch"
    )
    plt.tight_layout()
    plt.show()


# ──────── ENTRY POINT ─────────
if __name__ == "__main__":
    main()
