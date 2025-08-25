#!/usr/bin/env python3
# Highlight internal U-shapes (three sides A, B, -A) in a rectilinear polygon.
# Criteria:
#   • A ⟂ B and C == −A (after colinear compression into runs)
#   • both turn vertices (between A-B and B-C) are reflex (270°)
#   • mouth midpoint is OUTSIDE the polygon (inclusive=false)
#   • stem (B) midpoint is INSIDE the polygon (INCLUSIVE=true so on-edge counts)
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import argparse
import os
import sys

# Optional plotting (fallback to SVG if matplotlib is missing)
try:
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
    plt = None  # type: ignore

Point = Tuple[float, float]

# -------------------------------
# Basic helpers
# -------------------------------

def close_poly(pts: List[Point]) -> List[Point]:
    return pts if (not pts or pts[0] == pts[-1]) else pts + [pts[0]]

def parse_points(s: str) -> List[Point]:
    pts: List[Point] = []
    s = s.strip()
    if not s:
        return pts
    for tok in s.replace(";", " ").split():
        x_str, y_str = tok.split(",")
        pts.append((float(x_str), float(y_str)))
    return pts

def is_axis_aligned(a: Point, b: Point) -> bool:
    return a[0] == b[0] or a[1] == b[1]

def edge_dir(a: Point, b: Point) -> Tuple[int, int, float]:
    """Axis-aligned unit direction (ux,uy) and length from a→b."""
    if not is_axis_aligned(a, b):
        raise ValueError("Non-rectilinear edge detected")
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if dx == 0 and dy == 0:
        return (0, 0, 0.0)
    if dx != 0:
        return (1 if dx > 0 else -1, 0, abs(dx))
    else:
        return (0, 1 if dy > 0 else -1, abs(dy))

def signed_area(pts: List[Point]) -> float:
    c = close_poly(pts)
    return 0.5 * sum(c[i][0]*c[i+1][1] - c[i+1][0]*c[i][1] for i in range(len(c)-1))

# Point-in-polygon
def point_in_poly_inclusive(x: float, y: float, pts: List[Point]) -> bool:
    """On-edge counts as inside."""
    c = close_poly(pts); inside = False
    for i in range(len(c) - 1):
        x1, y1 = c[i]; x2, y2 = c[i + 1]
        # on-edge
        if (y1 == y2 and y == y1 and min(x1, x2) <= x <= max(x1, x2)) or \
           (x1 == x2 and x == x1 and min(y1, y2) <= y <= max(y1, y2)):
            return True
        # ray up
        if (y1 > y) != (y2 > y):
            xint = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-30) + x1
            if x < xint:
                inside = not inside
    return inside

def point_in_poly_strict(x: float, y: float, pts: List[Point]) -> bool:
    """On-edge counts as outside."""
    c = close_poly(pts); inside = False
    for i in range(len(c) - 1):
        x1, y1 = c[i]; x2, y2 = c[i + 1]
        # on-edge → outside
        if (y1 == y2 and y == y1 and min(x1, x2) <= x <= max(x1, x2)) or \
           (x1 == x2 and x == x1 and min(y1, y2) <= y <= max(y1, y2)):
            return False
        # ray up
        if (y1 > y) != (y2 > y):
            xint = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-30) + x1
            if x < xint:
                inside = not inside
    return inside

# -------------------------------
# Runs (merge colinear edges)
# -------------------------------

@dataclass(frozen=True)
class Run:
    dirx: int; diry: int
    length: float
    start_idx: int   # vertex index where the run starts (in closed poly)
    end_idx:   int   # vertex index where the run ends   (corner at end)

def nonzero_edges(c: List[Point]):
    n = len(c) - 1
    out = []
    for i in range(n):
        ux, uy, L = edge_dir(c[i], c[i+1])
        if L > 0:
            out.append((i, (ux, uy, L)))
    return out

def compute_runs(pts: List[Point]) -> List[Run]:
    c = close_poly(pts)
    edges = nonzero_edges(c)
    if not edges:
        return []
    runs: List[Run] = []
    start_i, (ux, uy, L) = edges[0]
    cur_dir = (ux, uy)
    cur_len = L
    cur_start = start_i
    cur_end = start_i + 1
    for idx, (vx, vy, VL) in edges[1:]:
        if (vx, vy) == cur_dir:
            cur_len += VL
            cur_end = idx + 1
        else:
            runs.append(Run(cur_dir[0], cur_dir[1], cur_len, cur_start, cur_end))
            cur_dir = (vx, vy)
            cur_len = VL
            cur_start = idx
            cur_end = idx + 1
    runs.append(Run(cur_dir[0], cur_dir[1], cur_len, cur_start, cur_end))
    return runs

