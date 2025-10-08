from utils import *

def createPolygon(points, edgecolor='r', fill=None):
    """Creates a matplotlib Polygon object from a list of (x, y) points."""
    return Polygon(points, closed=True, fill=fill, edgecolor=edgecolor)

def getBounds(points, padding=1):
    """Calculates min and max bounds for x and y coordinates with optional padding."""
    x, y = zip(*points)
    x_min, x_max = min(x), max(x)
    y_min, y_max = min(y), max(y)
    return (x_min - padding, x_max + padding), (y_min - padding, y_max + padding)

def plotPolygon(polygon, xlim, ylim, title="Rectilinear Polygon"):
    """Plots the polygon with given axis limits and title."""
    fig, ax = plt.subplots()
    ax.add_patch(polygon)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_title(title)
    ax.grid(False)
    plt.show()

def cutPolyPath(points):
    edges = [
        (points[i], points[(i + 1) % len(points)])
        for i in range(len(points))
    ]
    
    return edges