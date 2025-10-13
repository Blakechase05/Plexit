from utils import *
from plot import *
import matplotlib.pyplot as plt

# ---------------------------
# your existing functions
# ---------------------------

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
    return directions

def removeOutsides(polygonPath, point, directions):
    # iterate on a shallow copy since we mutate
    for d in directions[:]:
        probe = (point[0] + delta * d[0], point[1] + delta * d[1])
        if not polygonPath.contains_point(probe):
            directions.remove(d)
    return directions

def horizontalSides(polySides):
    return [side for side in polySides if side[0][1] == side[1][1]]

def verticalSides(polySides):
    return [side for side in polySides if side[0][0] == side[1][0]]

def drawLines(point, polySides, directions, ax=None, all_segments=None):
    """
    For each viable direction from `point`, find the nearest blocking side and draw a line to it.
    Draws directly onto the current axes so it overlays your polygon.
    ALSO returns the list of segments it drew: [((x0,y0),(x1,y1)), ...]

    If all_segments is provided, also considers internal segments as blocking sides.
    """
    segments = []

    # Combine boundary sides with internal segments if provided
    if all_segments is None:
        all_segments = []
    combined_sides = list(polySides) + list(all_segments)

    if (UP in directions):
        hSides = horizontalSides(combined_sides)
        best = None
        for h in hSides:
            y = h[0][1]
            if y > point[1] and min(h[0][0], h[1][0]) <= point[0] <= max(h[0][0], h[1][0]):
                if best is None or y < best[0][1]:
                    best = ((point[0], y), h)
        if best:
            intersection = best[0]
            if ax is not None:
                ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')
            segments.append((point, intersection))

    if (DOWN in directions):
        hSides = horizontalSides(combined_sides)
        best = None
        for h in hSides:
            y = h[0][1]
            if y < point[1] and min(h[0][0], h[1][0]) <= point[0] <= max(h[0][0], h[1][0]):
                if best is None or y > best[0][1]:
                    best = ((point[0], y), h)
        if best:
            intersection = best[0]
            if ax is not None:
                ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')
            segments.append((point, intersection))

    if (LEFT in directions):
        vSides = verticalSides(combined_sides)
        best = None
        for v in vSides:
            x = v[0][0]
            if x < point[0] and min(v[0][1], v[1][1]) <= point[1] <= max(v[0][1], v[1][1]):
                if best is None or x > best[0][0]:
                    best = ((x, point[1]), v)
        if best:
            intersection = best[0]
            if ax is not None:
                ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')
            segments.append((point, intersection))

    if (RIGHT in directions):
        vSides = verticalSides(combined_sides)
        best = None
        for v in vSides:
            x = v[0][0]
            if x > point[0] and min(v[0][1], v[1][1]) <= point[1] <= max(v[0][1], v[1][1]):
                if best is None or x < best[0][0]:
                    best = ((x, point[1]), v)
        if best:
            intersection = best[0]
            if ax is not None:
                ax.plot([point[0], intersection[0]], [point[1], intersection[1]], 'b-')
            segments.append((point, intersection))

    return segments

def find_segment_intersections(internal_segments, polySides, polyPath):
    """
    Find all points where segments intersect with each other or with boundary edges.
    This includes:
    - Internal segments intersecting with boundary edges
    - Internal segments intersecting with other internal segments
    Returns a list of intersection points.
    """
    intersections = set()
    all_segments = list(internal_segments) + list(polySides)

    for i, seg1 in enumerate(internal_segments):
        (x1, y1), (x2, y2) = seg1

        # Check if this is a horizontal or vertical segment
        if y1 == y2:  # Horizontal segment
            y = y1
            x_min, x_max = min(x1, x2), max(x1, x2)
            # Find intersections with ALL vertical segments (boundary + internal)
            for seg2 in all_segments:
                (bx1, by1), (bx2, by2) = seg2
                if bx1 == bx2:  # Vertical segment
                    bx = bx1
                    by_min, by_max = min(by1, by2), max(by1, by2)
                    # Check if they intersect (excluding endpoints)
                    if x_min < bx < x_max and by_min < y < by_max:
                        intersections.add((bx, y))

        elif x1 == x2:  # Vertical segment
            x = x1
            y_min, y_max = min(y1, y2), max(y1, y2)
            # Find intersections with ALL horizontal segments (boundary + internal)
            for seg2 in all_segments:
                (bx1, by1), (bx2, by2) = seg2
                if by1 == by2:  # Horizontal segment
                    by = by1
                    bx_min, bx_max = min(bx1, bx2), max(bx1, bx2)
                    # Check if they intersect (excluding endpoints)
                    if y_min < by < y_max and bx_min < x < bx_max:
                        intersections.add((x, by))

    return list(intersections)

