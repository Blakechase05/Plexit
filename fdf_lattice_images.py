#!/usr/bin/env python3
"""
polygon_shapely_rectsplit.py
--------------------------------
Draw a polygon using Shapely and split it into axis-aligned rectangles.
This version uses a greedy grow algorithm on a rasterised grid
for minimal rectangular decomposition of orthogonal-like polygons.
Handles slight imperfections by snapping points to a grid.
"""

from typing import List, Tuple
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, box, LineString, Point
from shapely.prepared import prep
import numpy as np

# ─────────── CONFIG ───────────
CANVAS_SIZE_PX = 500
SHAPE_TYPE = "polygon"  # or "snake"
MARGIN_RATIO = 0.05
SNAKE_BUFFER_PX = 15
FILL_COLOR = "lightblue"
EDGE_COLOR = "black"
LINE_COLOR = "gray"
RECTANGLE_FILL_ALPHA = 0.4
GRID_STEP = 50.0  # in screen units (pixels)
SNAP_TOLERANCE = GRID_STEP / 2  # Snap points to nearest grid point
# ──────────────────────────────

def snap_to_grid(coords: List[Tuple[float, float]], step: float) -> List[Tuple[float, float]]:
    """Snap all points to nearest grid based on step."""
    return [(round(x / step) * step, round(y / step) * step) for x, y in coords]

def collectPolygonPoints() -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []

    fig, ax = plt.subplots()
    ax.set_title("Click to define shape (Right click or Enter to finish, 'r' to reset)")
    ax.set_xlim(0, CANVAS_SIZE_PX)
    ax.set_ylim(0, CANVAS_SIZE_PX)
    ax.invert_yaxis()
    ax.set_aspect('equal')
    marker_plot, = ax.plot([], [], marker="o", linestyle="-", color="black")

    def onclick(event):
        nonlocal points
        if event.button == 1 and event.inaxes:
            points.append((event.xdata, event.ydata))
            marker_plot.set_data(*zip(*points))
            fig.canvas.draw()
        elif event.button == 3:
            plt.close()

    def onkey(event):
        nonlocal points
        if event.key == 'enter':
            plt.close()
        elif event.key == 'r':
            points.clear()
            marker_plot.set_data([], [])
            fig.canvas.draw()

    fig.canvas.mpl_connect('button_press_event', onclick)
    fig.canvas.mpl_connect('key_press_event', onkey)
    plt.show()
    return points

def buildShape(shapeType: str, coords: List[Tuple[float, float]], snap_step: float) -> Polygon:
    snapped = snap_to_grid(coords, snap_step)
    if shapeType == "polygon":
        if snapped[0] != snapped[-1]:
            snapped.append(snapped[0])
        return Polygon(snapped)
    elif shapeType == "snake":
        return LineString(snapped).buffer(SNAKE_BUFFER_PX)
    else:
        raise ValueError("Invalid SHAPE_TYPE")

def greedy_raster_rectangle_decompose(polygon: Polygon, step: float) -> List[Polygon]:
    """
    Decompose polygon into large rectangles using greedy grow over a grid.
    """
    minx, miny, maxx, maxy = polygon.bounds
    width = int((maxx - minx) // step) + 1
    height = int((maxy - miny) // step) + 1

    grid = np.zeros((height, width), dtype=bool)
    prepared = prep(polygon)

    # Mark grid cells inside the polygon
    for row in range(height):
        for col in range(width):
            cx = minx + col * step + step / 2
            cy = miny + row * step + step / 2
            if prepared.contains(Point(cx, cy)):
                grid[row, col] = True

    rects = []
    visited = np.zeros_like(grid)

    for row in range(height):
        for col in range(width):
            if grid[row, col] and not visited[row, col]:
                # Grow rectangle as wide as possible
                w = 0
                while col + w < width and grid[row, col + w] and not visited[row, col + w]:
                    w += 1

                # Grow downward while all rows below maintain same width
                h = 1
                while row + h < height and all(grid[row + h, col:col + w]) and all(~visited[row + h, col:col + w]):
                    h += 1

                # Mark visited
                visited[row:row + h, col:col + w] = True

                # Create rectangle polygon
                x0 = minx + col * step
                y0 = miny + row * step
                x1 = minx + (col + w) * step
                y1 = miny + (row + h) * step
                rect = box(x0, y0, x1, y1)
                rects.append(rect)

    return rects

def plot_rectangles_on_polygon(original: Polygon, rectangles: List[Polygon]):
    fig, ax = plt.subplots()
    ax.set_xlim(0, CANVAS_SIZE_PX)
    ax.set_ylim(0, CANVAS_SIZE_PX)
    ax.set_aspect("equal")
    ax.invert_yaxis()

    # Original polygon outline
    x, y = original.exterior.xy
    ax.plot(x, y, color=EDGE_COLOR, linewidth=2, linestyle="-", label="Original Polygon")

    # Overlay rectangles
    for i, rect in enumerate(rectangles):
        rx, ry = rect.exterior.xy
        ax.fill(rx, ry, facecolor=FILL_COLOR, edgecolor=LINE_COLOR, alpha=RECTANGLE_FILL_ALPHA, label="" if i > 0 else "Rectangles")

    ax.set_title(f"Decomposed into {len(rectangles)} rectangles (Snapped & Greedy)")
    ax.legend()
    plt.tight_layout()
    plt.show()

def main():
    coords = collectPolygonPoints()
    if len(coords) < 3:
        print("❌ Not enough points for polygon.")
        return

    poly = buildShape(SHAPE_TYPE, coords, snap_step=GRID_STEP)
    margin = CANVAS_SIZE_PX * MARGIN_RATIO
    inset = poly.buffer(-margin)

    rectangles = greedy_raster_rectangle_decompose(inset, step=GRID_STEP)
    plot_rectangles_on_polygon(poly, rectangles)

if __name__ == "__main__":
    main()
