from utils import *
from plot import *
import matplotlib.pyplot as plt

def determineOrientation(p1, p2):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    if (dx > 0): return RIGHT
    if (dx < 0): return LEFT
    if (dy > 0): return UP
    if (dy < 0): return DOWN
    else: return None

def incidentSides(polySides, point):
    relevantSides = []
    for i, side in enumerate(polySides):
        if (point == side[0] or point == side[1]):
            # print(f"Point {point} is incident to side {i}: {side}")  # debug
            relevantSides.append(side)
    return relevantSides

def removeMimics(polySides, point):
    directions = [UP, DOWN, LEFT, RIGHT]
    relevantSides = incidentSides(polySides, point)
    for side in relevantSides:
        # choose the OTHER endpoint so direction is from `point` outward
        other = side[1] if point == side[0] else side[0]
        dir = determineOrientation(point, other)
        if dir in directions:
            directions.remove(dir)
            # print(f"Removed mimicking direction: {dir}. Remaining: {directions}")  # debug
    return directions

def removeOutsides(polygonPath, point, directions):
    # iterate on a shallow copy since we mutate
    for d in directions[:]:
        probe = (point[0] + delta * d[0], point[1] + delta * d[1])
        if not polygonPath.contains_point(probe):
            directions.remove(d)
            # print(f"Removed outside direction: {d}")  # debug
    return directions

def horizontalSides(polySides):
    return [side for side in polySides if side[0][1] == side[1][1]]

def verticalSides(polySides):
    return [side for side in polySides if side[0][0] == side[1][0]]

def drawLines(point, polySides, directions, ax=None):
    """
    For each viable direction from `point`, find the nearest blocking side and draw a line to it.
    Draws directly onto the current axes so it overlays your polygon.
    """

    if (UP in directions):
        hSides = horizontalSides(polySides)
        best = None
        for h in hSides:
            y = h[0][1]
            if y > point[1] and min(h[0][0], h[1][0]) <= point[0] <= max(h[0][0], h[1][0]):
                if best is None or y < best[0][1]:
                    best = ((point[0], y), h)
        if best:
            intersection = best[0]
            ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')

    if (DOWN in directions):
        hSides = horizontalSides(polySides)
        best = None
        for h in hSides:
            y = h[0][1]
            if y < point[1] and min(h[0][0], h[1][0]) <= point[0] <= max(h[0][0], h[1][0]):
                if best is None or y > best[0][1]:
                    best = ((point[0], y), h)
        if best:
            intersection = best[0]
            ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')

    if (LEFT in directions):
        vSides = verticalSides(polySides)
        best = None
        for v in vSides:
            x = v[0][0]
            if x < point[0] and min(v[0][1], v[1][1]) <= point[1] <= max(v[0][1], v[1][1]):
                if best is None or x > best[0][0]:
                    best = ((x, point[1]), v)
        if best:
            intersection = best[0]
            ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')

    if (RIGHT in directions):
        vSides = verticalSides(polySides)
        best = None
        for v in vSides:
            x = v[0][0]
            if x > point[0] and min(v[0][1], v[1][1]) <= point[1] <= max(v[0][1], v[1][1]):
                if best is None or x < best[0][0]:
                    best = ((x, point[1]), v)
        if best:
            intersection = best[0]
            ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')

def dividePolygon(points, polyPath, polySides, ax=None):
    """
    Your simple driver that:
      - for each vertex, removes mimicking directions and outside directions
      - draws the internal line in each remaining direction
    """
    for point in points:
        directions = removeMimics(polySides, point)
        directions = removeOutsides(polyPath, point, directions)
        drawLines(point, polySides, directions, ax=ax)
