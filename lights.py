"""Light placement inside the merged rectangles.

This is the rectangle-only version of generateLatticePoints() from the fdf
generator. Because every rectangle here is axis-aligned the whole thing is
arithmetic on the corners - no shapely buffer(), no containment test, no
dropped points.

Spacing rule: the gap from a light to the wall is the SAME as the gap between
two lights. So a span holding n lights is cut into n+1 equal gaps, and there is
no separate wall margin - the margin IS the spacing.

    |<-g->o<-g->o<-g->o<-g->|      span = 4g, n = 3

GUARDRAIL: light COUNT and light POSITION are kept as two separate steps on
purpose. `_axisCount()` is the ONLY function in this codebase allowed to
decide how many lights go on an axis - touch it only to fix an actual bug
(wrong rounding, wrong minimum, an off-by-one). `_axisPositions()` just places
a count it's given; it can never add or drop a light, so every aesthetic
request - recentring, evening out spacing, aligning across a partition seam -
belongs there instead. Never fold a "make it look nicer" change back into
_axisCount().
"""

import math


def lightsInRect(rect, spacing):
    """Lights inside one rectangle, evenly spaced from each other and the walls.

    `spacing` is the target/maximum gap. The actual gap shrinks to whatever
    divides the span evenly, so it is never wider than `spacing`. Each axis is
    solved independently, so a rectangle that is not the same shape in x and y
    can end up with a slightly different pitch per axis - that is unavoidable
    if the wall gap has to match the light gap on both axes at once.
    """
    (x0, y0), (x1, y1) = rect
    # normalise in case a rectangle ever arrives with its corners the other way
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)

    return [(x, y) for x in _axis(x0, x1, spacing)
                   for y in _axis(y0, y1, spacing)]


def _axis(lo, hi, spacing):
    """Evenly spaced positions along one axis, walls included in the spacing.

    Thin wrapper: decide the count once (_axisCount), then place that many
    positions (_axisPositions). Kept as the entry point other modules already
    import - the split below is what actually enforces the guardrail.
    """
    n = _axisCount(hi - lo, spacing)
    return _axisPositions(lo, hi, n)


def _axisCount(span, spacing):
    """Decide HOW MANY lights fit on one axis.

    *** STRUCTURAL - only touch this to fix an actual bug. ***
    n lights make n+1 gaps, so pick the fewest gaps that keeps each one no
    wider than `spacing`. This is the single place in the codebase that fixes
    a light count; nothing downstream of it is allowed to add or remove one.
    """
    if span <= 0:
        return 1

    # -1e-9 so a span that divides exactly (span=10, spacing=5) gives 2 gaps,
    # not 3. Never fewer than 2 gaps, i.e. always at least one light.
    gaps = max(2, math.ceil(span / spacing - 1e-9))
    return gaps - 1


def _axisPositions(lo, hi, n):
    """Place a FIXED count `n` of lights evenly along [lo, hi].

    *** AESTHETIC - safe to edit. *** Given `n`, this only decides where those
    n lights sit; it can never invent or drop one. This is where "shift them,"
    "space them evenly," "recentre this row" type changes belong.
    """
    span = hi - lo
    if span <= 0 or n <= 0:
        return [(lo + hi) / 2.0]

    gaps = n + 1
    g = span / gaps
    return [lo + g * (i + 1) for i in range(n)]


def actualGaps(rect, points):
    """The realised gap per axis for one rectangle - span / (lights + 1)."""
    (x0, y0), (x1, y1) = rect
    nx = len(set(p[0] for p in points))
    ny = len(set(p[1] for p in points))
    gx = abs(x1 - x0) / (nx + 1) if nx else 0.0
    gy = abs(y1 - y0) / (ny + 1) if ny else 0.0
    return gx, gy


def layoutLights(rectangles, spacing):
    """Run lightsInRect over every rectangle.

    Returns (allPoints, perRect) so callers can either scatter the lot or report
    the count rectangle by rectangle.
    """
    perRect = [lightsInRect(r, spacing) for r in rectangles]
    allPoints = [p for pts in perRect for p in pts]
    return allPoints, perRect
