import matplotlib.pyplot as plt
import numpy as np

# ─── Settings ───────────────────────────────────────────────────── #
DOT_SIZE = 40
X_LIM = (0, 100)
Y_LIM = (0, 100)

# ─── Input ───────────────────────────────────────────────────────── #
raw_points = [
    (10, 10),
    (40, 15),
    (60, 50),
    (30, 80),
    (10, 60),
]

# ─── Geometry ───────────────────────────────────────────────────── #

def make_rectilinear(points):
    """
    Convert any polygon into a rectilinear one by inserting L-shaped turns.
    Ensures all edges are axis-aligned (horizontal or vertical).
    """
    rect_path = [points[0]]
    for i in range(1, len(points)):
        prev = rect_path[-1]
        curr = points[i]

        if prev[0] != curr[0] and prev[1] != curr[1]:
            # Insert corner: horizontal then vertical
            mid = (curr[0], prev[1])
            rect_path.append(mid)
        rect_path.append(curr)

    # Close the polygon
    last = rect_path[-1]
    first = rect_path[0]
    if last != first:
        if last[0] != first[0] and last[1] != first[1]:
            mid = (first[0], last[1])
            rect_path.append(mid)
        rect_path.append(first)

    return rect_path

def compute_internal_angle(p0, p1, p2):
    """Return internal angle at vertex p1."""
    v1 = np.array([p0[0]-p1[0], p0[1]-p1[1]])
    v2 = np.array([p2[0]-p1[0], p2[1]-p1[1]])
    angle = np.arctan2(v1[0]*v2[1] - v1[1]*v2[0], np.dot(v1, v2))
    angle_deg = np.degrees(angle)
    if angle_deg < 0:
        angle_deg += 360
    return angle_deg

def classify_vertices(ax, points):
    """Mark convex and concave vertices. Return list of concave (270°) triplets."""
    concaves = []
    n = len(points)
    for i in range(n):
        p0 = points[i - 1]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        angle = compute_internal_angle(p0, p1, p2)
        print(f"Angle at {p1}: {angle:.1f}°")

        if abs(angle - 90) < 1e-3:
            ax.scatter(*p1, color='red', s=DOT_SIZE)
        elif abs(angle - 270) < 1e-3:
            ax.scatter(*p1, color='green', s=DOT_SIZE)
            concaves.append((p0, p1, p2))
    return concaves

def get_direction(p0, p1):
    """Return axis-aligned direction vector from p0 to p1."""
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    if abs(dx) > abs(dy):
        return (np.sign(dx), 0)
    else:
        return (0, np.sign(dy))

def extend_concave_lines(ax, concave_triplets):
    """Extend a line from each 270° corner outward."""
    for p0, p1, p2 in concave_triplets:
        d1 = get_direction(p1, p0)
        d2 = get_direction(p1, p2)

        # Get the direction that's orthogonal to both used edges
        # For axis-aligned vectors, there is only one unused direction
        directions = {(1,0), (-1,0), (0,1), (0,-1)}
        used = {d1, d2}
        unused = list(directions - used)

        if len(unused) == 1:
            dx, dy = unused[0]
            length = max(X_LIM[1], Y_LIM[1])
            end = (p1[0] + dx * length, p1[1] + dy * length)
            ax.plot([p1[0], end[0]], [p1[1], end[1]], 'gray', linestyle='--')
        else:
            print(f"⚠️ Skipping ambiguous direction at {p1}")

# ─── Main ───────────────────────────────────────────────────────── #

def draw():
    rect_path = make_rectilinear(raw_points)

    fig, ax = plt.subplots()
    ax.set_xlim(X_LIM)
    ax.set_ylim(Y_LIM)
    ax.set_aspect('equal')
    ax.set_title("✅ Extension Lines from 270° Corners")

    # Draw polygon
    xs, ys = zip(*rect_path)
    ax.plot(xs, ys, 'b-')

    # Classify and extend
    concave_triplets = classify_vertices(ax, rect_path)
    extend_concave_lines(ax, concave_triplets)

    plt.show()

draw()