# -------------------------------
# Reflex (270°) at a vertex
# -------------------------------

def is_reflex_vertex(c: List[Point], i: int, ccw: bool) -> bool:
    """Is vertex i a reflex (270°) corner?"""
    n = len(c) - 1
    i_prev = (i - 1) % n
    i_next = (i + 1) % n
    ax = c[i][0] - c[i_prev][0]
    ay = c[i][1] - c[i_prev][1]
    bx = c[i_next][0] - c[i][0]
    by = c[i_next][1] - c[i][1]
    z = ax * by - ay * bx
    # For CCW polys, right turns (z < 0) are reflex; for CW, left turns (z > 0) are reflex
    return (z < 0) if ccw else (z > 0)

# -------------------------------
# U-shape detection (internal only)
# -------------------------------

@dataclass(frozen=True)
class Segment:
    x1: float; y1: float; x2: float; y2: float

def detect_u_triples(pts: List[Point], debug: bool = False) -> List[List[Segment]]:
    """
    Find INTERNAL U-triples (A,B,-A), highlighting exactly those three sides.
    Conditions:
      - A ⟂ B  and  C == −A  (using colinear-compressed runs)
      - Both turn vertices are reflex (270°)
      - Mouth midpoint is OUTSIDE the polygon   (strict: on-edge treated as outside is fine)
      - Stem (B) midpoint is INSIDE the polygon (INCLUSIVE so on-edge counts)
    """
    c = close_poly(pts)
    n = len(c) - 1
    if n < 4:
        return []
    ccw = signed_area(pts) > 0
    runs = compute_runs(pts)
    m = len(runs)
    triples: List[List[Segment]] = []

    if debug:
        print(f"[debug] vertices={n}, runs={m}")

    for r in range(m):
        A = runs[r]
        B = runs[(r + 1) % m]
        C = runs[(r + 2) % m]

        # A ⟂ B  and  C == −A
        if A.dirx * B.dirx + A.diry * B.diry != 0:
            continue
        if (C.dirx, C.diry) != (-A.dirx, -A.diry):
            continue

        # Mouth corners (between A-B and B-C)
        v1 = A.end_idx % n
        v2 = B.end_idx % n

        # Both corners must be reflex
        if not (is_reflex_vertex(c, v1, ccw) and is_reflex_vertex(c, v2, ccw)):
            continue

        # Build segment endpoints
        a0 = c[A.start_idx % n]; a1 = c[A.end_idx % n]
        b0 = c[B.start_idx % n]; b1 = c[B.end_idx % n]
        c0p = c[C.start_idx % n]; c1p = c[C.end_idx % n]

        # Internal-vs-external checks:
        # 1) Mouth midpoint OUTSIDE polygon
        mouth_mid = ((c[v1][0] + c[v2][0]) * 0.5, (c[v1][1] + c[v2][1]) * 0.5)
        if point_in_poly_inclusive(mouth_mid[0], mouth_mid[1], pts):
            # midpoint is inside → external "tab", skip
            continue

        # 2) Stem midpoint INSIDE polygon (INCLUSIVE: on-edge counts as inside)
        stem_mid = ((b0[0] + b1[0]) * 0.5, (b0[1] + b1[1]) * 0.5)
        if not point_in_poly_inclusive(stem_mid[0], stem_mid[1], pts):
            continue

        triple = [Segment(*a0, *a1), Segment(*b0, *b1), Segment(*c0p, *c1p)]
        triples.append(triple)

    if debug:
        print(f"[debug] internal U-triples found: {len(triples)}")

    return triples

# -------------------------------
# Rendering
# -------------------------------

def plot_matplotlib(pts: List[Point], triples: List[List[Segment]], annotate: bool = True) -> None:
    assert HAS_MPL
    c = close_poly(pts)
    xs = [p[0] for p in c]; ys = [p[1] for p in c]
    fig, ax = plt.subplots(figsize=(7, 7))
    # polygon outline
    ax.plot(xs, ys, "-k", linewidth=2)

    # draw all highlighted segments in green
    for tri in triples:
        for seg in tri:
            ax.plot([seg.x1, seg.x2], [seg.y1, seg.y2], color="green", linewidth=4, solid_capstyle="round")

    if annotate:
        for i, (x, y) in enumerate(c[:-1]):
            ax.text(x, y, str(i), fontsize=9, ha="center", va="center",
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.5))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("Internal U-shape sides highlighted (green)")
    plt.show()

