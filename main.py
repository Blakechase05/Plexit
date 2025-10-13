from plot import *
from partition import *
import matplotlib.pyplot as plt
from matplotlib.path import Path


# Example polygon points - this will eventually come from the fdf extractor once they're integrated together and this program stops shitting it's pants
points = [
        (0.0, 0.0), (12.0, 0.0), (12.0, 5.0), (8.0, 5.0),
        (8.0, 6.0), (10.0, 6.0), (10.0, 10.0), (3.0, 10.0),
        (3.0, 7.0), (1.0, 7.0), (1.0, 4.0), (-2.0, 4.0),
        (-2.0, 1.0), (0.0, 1.0)
    ]


def main():
    # Set up da polygon - this should prolly be in plot.py lol
    ax = plotInit(points, xLim=None, yLim=None, title="Rectilinear Polygon")
    
    # Polygon objects (the juicy stuff)
    polygon  = createPolygon(points, edgecolor='r', fill=None)
    polyPath = Path(points, closed=True)
    polySides = cutPolyPath(points)
    rectangles = dividePolygon(points, polyPath, polySides, ax=None, return_rectangles=True)

    # Draw dem rectangles boi
    for (x0, y0), (x1, y1) in rectangles:
        ax.add_patch(plt.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            fill=False, edgecolor='g', linestyle='-', linewidth=1.5
        ))

    # Plot the original polygon on top
    ax.add_patch(polygon)

    plt.show()


if __name__ == "__main__":
    main()