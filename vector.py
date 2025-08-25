#!/usr/bin/env python3
"""
Visualise polygon edges and highlight 'reflection' triples:
(i, i+1, i+2) where edges i and i+2 are anti-parallel (opposite directions)
and edge i+1 is perpendicular to both.

Bridges (your rule):
1) For each reflection triple, compare the two parallel edges (1 & 3) and pick the shorter.
2) From the far end of the shorter edge (the endpoint NOT touching the middle edge), draw a line to the
   nearest point on the other parallel edge (perpendicular foot if inside the segment, otherwise nearest endpoint).
3) Bridge-inside filter: If that bridge lies outside the polygon, exclude that group.

Rectangle step:
- Build the full rectangle for each **kept** group by projecting **both** endpoints of the shorter edge onto the
  other parallel edge.

Post-processing:
- Separate overlaps: produce the **cover** pieces
  (non-overlap originals + trimmed remainder pieces + overlap piece rectangles).
- Compute leftover polygon(s): original polygon minus union of rectangles.
- (Optional) Merge cover rectangles into larger rectilinear polygons (side-adjacent union).

Dots (this file’s default demo):
- After overlap separation, draw a dot matrix per separated piece,
  anchored at that piece’s centroid, and keep dots strictly inside the piece.
"""

import math
from typing import List, Tuple, Dict, Any, Union

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Polygon
from matplotlib.collections import LineCollection

Point = Tuple[float, float]
EPS = 1e-9


# ---------- Basic helpers ----------
def close_polygon(verts: List[Point]) -> np.ndarray:
    P = np.asarray(verts, dtype=float)
    if not np.allclose(P[0], P[-1]):
        P = np.vstack([P, P[0]])
    return P


def signed_area(verts: List[Point]) -> float:
    P = close_polygon(verts)
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def unit(v: np.ndarray) -> np.ndarray:
    n = float(np.hypot(v[0], v[1]))
    if n < EPS:
        return np.array([0.0, 0.0])
    return v / n


def almost_zero(x: float, tol: float = 1e-8) -> bool:
    return abs(x) <= tol


def seg_len(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.hypot(*(b - a)))


def project_point_to_segment(q: np.ndarray, a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, float, bool]:
    """Project point q onto segment ab. Returns (p, t, inside) with clamped t ∈ [0,1]."""
    ab = b - a
    denom = float(ab[0] * ab[0] + ab[1] * ab[1])
    if denom < EPS:
        return a.copy(), 0.0, False
    t = float(((q - a) @ ab) / denom)
    inside = 0.0 <= t <= 1.0
    t_clamped = max(0.0, min(1.0, t))
    p = a + t_clamped * ab
    return p, t_clamped, inside


def point_on_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray, tol: float = 1e-9) -> bool:
    ap, bp = p - a, p - b
    ab = b - a
    cross = abs(ab[0] * ap[1] - ab[1] * ap[0])
    if cross > tol:
        return False
    dot = (ap @ bp)
    return dot <= tol  # between a and b


def point_in_polygon(p: np.ndarray, poly: np.ndarray) -> bool:
    """Ray casting; boundary counts as inside."""
    # On any edge?
    for i in range(len(poly) - 1):
        if point_on_segment(p, poly[i], poly[i + 1]):
            return True
    x, y = float(p[0]), float(p[1])
    inside = False
    for i in range(len(poly) - 1):
        x0, y0 = poly[i]
        x1, y1 = poly[i + 1]
        if (y0 > y) != (y1 > y):
            xint = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xint >= x - 1e-12:
                inside = not inside
    return inside


def point_to_polygon_min_dist(p: np.ndarray, poly: np.ndarray) -> float:
    """Euclidean distance from point p to polygon boundary (0 if on edge)."""
    P = poly if np.allclose(poly[0], poly[-1]) else np.vstack([poly, poly[0]])
    dmin = float("inf")
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        proj, _, _ = project_point_to_segment(p, a, b)
        d = float(np.hypot(*(p - proj)))
        if d < dmin:
            dmin = d
    return dmin


def segment_inside_polygon(a: np.ndarray, b: np.ndarray, poly: np.ndarray) -> bool:
    """Conservative: sample along segment and require all sample points are inside."""
    ts = [0.1, 0.25, 0.5, 0.75, 0.9]
    for t in ts:
        p = (1 - t) * a + t * b
        if not point_in_polygon(p, poly):
            return False
    return True