def add_sweeplines(points, polyPath, polySides, ax=None):
    """
    Add vertical sweeplines at x-coordinates where they are needed to complete the partition.
    Adds sweeplines at all vertex x-coordinates to ensure complete rectangular decomposition.
    """
    xs = sorted(set([p[0] for p in points]))
    vs = verticalSides(polySides)
    hs = horizontalSides(polySides)

    sweepline_segments = []

    for x in xs:

        # Find all horizontal edges that span this x-coordinate
        # We need all y-coordinates where horizontal boundaries cross this vertical line
        y_coords = set()
        for h in hs:
            y = h[0][1]
            x_min, x_max = min(h[0][0], h[1][0]), max(h[0][0], h[1][0])
            if x_min <= x <= x_max:
                # Add this y-coordinate - it's a boundary crossing point
                y_coords.add(y)

        # Sort y-coordinates and create vertical segments between consecutive pairs
        if len(y_coords) >= 2:
            y_list = sorted(y_coords)
            for i in range(len(y_list) - 1):
                y1, y2 = y_list[i], y_list[i+1]
                # Check if the midpoint is inside the polygon
                mid_y = (y1 + y2) / 2
                if polyPath.contains_point((x, mid_y)):
                    seg = ((x, y1), (x, y2))
                    sweepline_segments.append(seg)
                    if ax is not None:
                        ax.plot([x, x], [y1, y2], 'b-')

    return sweepline_segments

def is_reflex_vertex(points, index):
    """
    Determine if a vertex is reflex (concave) in a polygon.
    Returns True if the vertex is reflex (interior angle > 180 degrees).
    """
    n = len(points)
    prev_point = points[(index - 1) % n]
    curr_point = points[index]
    next_point = points[(index + 1) % n]

    # Calculate vectors
    v1 = (curr_point[0] - prev_point[0], curr_point[1] - prev_point[1])
    v2 = (next_point[0] - curr_point[0], next_point[1] - curr_point[1])

    # Calculate cross product (z-component)
    cross = v1[0] * v2[1] - v1[1] * v2[0]

    # For counterclockwise winding:
    # - If cross < 0, the vertex is reflex (concave, interior angle > 180°)
    # - If cross > 0, the vertex is convex (interior angle < 180°)
    return cross < 0

def dividePolygon(points, polyPath, polySides, ax=None, return_rectangles=False):
    """
    Your simple driver that:
      - for each vertex, removes mimicking directions and outside directions
      - draws the internal line in each remaining direction
      - for reflex vertices, also tries to draw lines even if removeOutsides filters them
    Now also collects the drawn internal segments and (optionally) computes rectangles.

    If return_rectangles=True, returns (internal_segments, rectangles).
    Otherwise returns None (original behavior), but still draws on 'ax' if provided.
    """
    all_internal = []

    # First pass: draw lines from all vertices
    for i, point in enumerate(points):
        directions = removeMimics(polySides, point)
        is_reflex = is_reflex_vertex(points, i)

        if is_reflex:
            # For reflex vertices, try all non-mimicking directions
            # because they may need to extend into notches
            segs = drawLines(point, polySides, directions, ax=ax)
        else:
            # For convex vertices, filter out outside directions
            directions = removeOutsides(polyPath, point, directions)
            segs = drawLines(point, polySides, directions, ax=ax)

        all_internal.extend(segs)

    # Add sweeplines at each x-coordinate to complete the partition
    sweepline_segs = add_sweeplines(points, polyPath, polySides, ax=ax)
    all_internal.extend(sweepline_segs)

    # Second pass: find intersection points and draw lines from them
    # We need to iterate until no new segments are added
    max_iterations = 10
    for iteration in range(max_iterations):
        intersection_points = find_segment_intersections(all_internal, polySides, polyPath)

        new_segments = []
        for point in intersection_points:
            # For intersection points, we don't use removeMimics since they're not vertices
            # We only check which directions point inward
            directions = [UP, DOWN, LEFT, RIGHT]
            directions = removeOutsides(polyPath, point, directions)

            # Pass all_internal so drawLines can consider internal segments as blocking
            segs = drawLines(point, polySides, directions, ax=ax, all_segments=all_internal)

            for seg in segs:
                # Check if this segment (or its reverse) already exists
                if seg not in all_internal and (seg[1], seg[0]) not in all_internal:
                    new_segments.append(seg)

        if not new_segments:
            break

        all_internal.extend(new_segments)

    if return_rectangles:
        rects = find_rectangles_from_segments(polyPath, polySides, all_internal)
        return rects
    # keep backward compatibility (caller may ignore return)
    return None

