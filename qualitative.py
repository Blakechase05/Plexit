"""Qualitative review of a light layout, judged by Claude.

Claude looks at the rendered layout (image + exact geometry), says whether it
looks acceptable, and nominates which rectangles should share a light grid.
This module then applies those nominations geometrically and renders a
before/after comparison.

Division of labour: Claude decides WHAT is wrong and WHICH rectangles belong on
a shared grid; the code works out the exact coordinates. An LLM cannot read
sub-pixel positions off a PNG, so it is given the real numbers as text too and
never asked to emit coordinates itself.

    python qualitative.py e-shape
    python qualitative.py complex --offline    # skip the API, align every seam
"""

import base64
import io
import json
import math
import sys

import matplotlib.pyplot as plt
from matplotlib.path import Path

from plot import createPolygon, cutPolyPath, getBounds
from partition import dividePolygon
from merge import merge_optimal_fast
from lights import _axis

# Cost weights for the shared-lattice search (see solveSharedAxis).
W_CENTRE = 0.5   # keep each run centred in its rectangle
W_WALL   = 3.0   # keep wall gaps close to the light-to-light pitch
W_PITCH  = 0.25  # keep the pitch close to the requested spacing

MODEL = "claude-opus-5"
FALLBACK_MODEL = "claude-opus-4-8"
TOL = 1e-9


# ─── review schema ───────────────────────────────────────────────────────────
# align_groups is the actionable part: Claude names rectangles by index and the
# axis they should share. Everything else is commentary shown to the user.
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ok", "needs_work"]},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["error", "spacing", "alignment", "aesthetic"],
                    },
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "where": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["category", "severity", "where", "description"],
                "additionalProperties": False,
            },
        },
        "align_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "axis": {"type": "string", "enum": ["rows", "columns"]},
                    "rect_indices": {"type": "array", "items": {"type": "integer"}},
                    "reason": {"type": "string"},
                },
                "required": ["axis", "rect_indices", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "summary", "issues", "align_groups"],
    "additionalProperties": False,
}

SYSTEM = """\
You are reviewing an automatically generated lighting layout for a rectilinear \
floor plan. The plan is partitioned into axis-aligned rectangles and each \
rectangle is given a grid of lights.

Judge three things:

1. Errors - lights outside the floor plan, lights on top of each other, a \
rectangle with no lights, anything geometrically wrong.
2. Visual quality - is the result something a lighting designer would sign off? \
Look for lopsided runs, lonely lights, gaps that read as holes, density that \
jumps between neighbouring areas.
3. Alignment across partition boundaries - THIS IS THE MAIN ONE. The rectangles \
are an artefact of how the floor was subdivided, not real walls. A light in a \
big rectangle should generally line up with the lights in a neighbouring \
rectangle, so rows and columns run straight through the whole plan instead of \
breaking at every seam.

For each set of rectangles that should share a grid, add an align_groups entry. \
Use axis "rows" to make the y positions line up (rectangles sitting side by \
side) and "columns" to make the x positions line up (rectangles stacked one \
above the other). Group as many rectangles together as genuinely should align - \
a group of three or four is normal and better than several overlapping pairs.

Only leave align_groups empty if the layout genuinely needs no alignment work. \
Do not invent coordinates; refer to rectangles by their index.

HARD CONSTRAINT: the number of lights in each rectangle is fixed. Alignment \
shifts lights and re-spaces them evenly; it never adds or removes one. Never \
recommend adding or removing lights to make something look better - a \
rectangle that reads as under-lit or over-lit is not grounds for changing its \
count. Report a count as wrong ONLY under category "error", and only for a \
genuine fault: a rectangle with no lights at all, lights outside the floor \
plan, or duplicates stacked on one point. Every aesthetic issue you raise \
must be fixable by moving existing lights.\
"""


# ─── geometry the model is given alongside the picture ───────────────────────