# ---------- Edge info ----------
def edge_info(verts: List[Point]):
    P = close_polygon(verts)
    for i in range(len(P) - 1):
        x0, y0 = P[i]
        x1, y1 = P[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < EPS:
            continue
        ux, uy = dx / L, dy / L
        ang = math.degrees(math.atan2(dy, dx))  # 0° = +x, CCW+
        if abs(dy) < EPS:
            cardinal = "E" if dx > 0 else "W"
        elif abs(dx) < EPS:
            cardinal = "N" if dy > 0 else "S"
        else:
            cardinal = None
        yield {
            "i": i,
            "p0": (x0, y0),
            "p1": (x1, y1),
            "vec": (dx, dy),
            "length": L,
            "unit": (ux, uy),
            "angle_deg": ang,
            "cardinal": cardinal,
        }


# ---------- Reflection triples ----------
def find_reflection_triples(
    verts: List[Point],
    internal_only: bool = False,
    allow_overlap: bool = True,
):
    """
    Return all triples [i, i+1, i+2] where:
      - edges i and i+2 are anti-parallel,
      - edge i+1 is perpendicular to both.

    If internal_only=True, require both turns to be reflex based on polygon orientation.
    """
    P = close_polygon(verts)
    segs = P[1:] - P[:-1]
    U = np.stack([unit(e) for e in segs], axis=0)
    m = len(U)

    ori = np.sign(signed_area(verts))  # +1 CCW, -1 CW (0 degenerate)
    groups, used = [], set()

    def turn_sign(u, v):
        return np.sign(u[0] * v[1] - u[1] * v[0])

    for i in range(m):
        j = (i + 1) % m
        k = (i + 2) % m
        u0, u1, u2 = U[i], U[j], U[k]

        cross02 = u0[0] * u2[1] - u0[1] * u2[0]
        dot02 = float(u0[0] * u2[0] + u0[1] * u2[1])
        antiparallel = almost_zero(cross02) and (dot02 < -0.999999 + 1e-6)

        perp01 = almost_zero(float(u0[0] * u1[0] + u0[1] * u1[1]))
        perp12 = almost_zero(float(u1[0] * u2[0] + u1[1] * u2[1]))

        if not (antiparallel and perp01 and perp12):
            continue

        if internal_only and ori != 0:
            s1 = turn_sign(u0, u1)
            s2 = turn_sign(u1, u2)
            inward = -ori  # CCW: right; CW: left
            if not (s1 == s2 == inward):
                continue

        if not allow_overlap and (i in used or j in used or k in used):
            continue

        groups.append([i, j, k])
        if not allow_overlap:
            used.update([i, j, k])

    return groups


# ---------- Bridges & rectangles (with inside filter) ----------
def compute_bridges_for_groups(verts: List[Point], groups: List[List[int]]) -> List[Dict[str, Any]]:
    """For each group [i,j,k], choose the shorter of edges i and k, project both endpoints to the other edge.
    Keep only if both cross-bridges are fully inside the polygon.
    """
    P = close_polygon(verts)
    out: List[Dict[str, Any]] = []

    for (i, j, k) in groups:
        Ai, Bi = P[i], P[i + 1]
        Aj, Bj = P[j], P[j + 1]
        Ak, Bk = P[k], P[k + 1]

        Li = seg_len(Ai, Bi)
        Lk = seg_len(Ak, Bk)

        if Li <= Lk:
            shorter_idx, longer_idx = i, k
            short_far, short_near = Ai, Bi     # Bi touches j
            A_long, B_long = Ak, Bk
        else:
            shorter_idx, longer_idx = k, i
            short_far, short_near = Bk, Ak     # Ak touches j
            A_long, B_long = Ai, Bi

        p_far, _, _  = project_point_to_segment(short_far, A_long, B_long)
        p_near, _, _ = project_point_to_segment(short_near, A_long, B_long)

        if not segment_inside_polygon(short_far, p_far, P):
            continue
        if not segment_inside_polygon(short_near, p_near, P):
            continue

        out.append({
            "triple": [i, j, k],
            "shorter_edge": shorter_idx,
            "longer_edge": longer_idx,
            "short_far": short_far,
            "short_near": short_near,
            "p_far": p_far,
            "p_near": p_near,
        })

    return out


def rectangles_from_bridges(verts: List[Point], bridges: List[Dict[str, Any]]):
    """Return list of quadrilaterals (rectangles) as 4×2 arrays in order:
    [short_near, short_far, p_far, p_near]."""
    rects = []
    for b in bridges:
        qn = b["short_near"]
        qf = b["short_far"]
        pf = b["p_far"]
        pn = b["p_near"]
        rect = np.vstack([qn, qf, pf, pn])
        rects.append(rect)
    return rects


# ---------- Pretty print ----------
def print_table(verts: List[Point]):
    rows = list(edge_info(verts))
    header = f"{'i':>2}  {'from':>12} -> {'to':<12}  {'len':>6}  {'unit_dir':>17}  {'angle°':>7}  {'card'}"
    print(header)
    print("-" * len(header))
    for r in rows:
        f = f"({float(r['p0'][0]):.3f}, {float(r['p0'][1]):.3f})"
        t = f"({float(r['p1'][0]):.3f}, {float(r['p1'][1]):.3f})"
        u = f"({float(r['unit'][0]):.3f}, {float(r['unit'][1]):.3f})"
        print(
            f"{r['i']:>2}  {f:>12} -> {t:<12}  "
            f"{r['length']:>6.3f}  {u:>17}  "
            f"{r['angle_deg']:>7.1f}  {r['cardinal'] or '-'}"
        )


# ---------- Overlap & partition helpers ----------
def rect_to_aabb(R: np.ndarray):
    xs, ys = R[:, 0], R[:, 1]
    return float(np.min(xs)), float(np.max(xs)), float(np.min(ys)), float(np.max(ys))


def _rect_from_xy(x0, x1, y0, y1):
    return np.vstack([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def find_overlapping_rectangles(rects: List[np.ndarray], tol: float = 1e-8):
    n = len(rects)
    if n == 0:
        return [False] * 0, []
    aabbs = []
    for R in rects:
        xs = R[:, 0]; ys = R[:, 1]
        aabbs.append((float(np.min(xs)), float(np.max(xs)), float(np.min(ys)), float(np.max(ys))))
    overlaps = [False] * n
    pairs = []
    for i in range(n):
        x1min, x1max, y1min, y1max = aabbs[i]
        for j in range(i + 1, n):
            x2min, x2max, y2min, y2max = aabbs[j]
            dx = min(x1max, x2max) - max(x1min, x2min)
            dy = min(y1max, y2max) - max(y1min, y2min)
            if dx > tol and dy > tol:
                overlaps[i] = overlaps[j] = True
                pairs.append((i, j))
    return overlaps, pairs


def compute_overlap_rectangles(rects: List[np.ndarray], tol: float = 1e-8):
    _, pairs = find_overlapping_rectangles(rects, tol=tol)
    overlaps_only: List[np.ndarray] = []
    for i, j in pairs:
        x1a, x1b, y1a, y1b = rect_to_aabb(rects[i])
        x2a, x2b, y2a, y2b = rect_to_aabb(rects[j])
        xa, xb = max(x1a, x2a), min(x1b, x2b)
        ya, yb = max(y1a, y2a), min(y1b, y2b)
        if xb - xa > tol and yb - ya > tol:
            overlaps_only.append(_rect_from_xy(xa, xb, ya, yb))
    return overlaps_only, pairs


def subtract_axis_aligned(R: np.ndarray, C: np.ndarray, tol: float = 1e-9) -> List[np.ndarray]:
    x1a, x1b, y1a, y1b = rect_to_aabb(R)
    x2a, x2b, y2a, y2b = rect_to_aabb(C)
    xa, xb = max(x1a, x2a), min(x1b, x2b)
    ya, yb = max(y1a, y2a), min(y1b, y2b)
    if xb - xa <= tol or yb - ya <= tol:
        return [R]
    out = []
    if xa - x1a > tol:
        out.append(_rect_from_xy(x1a, xa, y1a, y1b))
    if x1b - xb > tol:
        out.append(_rect_from_xy(xb, x1b, y1a, y1b))
    if ya - y1a > tol:
        out.append(_rect_from_xy(xa, xb, y1a, ya))
    if y1b - yb > tol:
        out.append(_rect_from_xy(xa, xb, yb, y1b))
    return out


def compute_trimmed_rectangles(rects: List[np.ndarray], tol: float = 1e-8):
    overlaps_only, pairs = compute_overlap_rectangles(rects, tol=tol)
    per_idx_overlaps: Dict[int, List[np.ndarray]] = {}
    for (i, j), ovl in zip(pairs, overlaps_only):
        per_idx_overlaps.setdefault(i, []).append(ovl)
        per_idx_overlaps.setdefault(j, []).append(ovl)
    trimmed: List[Tuple[np.ndarray, int]] = []
    for idx, R in enumerate(rects):
        if idx not in per_idx_overlaps:
            continue
        pieces = [R]
        for C in per_idx_overlaps[idx]:
            new_pieces = []
            for Prect in pieces:
                new_pieces.extend(subtract_axis_aligned(Prect, C, tol=tol))
            pieces = new_pieces
        for Prect in pieces:
            x0, x1, y0, y1 = rect_to_aabb(Prect)
            if (x1 - x0) > tol and (y1 - y0) > tol:
                trimmed.append((Prect, idx))
    return trimmed, pairs


def point_in_any_rect(qx: float, qy: float, rects: List[np.ndarray]) -> bool:
    for R in rects:
        x0, x1, y0, y1 = rect_to_aabb(R)
        if (x0 <= qx <= x1) and (y0 <= qy <= y1) and (x1 - x0) > 0 and (y1 - y0) > 0:
            return True
    return False


def collect_partition_rects(
    verts: List[Point],
    internal_only: bool = False,
    allow_overlap: bool = True,
):
    """Return rectangles for partitioning and their union cover pieces."""
    # Build rectangles from reflection groups
    groups_all = find_reflection_triples(verts, internal_only=internal_only, allow_overlap=allow_overlap)
    bridges = compute_bridges_for_groups(verts, groups_all)
    rects = rectangles_from_bridges(verts, bridges)

    # Overlap separation
    overlaps_only, pairs = compute_overlap_rectangles(rects)
    trimmed, _ = compute_trimmed_rectangles(rects)

    idxs_in_pairs = set()
    for i, j in pairs:
        idxs_in_pairs.add(i); idxs_in_pairs.add(j)
    nonoverlap_rects = [rects[i] for i in range(len(rects)) if i not in idxs_in_pairs]

    # Cover set = non-overlap originals + trimmed pieces + overlap pieces
    cover_rects = list(nonoverlap_rects) + [r for (r, _) in trimmed] + list(overlaps_only)
    return rects, nonoverlap_rects, overlaps_only, trimmed, cover_rects


def compute_leftover_polygons(
    verts: List[Point],
    internal_only: bool = False,
    allow_overlap: bool = True,
) -> List[np.ndarray]:
    """Original polygon minus union coverage by rectangles."""
    P = close_polygon(verts)
    _, _, _, _, cover_rects = collect_partition_rects(verts, internal_only=internal_only, allow_overlap=allow_overlap)

    xs = set(float(x) for x in P[:, 0])
    ys = set(float(y) for y in P[:, 1])
    for R in cover_rects:
        x0, x1, y0, y1 = rect_to_aabb(R)
        xs.update([x0, x1]); ys.update([y0, y1])
    xs = sorted(xs); ys = sorted(ys)
    if len(xs) < 2 or len(ys) < 2:
        return []

    leftover_cells: List[Tuple[int, int]] = []
    for i in range(len(xs) - 1):
        xmid = 0.5 * (xs[i] + xs[i + 1])
        for j in range(len(ys) - 1):
            ymid = 0.5 * (ys[j] + ys[j + 1])
            q = np.array([xmid, ymid], dtype=float)
            if point_in_polygon(q, P) and not point_in_any_rect(xmid, ymid, cover_rects):
                leftover_cells.append((i, j))

    if not leftover_cells:
        return []

    def edge_key(a: Tuple[float, float], b: Tuple[float, float]):
        return (a, b) if a < b else (b, a)

    boundary_edges: set = set()
    for (i, j) in leftover_cells:
        x0, x1 = xs[i], xs[i + 1]
        y0, y1 = ys[j], ys[j + 1]
        p00 = (x0, y0); p10 = (x1, y0); p11 = (x1, y1); p01 = (x0, y1)
        for (a, b) in [(p00, p10), (p10, p11), (p11, p01), (p01, p00)]:
            k = edge_key(a, b)
            if k in boundary_edges:
                boundary_edges.remove(k)
            else:
                boundary_edges.add(k)

    if not boundary_edges:
        return []

    from collections import defaultdict
    adj = defaultdict(list)
    for a, b in boundary_edges:
        adj[a].append(b); adj[b].append(a)

    used = set()
    polys: List[np.ndarray] = []

    def norm_e(u, v):
        return (u, v) if u < v else (v, u)

    for (a0, b0) in list(boundary_edges):
        k0 = norm_e(a0, b0)
        if k0 in used:
            continue
        start, prev = a0, a0
        curr = b0
        path = [start, curr]
        used.add(k0)
        while True:
            nbrs = adj[curr]
            nxt = nbrs[0] if nbrs[0] != prev else (nbrs[1] if len(nbrs) > 1 else None)
            if nxt is None:
                break
            k = norm_e(curr, nxt)
            if k in used:
                if nxt == start:
                    path.append(nxt); break
                if len(nbrs) > 1:
                    alt = nbrs[1] if nxt == nbrs[0] else nbrs[0]
                    k = norm_e(curr, alt); nxt = alt
                    if k in used:
                        break
            used.add(k); path.append(nxt)
            prev, curr = curr, nxt
            if nxt == start:
                break
        poly = np.array(path, dtype=float)
        if len(poly) >= 4:
            area = 0.5 * float(np.sum(poly[:-1, 0] * poly[1:, 1] - poly[1:, 0] * poly[:-1, 1]))
            if area < 0:
                poly = poly[::-1]
            polys.append(poly)

    return polys


# ---------- Merge rectangles into polygons (side-adjacent union) ----------
def union_axis_aligned_rects_to_polygons(rects: List[np.ndarray], tol: float = 1e-9) -> List[np.ndarray]:
    if not rects:
        return []

    xs = set(); ys = set(); boxes = []
    for R in rects:
        x0, x1, y0, y1 = rect_to_aabb(R)
        xs.update([x0, x1]); ys.update([y0, y1])
        boxes.append((x0, x1, y0, y1))
    xs = sorted(xs); ys = sorted(ys)
    if len(xs) < 2 or len(ys) < 2:
        return []

    covered = set()
    for i in range(len(xs) - 1):
        xmid = 0.5 * (xs[i] + xs[i + 1])
        for j in range(len(ys) - 1):
            ymid = 0.5 * (ys[j] + ys[j + 1])
            inside_any = False
            for (x0, x1, y0, y1) in boxes:
                if (x0 - tol) <= xmid <= (x1 + tol) and (y0 - tol) <= ymid <= (y1 + tol):
                    inside_any = True; break
            if inside_any:
                covered.add((i, j))
    if not covered:
        return []

    comps: List[List[Tuple[int, int]]] = []
    seen = set()
    for cell in list(covered):
        if cell in seen:
            continue
        stack = [cell]; seen.add(cell); comp = []
        while stack:
            ci, cj = stack.pop()
            comp.append((ci, cj))
            for di, dj in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nb = (ci + di, cj + dj)
                if nb in covered and nb not in seen:
                    seen.add(nb); stack.append(nb)
        comps.append(comp)

    def edge_key(a: Tuple[float, float], b: Tuple[float, float]):
        return (a, b) if a < b else (b, a)

    polys: List[np.ndarray] = []
    from collections import defaultdict
    for comp in comps:
        boundary_edges: set = set()
        for (i, j) in comp:
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]
            p00 = (x0, y0); p10 = (x1, y0); p11 = (x1, y1); p01 = (x0, y1)
            for (a, b) in [(p00, p10), (p10, p11), (p11, p01), (p01, p00)]:
                k = edge_key(a, b)
                if k in boundary_edges:
                    boundary_edges.remove(k)
                else:
                    boundary_edges.add(k)

        if not boundary_edges:
            continue

        adj = defaultdict(list)
        for a, b in boundary_edges:
            adj[a].append(b); adj[b].append(a)

        def norm_e(u, v):
            return (u, v) if u < v else (v, u)

        used = set()
        for (a0, b0) in list(boundary_edges):
            k0 = norm_e(a0, b0)
            if k0 in used:
                continue
            start, prev = a0, a0
            curr = b0
            path = [start, curr]
            used.add(k0)
            while True:
                nbrs = adj[curr]
                nxt = nbrs[0] if nbrs[0] != prev else (nbrs[1] if len(nbrs) > 1 else None)
                if nxt is None:
                    break
                k = norm_e(curr, nxt)
                if k in used:
                    if nxt == start:
                        path.append(nxt); break
                    if len(nbrs) > 1:
                        alt = nbrs[1] if nxt == nbrs[0] else nbrs[0]
                        k = norm_e(curr, alt); nxt = alt
                        if k in used:
                            break
                used.add(k); path.append(nxt)
                prev, curr = curr, nxt
                if nxt == start:
                    break
            poly = np.array(path, dtype=float)
            if len(poly) >= 4:
                area = 0.5 * float(np.sum(poly[:-1, 0] * poly[1:, 1] - poly[1:, 0] * poly[:-1, 1]))
                if area < 0:
                    poly = poly[::-1]
                polys.append(poly)

    return polys


def merge_partition_rects_into_polys(
    verts: List[Point], internal_only: bool = False, allow_overlap: bool = True
) -> List[np.ndarray]:
    _, _, _, _, cover_rects = collect_partition_rects(verts, internal_only=internal_only, allow_overlap=allow_overlap)
    return union_axis_aligned_rects_to_polygons(cover_rects)


# ---------- Dot-matrix helpers ----------
def strictly_inside_poly(p: np.ndarray, poly: np.ndarray, margin: float = 1e-9) -> bool:
    """Inside and at least `margin` away from boundary."""
    if not point_in_polygon(p, poly):
        return False
    return point_to_polygon_min_dist(p, poly) > margin


def matrix_points_in_poly(
    poly: np.ndarray,
    origin: Tuple[float, float],
    spacing: Union[float, Tuple[float, float]] = 1.0,
    margin: float = 1e-9,
) -> List[np.ndarray]:
    """
    Build a grid of points centred on `origin` with spacing (sx, sy),
    keeping only those strictly inside `poly` (>= margin from edges).
    """
    if isinstance(spacing, (tuple, list)) and len(spacing) == 2:
        sx, sy = float(spacing[0]), float(spacing[1])
    else:
        sx = sy = float(spacing)
    if sx <= 0 or sy <= 0:
        raise ValueError("spacing must be > 0 (float) or (sx, sy) with both > 0.")

    ox, oy = float(origin[0]), float(origin[1])
    xs, ys = poly[:, 0], poly[:, 1]
    xmin, xmax = float(np.min(xs)), float(np.max(xs))
    ymin, ymax = float(np.min(ys)), float(np.max(ys))

    nx_neg = int(math.floor((ox - xmin) / sx))
    nx_pos = int(math.floor((xmax - ox) / sx))
    ny_neg = int(math.floor((oy - ymin) / sy))
    ny_pos = int(math.floor((ymax - oy) / sy))

    pts: List[np.ndarray] = []
    for ix in range(-nx_neg, nx_pos + 1):
        px = ox + ix * sx
        for iy in range(-ny_neg, ny_pos + 1):
            py = oy + iy * sy
            p = np.array([px, py], dtype=float)
            if strictly_inside_poly(p, poly, margin=margin):
                pts.append(p)
    return pts


# ---------- Plot: separated pieces (post-overlap) with dot matrices ----------
def plot_separated_pieces_with_dot_matrices(
    verts: List[Point],
    internal_only: bool = False,
    allow_overlap: bool = True,
    face_alpha: float = 0.30,
    edge_width: float = 2.0,
    # dot controls
    dot_spacing: Union[float, Tuple[float, float]] = 1.0,
    dot_margin: float = 1e-9,
    dot_ms: float = 4.0,
    show_piece_index: bool = True,
):
    """
    Draw dot matrices for the partition **after** overlap separation:
      - Uses the 'cover' set = non-overlap originals + trimmed remainders + explicit overlap rectangles.
      - Each piece gets its own centroid-anchored dot matrix, strictly inside that piece.
    """
    # Separated cover pieces
    _, _, _, _, cover_rects = collect_partition_rects(
        verts, internal_only=internal_only, allow_overlap=allow_overlap
    )

    P = close_polygon(verts)
    fig, ax = plt.subplots(figsize=(10, 6))

    # Outline original polygon
    ax.plot(P[:, 0], P[:, 1], "-o", color=(0, 0, 0, 0.35), linewidth=2.0, markersize=4, zorder=1)

    cmap = plt.get_cmap("tab20")

    for i, R in enumerate(cover_rects):
        col = cmap(i % 20)
        Rpoly = close_polygon(R)

        # draw the separated piece
        ax.add_patch(
            Polygon(R, closed=True, edgecolor=col,
                    facecolor=(col[0], col[1], col[2], face_alpha),
                    linewidth=edge_width, zorder=2)
        )

        # centroid origin
        origin = np.mean(R, axis=0)

        # dots strictly inside the piece
        pts = matrix_points_in_poly(
            Rpoly, (float(origin[0]), float(origin[1])),
            spacing=dot_spacing, margin=dot_margin
        )
        if pts:
            ds = np.array(pts, dtype=float)
            ax.plot(ds[:, 0], ds[:, 1], linestyle="none", marker="o", ms=dot_ms,
                    mfc="black", mec="black", mew=0.0, zorder=3)

        # optional markers
        ax.plot(origin[0], origin[1], marker='x', ms=6, mec='black', mfc='none', mew=1.0, zorder=4)
        if show_piece_index:
            ax.text(float(origin[0]), float(origin[1]), f" {i}", fontsize=9, color='black',
                    va='center', ha='left', zorder=5)

    # axes & labels
    ax.set_aspect("equal", adjustable="box")
    pad = max(1.0, 0.05 * max(np.ptp(P[:, 0]), np.ptp(P[:, 1])))
    ax.set_xlim(P[:, 0].min() - pad, P[:, 0].max() + pad)
    ax.set_ylim(P[:, 1].min() - pad, P[:, 1].max() + pad)
    ax.grid(True, linewidth=0.5, alpha=0.3)
    ax.set_title("Separated pieces (post-overlap) — centroid‑anchored dot matrices")
    ax.text(0.01, 0.01, f"pieces: {len(cover_rects)}",
            transform=ax.transAxes, fontsize=9, alpha=0.85, va="bottom")

    plt.show()


# ---------- Optional: other plots kept for convenience ----------
def plot_rects_with_dot_matrices(
    verts: List[Point],
    internal_only: bool = False,
    allow_overlap: bool = True,
    which: str = "original",     # "original" (raw) or "cover" (trimmed+overlaps)
    face_alpha: float = 0.30,
    edge_width: float = 2.0,
    dot_spacing: Union[float, Tuple[float, float]] = 1.0,
    dot_margin: float = 1e-9,
    dot_ms: float = 4.0,
):
    groups_all = find_reflection_triples(verts, internal_only=internal_only, allow_overlap=allow_overlap)
    bridges = compute_bridges_for_groups(verts, groups_all)
    raw_rects = rectangles_from_bridges(verts, bridges)
    _, _, _, _, cover_rects = collect_partition_rects(verts, internal_only=internal_only, allow_overlap=allow_overlap)

    if which == "original":
        rects = raw_rects; title_tag = "Raw rectangles (pre‑merge)"
    elif which == "cover":
        rects = cover_rects; title_tag = "Cover rectangles (trimmed + overlaps)"
    else:
        raise ValueError('which must be "original" or "cover".')

    P = close_polygon(verts)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(P[:, 0], P[:, 1], "-o", color=(0, 0, 0, 0.35), linewidth=2.0, markersize=4, zorder=1)

    cmap = plt.get_cmap("tab20")

    for i, R in enumerate(rects):
        col = cmap(i % 20)
        Rpoly = close_polygon(R)

        ax.add_patch(
            Polygon(R, closed=True, edgecolor=col,
                    facecolor=(col[0], col[1], col[2], face_alpha),
                    linewidth=edge_width, zorder=2)
        )

        origin = np.mean(R, axis=0)
        pts = matrix_points_in_poly(Rpoly, (float(origin[0]), float(origin[1])),
                                    spacing=dot_spacing, margin=dot_margin)
        if pts:
            ds = np.array(pts, dtype=float)
            ax.plot(ds[:, 0], ds[:, 1], linestyle="none", marker="o", ms=dot_ms,
                    mfc="black", mec="black", mew=0.0, zorder=3)

        ax.plot(origin[0], origin[1], marker='x', ms=6, mec='black', mfc='none', mew=1.0, zorder=4)

    ax.set_aspect("equal", adjustable="box")
    pad = max(1.0, 0.05 * max(np.ptp(P[:, 0]), np.ptp(P[:, 1])))
    ax.set_xlim(P[:, 0].min() - pad, P[:, 0].max() + pad)
    ax.set_ylim(P[:, 1].min() - pad, P[:, 1].max() + pad)
    ax.grid(True, linewidth=0.5, alpha=0.3)
    ax.set_title(f"{title_tag} — centroid‑anchored dot matrices")
    ax.text(0.01, 0.01, f"rectangles: {len(rects)}",
            transform=ax.transAxes, fontsize=9, alpha=0.85, va="bottom")

    plt.show()


def plot_polygon(
    verts: List[Point],
    arrow_frac: float = 0.25,
    show_lengths: bool = False,
    colour_mode: str = "reflection_groups",  # 'edges' or 'reflection_groups'
    internal_only: bool = False,
    allow_overlap: bool = True,
    draw_bridges: bool = True,
):
    P = close_polygon(verts)
    rows = list(edge_info(verts))
    segments = np.array([[r["p0"], r["p1"]] for r in rows], dtype=float)
    cmap = plt.get_cmap("tab20")

    if colour_mode == "edges":
        colours = [cmap(i % 20) for i in range(len(rows))]
        legend_note = "Unique colour per edge"
        bridges = []
        groups_filtered = []
    else:
        groups_all = find_reflection_triples(verts, internal_only=internal_only, allow_overlap=allow_overlap)
        bridges = compute_bridges_for_groups(verts, groups_all)
        groups_filtered = [b["triple"] for b in bridges]
        colours = [(0, 0, 0, 0.15)] * len(rows)
        for gi, grp in enumerate(groups_filtered):
            col = cmap(gi % 20)
            for idx in grp:
                colours[idx] = col
        legend_note = f"Reflection groups kept ({len(groups_filtered)}) — indices {groups_filtered}"

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(P[:, 0], P[:, 1], color=(0, 0, 0, 0.15), linewidth=1.0, zorder=1)
    lc = LineCollection(segments, colors=colours, linewidths=3.0, zorder=2)
    ax.add_collection(lc)

    for i, r in enumerate(rows):
        x0, y0 = r["p0"]; x1, y1 = r["p1"]
        L = r["length"]; ux, uy = r["unit"]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        half = 0.5 * arrow_frac * L
        start = (mx - half * ux, my - half * uy)
        end = (mx + half * ux, my + half * uy)
        ax.add_patch(
            FancyArrowPatch(posA=start, posB=end, arrowstyle="-|>", mutation_scale=12,
                            linewidth=2.0, color=colours[i], zorder=3)
        )
        if show_lengths:
            nx, ny = -uy, ux
            ax.text(mx + 0.05 * L * nx, my + 0.05 * L * ny, f"{L:.2f}",
                    fontsize=9, ha="center", va="center", color=colours[i], zorder=4)

    if draw_bridges and groups_filtered:
        for gi, b in enumerate(bridges):
            col = cmap(gi % 20)
            qf, pf = b["short_far"], b["p_far"]
            ax.plot([qf[0], pf[0]], [qf[1], pf[1]], linestyle="--", linewidth=2.5, color=col, zorder=4)
            ax.plot(qf[0], qf[1], marker="o", ms=6, color=col, zorder=5)
            ax.plot(pf[0], pf[1], marker="s", ms=5, color=col, zorder=5)

    ax.plot(P[:, 0], P[:, 1], "o", ms=4, color="black", zorder=5)
    ax.set_aspect("equal", adjustable="box")
    pad = max(1.0, 0.05 * max(np.ptp(P[:, 0]), np.ptp(P[:, 1])))
    ax.set_xlim(P[:, 0].min() - pad, P[:, 0].max() + pad)
    ax.set_ylim(P[:, 1].min() - pad, P[:, 1].max() + pad)
    ax.grid(True, linewidth=0.5, alpha=0.3)
    ax.set_title("Reflection groups (filtered) + bridges")
    ax.text(0.01, 0.01, legend_note, transform=ax.transAxes, fontsize=9, alpha=0.8, va="bottom")
    plt.show()


# ---------- Demo ----------
if __name__ == "__main__":
    vertices: List[Point] = [
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

    print_table(vertices)

    # --- Draw dots AFTER overlap separation (requested) ---
    plot_separated_pieces_with_dot_matrices(
        vertices,
        internal_only=False,
        allow_overlap=True,
        face_alpha=0.30,
        edge_width=2.0,
        dot_spacing=1.5,   # or (1.5, 1.0) for rectangular spacing
        dot_margin=1e-6,
        dot_ms=4.5,
        show_piece_index=True,
    )

    # # (Optional) See raw rectangles or cover pieces with dots:
    # plot_rects_with_dot_matrices(
    #     vertices,
    #     which="cover",  # "original" or "cover"
    #     dot_spacing=1.5,
    #     dot_margin=1e-6,
    #     dot_ms=4.5,
    # )
