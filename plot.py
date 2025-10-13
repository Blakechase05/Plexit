from utils import *
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

def plotInit(points, xLim, yLim, title="Rectilinear Polygon"):
    xLim, yLim = getBounds(points)
    fig, ax = plt.subplots()
    ax.set_xlim(xLim)
    ax.set_ylim(yLim)
    ax.set_title(title)
    ax.set_aspect('equal', adjustable='box')
    ax.grid(False)

    return ax

def createPolygon(points, edgecolor='r', fill=None):
    """Creates a matplotlib Polygon object from a list of (x, y) points."""
    return MplPolygon(points, closed=True, fill=fill, edgecolor=edgecolor)

def getBounds(points, padding=1):
    """Calculates min and max bounds for x and y with optional padding."""
    x, y = zip(*points)
    x_min, x_max = min(x), max(x)
    y_min, y_max = min(y), max(y)
    return (x_min - padding, x_max + padding), (y_min - padding, y_max + padding)

def plotLine(start, end, style='b-'):
    plt.plot([start[0], end[0]], [start[1], end[1]], style)

def cutPolyPath(points):
    edges = [
        (points[i], points[(i + 1) % len(points)])
        for i in range(len(points))
    ]
    return edges