def geometryReport(points, rects, perRect):
    """Exact numbers for Claude, so it never has to measure from the image."""
    out = [f"Polygon vertices (counter-clockwise): {points}", ""]
    out.append(f"{len(rects)} rectangles after merging:")
    for i, (r, pts) in enumerate(zip(rects, perRect)):
        (x0, y0), (x1, y1) = r
        xs = sorted({p[0] for p in pts})
        ys = sorted({p[1] for p in pts})
        out.append(
            f"  [{i}] ({x0},{y0})-({x1},{y1})  {len(pts)} lights"
            f"  columns x={_fmt(xs)}  rows y={_fmt(ys)}"
        )

    out.append("")
    out.append("Shared edges between rectangles:")
    adj = adjacency(rects)
    if not adj:
        out.append("  none")
    for i, j, axis in adj:
        out.append(f"  [{i}] and [{j}] share an edge -> their {axis} could align")
    return "\n".join(out)


def _fmt(vals):
    return "[" + ", ".join(f"{v:g}" for v in vals) + "]"


# ─── adjacency ───────────────────────────────────────────────────────────────

def adjacency(rects):
    """Pairs of rectangles sharing an edge of non-zero length.

    A shared VERTICAL edge means the rectangles sit side by side, so it is their
    rows (y positions) that ought to line up - and vice versa.
    """
    pairs = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            (ax0, ay0), (ax1, ay1) = rects[i]
            (bx0, by0), (bx1, by1) = rects[j]

            touchX = abs(ax1 - bx0) < TOL or abs(bx1 - ax0) < TOL
            overlapY = min(ay1, by1) - max(ay0, by0)
            if touchX and overlapY > TOL:
                pairs.append((i, j, "rows"))

            touchY = abs(ay1 - by0) < TOL or abs(by1 - ay0) < TOL
            overlapX = min(ax1, bx1) - max(ax0, bx0)
            if touchY and overlapX > TOL:
                pairs.append((i, j, "columns"))
    return pairs


def _union(groups):
    """Merge overlapping index sets (union-find, small n so keep it obvious)."""
    merged = []
    for g in groups:
        g = set(g)
        hit = [m for m in merged if m & g]
        for m in hit:
            merged.remove(m)
            g |= m
        merged.append(g)
    return [sorted(g) for g in merged]


# ─── the snap + re-space solver ──────────────────────────────────────────────

def _bestRun(lo, hi, n, pitch, anchor):
    """n consecutive lattice points sitting inside (lo, hi), as centred as possible.

    The count is fixed by the caller, so this never invents or drops a light -
    it only chooses WHICH consecutive run of the shared lattice to occupy.
    Returns None if n points at this pitch cannot fit inside the span.
    """
    if n <= 0:
        return []
    width = (n - 1) * pitch
    if width >= (hi - lo) - 2 * TOL:
        return None

    kmin = int(math.ceil((lo - anchor) / pitch + TOL))
    kmax = int(math.floor((hi - width - anchor) / pitch - TOL))
    if kmin > kmax:
        return None

    best = None
    for k in range(kmin, kmax + 1):
        first = anchor + k * pitch
        lead = first - lo
        trail = hi - (first + width)
        cost = (lead - trail) ** 2          # centre the run in the rectangle
        if best is None or cost < best[0]:
            best = (cost, [first + i * pitch for i in range(n)])
    return best[1]


def solveSharedAxis(spans, counts, spacing, pitchSteps=61, phaseSteps=60):
    """One pitch and one phase for a whole group, keeping every light count.

    Sweeps pitch and phase; for each candidate lattice every rectangle takes the
    best-centred run of its OWN existing number of lights. A candidate is only
    valid if every rectangle can still fit its full count, so alignment can
    never change how many lights a rectangle has - it only shifts them and
    re-spaces them evenly.

    Pitch is capped at the target spacing so a run never becomes coarser than
    asked for. Returns a list of position lists, or None if no shared lattice
    fits every rectangle's existing count.
    """
    origin = min(lo for lo, _ in spans)
    best = None

    for pi in range(pitchSteps):
        pitch = spacing * (0.4 + 0.6 * pi / (pitchSteps - 1))
        for qi in range(phaseSteps):
            anchor = origin + pitch * qi / phaseSteps
            runs = []
            cost = 0.0
            for (lo, hi), n in zip(spans, counts):
                run = _bestRun(lo, hi, n, pitch, anchor)
                if run is None:
                    break
                lead, trail = run[0] - lo, hi - run[-1]
                cost += W_CENTRE * (lead - trail) ** 2
                cost += W_WALL * ((lead - pitch) ** 2 + (trail - pitch) ** 2)
                runs.append(run)
            if len(runs) != len(spans):
                continue
            cost += W_PITCH * len(spans) * (spacing - pitch) ** 2
            if best is None or cost < best[0]:
                best = (cost, runs)

    return None if best is None else best[1]


