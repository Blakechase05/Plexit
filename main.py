from plot import *
from partition import *
from merge import optimize_rectangles, merge_greedy, merge_optimal_fast
import matplotlib.pyplot as plt
from matplotlib.path import Path


# Example polygon points - this will eventually come from the fdf extractor once they're integrated together and this program stops shitting it's pants
# 1) Simple rectangle
# 2) L-shape
# 3) U-shape
# 4) Notched rectangle (single inward notch)
# 5) Staircase (monotone up-right)
# 6) Corridor with bays
# 7) Zigzag notch along top
# 8) “C” shape (thick frame with one open side)
# 9) Double-notch rectangle
# 10) “E” shape (three prongs)
points = [(0,0), (14,0), (14,2), (6,2), (6,4), (12,4), (12,6),
          (6,6), (6,8), (14,8), (14,10), (0,10)]

# 11) Box with internal courtyard mouth (concave)
# 12) Complex rectilinear (multiple steps and bays)


def main():
    # Set up da polygon - this should prolly be in plot.py lol
    ax = plotInit(points, xLim=None, yLim=None, title="Rectilinear Polygon - Optimized Merge")

    # Polygon objects (the juicy stuff)
    polygon  = createPolygon(points, edgecolor='r', fill=None)
    polyPath = Path(points, closed=True)
    polySides = cutPolyPath(points)
    rectangles = dividePolygon(points, polyPath, polySides, ax=None, return_rectangles=True)

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

    # for (x0, y0), (x1, y1) in rectangles:
    #     ax.add_patch(plt.Rectangle(
    #         (x0, y0), x1 - x0, y1 - y0,
    #         fill=False, edgecolor='b', linestyle='--', linewidth=1
    #     ))
    # Draw optimized rectangles
    for (x0, y0), (x1, y1) in optimized_rectangles:
        ax.add_patch(plt.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            fill=False, edgecolor='g', linestyle='-', linewidth=1.5
        ))

    # Plot the original polygon on top
    ax.add_patch(polygon)

    plt.show()


if __name__ == "__main__":
    main()