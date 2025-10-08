from utils import *

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
            # print(f"Point {point} is incident to side {i}: {side}") # Debugging line
            relevantSides.append(side)
        
    return relevantSides

def removeMimics(polySides, point):
    directions = [UP, DOWN, LEFT, RIGHT]

    relevantSides = incidentSides(polySides, point)

    for side in relevantSides:
        # choose the OTHER endpoint so direction is from `point` outward
        other = side[1] if point == side[0] else side[0]

        dir = determineOrientation(point, other)  # use your function as-is
        # print(f"At {point}, side {side} blocks direction {dir}") # Debugging line

        if dir in directions:
            directions.remove(dir)
            # print(f"Removed mimicking direction: {dir}. Remaining: {directions}") # Debugging line
        # else:
        #     print(f"No removal for {dir} (already removed or None).") # Debugging line

    return directions

def removeOutsides(polygon, point, directions):
    for d, direction in enumerate(directions[:]):  # iterate over a shallow copy
        probe = (point[0] + delta * direction[0], point[1] + delta * direction[1])
        if not polygon.contains_point(probe):
            directions.remove(direction)
            # print(f"Removed outside direction: {direction}") # Debugging line
    return directions

def dividePolygon(polygon):
    print("Hello World!")