def alignedLayout(rects, spacing, alignGroups):
    """Lights per rectangle, with the nominated groups sharing a lattice.

    Every rectangle keeps exactly the number of lights the plain per-rectangle
    layout gave it. Groups that cannot be aligned without changing a count are
    left alone rather than gaining or losing lights.
    """
    axisIndex = {"columns": 0, "rows": 1}

    # baseline: the counts we are required to preserve
    baseline = {}
    for i, ((x0, y0), (x1, y1)) in enumerate(rects):
        baseline[(i, "columns")] = _axis(x0, x1, spacing)
        baseline[(i, "rows")] = _axis(y0, y1, spacing)

    positions = dict(baseline)
    skipped = []

    for axis in ("rows", "columns"):
        raw = [g for a, g in alignGroups if a == axis]
        for group in _union(raw):
            k = axisIndex[axis]
            spans = [(rects[i][0][k], rects[i][1][k]) for i in group]
            counts = [len(baseline[(i, axis)]) for i in group]
            runs = solveSharedAxis(spans, counts, spacing)
            if runs is None:
                skipped.append((axis, group))
                continue
            for i, run in zip(group, runs):
                positions[(i, axis)] = run

    for axis, group in skipped:
        print(f"  note: {axis} for rects {group} left unaligned"
              f" - no shared lattice fits without changing a light count")

    return [[(x, y) for x in positions[(i, "columns")]
                    for y in positions[(i, "rows")]]
            for i in range(len(rects))]



# ─── rendering ───────────────────────────────────────────────────────────────

def drawLayout(ax, points, rects, perRect, title):
    for (x0, y0), (x1, y1) in rects:
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0,
                                   fill=False, edgecolor='g', linewidth=1.4))
    ax.add_patch(createPolygon(points, edgecolor='r', fill=None))

    pts = [p for group in perRect for p in group]
    if pts:
        xs, ys = zip(*pts)
        ax.plot(xs, ys, 'o', color='orange', markeredgecolor='k',
                markersize=6, linestyle='none', zorder=5)

    xl, yl = getBounds(points)
    ax.set_xlim(xl)
    ax.set_ylim(yl)
    ax.set_aspect('equal', adjustable='box')
    ax.set_title(title, fontsize=10)


def renderPng(points, rects, perRect, title):
    """Single layout as PNG bytes, for sending to Claude."""
    fig, ax = plt.subplots(figsize=(7, 6))
    drawLayout(ax, points, rects, perRect, title)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight')
    plt.close(fig)
    return buf.getvalue()


def beforeAfter(points, rects, before, after, shape, outPath):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8))
    drawLayout(axes[0], points, rects, before,
               f"BEFORE - {sum(len(g) for g in before)} lights, per-rectangle grids")
    drawLayout(axes[1], points, rects, after,
               f"AFTER - {sum(len(g) for g in after)} lights, shared grids")
    fig.suptitle(f"{shape} - qualitative review", fontsize=12)
    fig.tight_layout()
    fig.savefig(outPath, dpi=110, bbox_inches='tight')
    return fig


# ─── Claude ──────────────────────────────────────────────────────────────────

def _send(client, kwargs):
    """One request, with refusal fallbacks and a retry if they are unavailable."""
    import anthropic

    try:
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": FALLBACK_MODEL}],
            **kwargs,
        )
    except anthropic.BadRequestError as e:
        # Fallbacks are Claude API only and not enabled on every account. The
        # review does not depend on them, so drop them and try again.
        print(f"  (refusal fallbacks unavailable: {e.message}; retrying without)")
        return client.messages.create(**kwargs)


