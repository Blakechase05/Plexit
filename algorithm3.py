import matplotlib.pyplot as plt
import matplotlib.patches as patches
from shapely.geometry import Polygon, box, Point
import numpy as np

# ───────────── CONFIG ───────────── #
RECT_WIDTH = 5.0
RECT_HEIGHT = 5.0
AXIS_LIMITS = (0, 100, 0, 100)
# ────────────────────────────────── #

points = []
polygon_patch = None
polygon_finalised = False
merged_rects = []

def reset(ax):
    global points, polygon_patch, polygon_finalised, merged_rects
    points.clear()
    merged_rects.clear()
    polygon_finalised = False
    ax.cla()
    ax.set_title("Left-click to add points | Enter to fill | R to reset")
    ax.set_xlim(AXIS_LIMITS[0], AXIS_LIMITS[1])
    ax.set_ylim(AXIS_LIMITS[2], AXIS_LIMITS[3])
    ax.set_aspect("equal", adjustable="box")
    plt.draw()

def draw_polygon(ax):
    global polygon_patch
    if polygon_patch:
        polygon_patch.remove()

    xs, ys = zip(*points)
    polygon_patch = patches.Polygon(points, closed=True, fill=False, edgecolor='black', linewidth=2)
    ax.add_patch(polygon_patch)
    ax.plot(xs, ys, 'ro')
    plt.draw()

def generate_grid(polygon: Polygon, rect_w: float, rect_h: float):
    minx, miny, maxx, maxy = polygon.bounds
    tiles = []

    x_coords = np.arange(minx, maxx + rect_w, rect_w)
    y_coords = np.arange(miny, maxy + rect_h, rect_h)

    for i, x in enumerate(x_coords):
        for j, y in enumerate(y_coords):
            r = box(x, y, x + rect_w, y + rect_h)
            if polygon.contains(r):
                tiles.append(((i, j), r))

    return tiles, x_coords, y_coords

def merge_all_directions(tiles_dict, x_coords, y_coords, polygon: Polygon):
    visited = set()
    merged = []

    max_i = len(x_coords)
    max_j = len(y_coords)

    # Get sorted list by proximity to centre
    centroid = polygon.centroid
    sorted_keys = sorted(tiles_dict.keys(), key=lambda ij: Point(*tiles_dict[ij].centroid.coords[0]).distance(centroid))

    for i, j in sorted_keys:
        if (i, j) in visited:
            continue

        best_area = 0
        best_rect = None
        best_tiles = []

        # Try all possible origins (i0, j0) that include this (i,j)
        for i0 in range(0, i+1):
            for j0 in range(0, j+1):
                for w in range(1, max_i - i0 + 1):
                    for h in range(1, max_j - j0 + 1):
                        if not (i0 <= i < i0 + w and j0 <= j < j0 + h):
                            continue  # Must contain (i, j)

                        current_tiles = [(ii, jj) for ii in range(i0, i0 + w) for jj in range(j0, j0 + h)]
                        if any((ti, tj) in visited or (ti, tj) not in tiles_dict for (ti, tj) in current_tiles):
                            break  # Some tile is unavailable

                        # Make rectangle box
                        x0 = x_coords[i0]
                        y0 = y_coords[j0]
                        x1 = x0 + w * RECT_WIDTH
                        y1 = y0 + h * RECT_HEIGHT
                        candidate = box(x0, y0, x1, y1)

                        if polygon.contains(candidate):
                            area = w * h
                            if area > best_area:
                                best_area = area
                                best_rect = candidate
                                best_tiles = current_tiles
                        else:
                            break  # stop trying taller h for this w

        # Add best result
        if best_rect:
            for t in best_tiles:
                visited.add(t)
            merged.append(best_rect)

    return merged

def draw_rectangles(ax, rectangles):
    for rect in rectangles:
        coords = list(rect.exterior.coords)[:-1]
        patch = patches.Polygon(
            coords,
            closed=True,
            fill=True,
            edgecolor='blue',
            facecolor='skyblue',
            linewidth=1,
            alpha=0.5
        )
        ax.add_patch(patch)
    plt.draw()

def on_click(event):
    if polygon_finalised or event.inaxes is None:
        return
    if event.button == 1:
        points.append((event.xdata, event.ydata))
        draw_polygon(event.inaxes)

def on_key(event):
    global polygon_finalised, merged_rects
    if event.key == 'enter' and len(points) >= 3:
        polygon_finalised = True
        poly = Polygon(points)
        tiles, x_coords, y_coords = generate_grid(poly, RECT_WIDTH, RECT_HEIGHT)
        tile_dict = {idx: tile for idx, tile in tiles}
        merged_rects = merge_all_directions(tile_dict, x_coords, y_coords, poly)
        draw_rectangles(event.inaxes, merged_rects)
    elif event.key == 'r':
        reset(event.inaxes)

def main():
    fig, ax = plt.subplots()
    ax.set_title("Left-click to add points | Enter to fill | R to reset")
    ax.set_xlim(AXIS_LIMITS[0], AXIS_LIMITS[1])
    ax.set_ylim(AXIS_LIMITS[2], AXIS_LIMITS[3])
    ax.set_aspect('equal', adjustable='box')
    fig.canvas.mpl_connect('button_press_event', on_click)
    fig.canvas.mpl_connect('key_press_event', on_key)
    plt.show()

if __name__ == "__main__":
    main()