from plot import *
from partition import *
import matplotlib.pyplot as plt
from matplotlib.path import Path

def main():
    # Your original demo polygon
    points = [
        (0.0, 0.0), (12.0, 0.0), (12.0, 5.0), (8.0, 5.0),
        (8.0, 6.0), (10.0, 6.0), (10.0, 10.0), (3.0, 10.0),
        (3.0, 7.0), (1.0, 7.0), (1.0, 4.0), (-2.0, 4.0),
        (-2.0, 1.0), (0.0, 1.0)
    ]

    # Set up polygon objects
    polygon  = createPolygon(points, edgecolor='r', fill=None)
    polyPath = Path(points, closed=True)
    polySides = cutPolyPath(points)

    # (Optional quick test on one vertex)
    # dir = removeMimics(polySides, (8.0, 5.0))
    # dir = removeOutsides(polyPath, (8.0, 5.0), dir)
    # drawLines((8.0, 5.0), polySides, dir)

    # Plot polygon & show
    xLim, yLim = getBounds(points)
    fig, ax = plt.subplots()
    ax.add_patch(polygon)
    ax.set_xlim(xLim)
    ax.set_ylim(yLim)
    ax.set_title("Rectilinear Polygon")
    ax.set_aspect('equal', adjustable='box')
    ax.grid(False)

    dividePolygon(points, polyPath, polySides, ax)

    plt.show()

if __name__ == "__main__":
    main()