def reviewWithClaude(pngBytes, geometry, shape):
    """Ask Claude to judge the layout and nominate alignment groups."""
    import anthropic

    client = anthropic.Anthropic()
    image = base64.standard_b64encode(pngBytes).decode("utf-8")

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image},
            },
            {
                "type": "text",
                "text": (
                    f"Shape: {shape}\n\n{geometry}\n\n"
                    "Review this lighting layout. The image shows the floor plan "
                    "outline in red, the partition rectangles in green, and the "
                    "lights as orange dots."
                ),
            },
        ],
    }]

    kwargs = dict(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        messages=messages,
        output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
    )

    try:
        response = _send(client, kwargs)
    except TypeError as e:
        if "authentication" not in str(e).lower():
            raise
        raise SystemExit("""No Anthropic credentials found.
  Either run `ant auth login`, or export ANTHROPIC_API_KEY.
  To exercise the alignment fix without any API call, add --offline.""")
    except anthropic.AuthenticationError:
        raise SystemExit("""API key rejected (401).
  The value should start with sk-ant- exactly ONCE - a doubled prefix is the
  usual cause. A real key is about 108 characters.
  Check its length and prefix before re-pasting it.
  A real key is about 108 characters long.""")
    except anthropic.PermissionDeniedError:
        raise SystemExit("API key lacks permission for this model (403).")
    except anthropic.RateLimitError as e:
        wait = e.response.headers.get("retry-after", "60")
        raise SystemExit(f"Rate limited (429). Retry after {wait}s.")
    except anthropic.APIConnectionError:
        raise SystemExit("Could not reach the API - check network or proxy.")
    except anthropic.APIStatusError as e:
        raise SystemExit(f"API error {e.status_code}: {e.message}")

    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        raise RuntimeError(f"Claude declined the review: {detail}")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def printReview(review):
    print(f"\nVerdict: {review['verdict']}")
    print(f"  {review['summary']}")
    if review["issues"]:
        print("\nIssues:")
        for it in review["issues"]:
            print(f"  [{it['severity']}/{it['category']}] {it['where']}")
            print(f"      {it['description']}")
    if review["align_groups"]:
        print("\nAlignment groups Claude asked for:")
        for g in review["align_groups"]:
            print(f"  {g['axis']:8s} rects {g['rect_indices']} - {g['reason']}")


# ─── driver ──────────────────────────────────────────────────────────────────

def buildLayout(points, spacing):
    """Partition, merge, and lay out lights the current (per-rectangle) way."""
    polyPath = Path(list(points) + [points[0]], closed=True)
    polySides = cutPolyPath(points)
    rects = dividePolygon(points, polyPath, polySides,
                          ax=None, return_rectangles=True)
    rects = merge_optimal_fast(rects, verbose=False)
    perRect = [[(x, y) for x in _axis(r[0][0], r[1][0], spacing)
                       for y in _axis(r[0][1], r[1][1], spacing)] for r in rects]
    return rects, perRect


def runShape(shape, points, spacing, offline):
    """Build the layout, decide the alignment groups, apply them."""
    rects, before = buildLayout(points, spacing)
    print(f"{shape}: {len(rects)} rectangles, "
          f"{sum(len(g) for g in before)} lights before review")

    if offline:
        # Test path for the geometry - aligns every shared edge, no API call.
        groups = [(axis, [i, j]) for i, j, axis in adjacency(rects)]
        print(f"  [offline] aligning all {len(groups)} shared edges")
    else:
        png = renderPng(points, rects, before, f"{shape} - current layout")
        print(f"  asking {MODEL} to review ({len(png)} byte image)...")
        review = reviewWithClaude(png, geometryReport(points, rects, before), shape)
        printReview(review)
        groups = [(g["axis"], g["rect_indices"]) for g in review["align_groups"]]
        if not groups:
            print("  Claude found nothing to align - layout unchanged.")

    after = alignedLayout(rects, spacing, groups)
    out = f"qualitative-{shape}.png"
    beforeAfter(points, rects, before, after, shape, out)
    print(f"  before {sum(len(g) for g in before)} lights"
          f" -> after {sum(len(g) for g in after)} lights   wrote {out}")
    return out


def main(argv):
    from main import SHAPES, LIGHT_SPACING

    args = [a for a in argv[1:] if not a.startswith("-")]
    offline = "--offline" in argv

    if "--all" in argv:
        for shape, points in SHAPES.items():
            runShape(shape, points, LIGHT_SPACING, offline)
            plt.close("all")
        print()
        print(f"Wrote {len(SHAPES)} before/after comparisons.")
        return 0

    shape = args[0] if args else "e-shape"
    if shape not in SHAPES:
        print(f"Unknown shape {shape!r}. Available: {', '.join(SHAPES)}")
        return 1

    runShape(shape, SHAPES[shape], LIGHT_SPACING, offline)
    plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