# ---------------------------
# added helpers for rectangles
# ---------------------------

def _split_HV(segments):
    """Split into normalized horizontals and verticals.
       Returns H: dict[y] -> [(x1,x2), ...], V: dict[x] -> [(y1,y2), ...]  (NOT merged yet)
    """
    H = {}
    V = {}
    for (a, b) in segments:
        x1, y1 = a
        x2, y2 = b
        if y1 == y2:
            xm, xM = (x1, x2) if x1 <= x2 else (x2, x1)
            H.setdefault(y1, []).append((xm, xM))
        elif x1 == x2:
            ym, yM = (y1, y2) if y1 <= y2 else (y2, y1)
            V.setdefault(x1, []).append((ym, yM))
        else:
            # ignore non-axis-aligned (shouldn't happen in rectilinear case)
            pass
    return H, V

def _merge_intervals(iv_list):
    """Merge overlapping/contiguous intervals on one line."""
    if not iv_list:
        return []
    iv = sorted(iv_list)
    out = [list(iv[0])]
    for s, e in iv[1:]:
        if s <= out[-1][1]:
            # overlap or touch → extend
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for (s, e) in out]

def _merge_by_key(map_in):
    """Merge intervals for each y or x key."""
    return {k: _merge_intervals(v) for k, v in map_in.items()}

def _interval_covered(key, a, b, cov):
    """Is [a,b] fully covered by any interval list at cov[key]?"""
    if key not in cov:
        return False
    for s, e in cov[key]:
        if a >= s and b <= e:
            return True
    return False

def _collect_grid_coords(segments):
    """All unique x and y from endpoints of segments."""
    xs = set()
    ys = set()
    for (p, q) in segments:
        xs.add(p[0]); xs.add(q[0])
        ys.add(p[1]); ys.add(q[1])
    xs = sorted(xs)
    ys = sorted(ys)
    return xs, ys

def _find_relevant_x_coords_at_y_range(segments, y_min, y_max):
    """Find all x-coordinates that have vertical coverage in the given y-range."""
    xs = set()
    for (p, q) in segments:
        x1, y1 = p
        x2, y2 = q
        # Check if this is a vertical segment that overlaps with [y_min, y_max]
        if x1 == x2:  # vertical segment
            seg_y_min, seg_y_max = min(y1, y2), max(y1, y2)
            # Check if ranges overlap
            if not (seg_y_max <= y_min or seg_y_min >= y_max):
                xs.add(x1)
    return sorted(xs)

def find_rectangles_from_segments(polyPath, polySides, internalSegments):
    """
    Implements a modified grid method that finds minimal rectangles.
    Returns a list of rectangles as ((x0,y0),(x1,y1)).
    """
    # 1) all segments = boundary + internal
    all_segments = list(polySides) + list(internalSegments)

    # 2) split into H/V and merge per line
    H_raw, V_raw = _split_HV(all_segments)
    covH = _merge_by_key(H_raw)  # y -> merged (x1,x2)
    covV = _merge_by_key(V_raw)  # x -> merged (y1,y2)

    # 3) build grid coords
    xs, ys = _collect_grid_coords(all_segments)
    if len(xs) < 2 or len(ys) < 2:
        return []

    # 4) iterate over grid cells (adjacent pairs only) for minimal rectangles
    rectangles = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]

            # center test inside polygon
            cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
            if not polyPath.contains_point((cx, cy)):
                continue

            # all four edges present?
            top_ok    = _interval_covered(y1, x0, x1, covH)
            bottom_ok = _interval_covered(y0, x0, x1, covH)
            left_ok   = _interval_covered(x0, y0, y1, covV)
            right_ok  = _interval_covered(x1, y0, y1, covV)

            if top_ok and bottom_ok and left_ok and right_ok:
                rectangles.append(((x0, y0), (x1, y1)))

    return rectangles