def save_svg(filename: str, pts: List[Point], triples: List[List[Segment]], annotate: bool = True) -> None:
    c = close_poly(pts)
    if not c:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("<svg xmlns='http://www.w3.org/2000/svg' width='400' height='200'/>")
        return
    xs = [p[0] for p in c[:-1]]; ys = [p[1] for p in c[:-1]]
    minx, maxx = min(xs), max(xs); miny, maxy = min(ys), max(ys)
    margin = 20.0; scale = 40.0
    width = (maxx - minx) * scale + 2 * margin
    height = (maxy - miny) * scale + 2 * margin

    def tx(x): return (x - minx) * scale + margin
    def ty(y): return height - ((y - miny) * scale + margin)

    lines: List[str] = []
    lines.append(f"<svg xmlns='http://www.w3.org/2000/svg' width='{width:.0f}' height='{height:.0f}'>")
    lines.append("  <rect x='0' y='0' width='100%' height='100%' fill='white'/>")

    # polygon outline
    poly_pts = " ".join(f"{tx(x):.2f},{ty(y):.2f}" for (x, y) in c)
    lines.append(f"  <polyline points='{poly_pts}' fill='none' stroke='black' stroke-width='2'/>")

    # green segments
    for tri in triples:
        for seg in tri:
            lines.append(
                f"  <line x1='{tx(seg.x1):.2f}' y1='{ty(seg.y1):.2f}' "
                f"x2='{tx(seg.x2):.2f}' y2='{ty(seg.y2):.2f}' "
                f"stroke='green' stroke-width='6' stroke-linecap='round'/>"
            )

    if annotate:
        for i, (x, y) in enumerate(c[:-1]):
            lines.append(f"  <text x='{tx(x)+6:.2f}' y='{ty(y)-6:.2f}' font-size='10' font-family='Arial'>{i}</text>")

    lines.append("</svg>")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# -------------------------------
# Demo + Tests
# -------------------------------

def demo_polygon() -> List[Point]:
    # Example with a notch
    return [
        (0.0, 0.0),
        (12.0, 0.0),
        (12.0, 2.0),
        (8.0, 2.0),
        (8.0, 6.0),
        (10.0, 6.0),
        (10.0, 10.0),
        (3.0, 10.0),
        (3.0, 7.0),
        (1.0, 7.0),
        (1.0, 4.0),
        (-2.0, 4.0),
        (-2.0, 1.0),
        (0.0, 1.0),
    ]

def run_tests() -> None:
    # 1) Rectangle → no internal U-triples
    rect = [(0,0),(10,0),(10,6),(0,6)]
    assert detect_u_triples(rect) == []

    # 2) Internal U-shaped notch
    poly_notch = [(0,0),(10,0),(10,8),(6,8),(6,3),(4,3),(4,8),(0,8)]
    assert len(detect_u_triples(poly_notch)) >= 1

    # 3) External tab (should be ignored)
    poly_tab = [(0,0),(10,0),(10,8),(6,8),(6,10),(4,10),(4,8),(0,8)]
    assert len(detect_u_triples(poly_tab)) == 0

    # 4) Two adjacent internal notches
    poly_adj = [
        (0,0),(16,0),(16,10),
        (14,10),(14,7),(12,7),(12,10),
        (10,10),(10,7),(8,7),(8,10),
        (0,10)
    ]
    assert len(detect_u_triples(poly_adj)) >= 2

    # 5) Vertical-U variant
    poly_vert = [(0,0),(8,0),(8,10),(5,10),(5,6),(3,6),(3,10),(0,10)]
    assert len(detect_u_triples(poly_vert)) >= 1

    # Smoke SVG
    out = "test_plot.svg"
    try:
        if os.path.exists(out): os.remove(out)
    except Exception:
        pass
    save_svg(out, demo_polygon(), detect_u_triples(demo_polygon()))
    assert os.path.exists(out)
    print("All tests passed.")

# -------------------------------
# CLI
# -------------------------------

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Highlight INTERNAL U-shape triples (A, B, -A) in a rectilinear polygon")
    ap.add_argument("--points", type=str, help="Space-separated 'x,y' pairs")
    ap.add_argument("--no-annotate", action="store_true", help="Do not label vertex indices")
    ap.add_argument("--tests", action="store_true", help="Run tests and exit")
    ap.add_argument("--out", type=str, default="plot.svg", help="SVG output when matplotlib is unavailable")
    ap.add_argument("--debug", action="store_true", help="Print counts while detecting")
    args = ap.parse_args(argv)

    if args.tests:
        run_tests()
        return 0

    pts = parse_points(args.points) if args.points else demo_polygon()
    triples = detect_u_triples(pts, debug=args.debug)

    if HAS_MPL:
        plot_matplotlib(pts, triples, annotate=not args.no_annotate)
    else:
        save_svg(args.out, pts, triples, annotate=not args.no_annotate)
        print(f"Matplotlib not available — wrote SVG: {args.out}")
    return 0

if __name__ == "__main__":
    _ = main(sys.argv[1:])
