#!/usr/bin/env python3
"""
insert_image_fdf.py
-------------------
Read an FDF containing polygon annotations, find each polygon’s centroid,
and output a new FDF that embeds an image (SquareImage annotation) at every
centroid.  Image size is based on a real‑world dimension and drawing scale.

Tested with Bluebeam Revu 21.
"""

import os
import re
import sys
import textwrap
from pathlib import Path
from typing import List, Tuple
from io import BytesIO
from PIL import Image   # pip install pillow

# ────────────────────────────── user inputs ────────────────────────────── #
polyFdf          = "25111-PLX-SKT-MD-Schematic Design_03.fdf"
pdfName          = "25111-PLX-SKT-MD-Schematic Design_03.pdf"
imagePath        = "Light.png"
page             = 1                     # 1‑based page number in the PDF
pageSizeMm       = (210, 297)            # A4 portrait (unused for now)
scale            = 50                   # 1 : 50 drawing scale
realObjectSizeMm = (250, 250)            # real object = 250 mm × 250 mm
DPI = 1000.0  # Higher DPI = better image clarity
# ───────────────────────────────────────────────────────────────────────── #

# ── helpers ──────────────────────────────────────────────────────────────
def mmToPt(mm: float) -> float:
    return mm * 72 / 25.4                # 1 inch = 72 pt = 25.4 mm

def calculateScaledSizePt(realMm: Tuple[float, float],
                           scale: float) -> Tuple[float, float]:
    """Convert real‑world mm to drawing‑size points given a scale (1:scale)."""
    widthMm  = realMm[0] / scale
    heightMm = realMm[1] / scale
    return mmToPt(widthMm), mmToPt(heightMm)

def resizeImageToPt(path: str,
                    targetSizePt: Tuple[float, float]) -> Tuple[int, int, bytes]:
    """
    Resize *path* to *targetSizePt* (points) assuming 72 dpi,
    return widthPx, heightPx, and the JPEG‑encoded bytes.
    """

    widthPx   = round(targetSizePt[0] * DPI / 72)
    heightPx  = round(targetSizePt[1] * DPI / 72)
    with Image.open(path) as img:
        resized = img.resize((widthPx, heightPx), Image.LANCZOS).convert("RGB")
        buf = BytesIO()
        resized.save(buf, format="JPEG", quality=85)
        return widthPx, heightPx, buf.getvalue()

def extractPolyPoints(fdfPath: str) -> List[List[Tuple[float, float]]]:
    if not os.path.isfile(fdfPath):
        sys.exit(f"❌  Cannot find file “{fdfPath}”")
    with open(fdfPath, "r", encoding="latin-1") as f:
        content = f.read()

    polys = []
    for block in re.findall(r"/Vertices\s*\[([^\]]+)\]", content):
        try:
            nums = list(map(float, block.strip().split()))
            polys.append(list(zip(nums[::2], nums[1::2])))
        except ValueError:
            print(f"⚠️  Skipped malformed /Vertices block: {block[:40]}…")
    return polys

def getCentroid(vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Polygon centroid (handles triangles‑n‑up plus 2‑point fallback)."""
    if len(vertices) < 3:
        xs, ys = zip(*vertices)
        return sum(xs)/len(xs), sum(ys)/len(ys)

    a = cx = cy = 0.0
    for i in range(len(vertices)):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % len(vertices)]
        cross  = x0 * y1 - x1 * y0
        a  += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:                           # nearly colinear – use average
        xs, ys = zip(*vertices)
        return sum(xs)/len(xs), sum(ys)/len(ys)
    a *= 0.5
    return cx / (6*a), cy / (6*a)

def nextOutputName(base="output", ext="fdf") -> str:
    for i in range(1, 100):
        name = f"{base}-{i:02d}.{ext}"
        if not Path(name).exists():
            return name
    sys.exit("❌  No free output slot (output-01 … output-99).")

def buildFdf(pdf: str, imgData: bytes, centres: List[Tuple[float, float]],
             wPt: float, hPt: float, wPx: int, hPx: int, pageNum0: int) -> bytes:
    """
    Construct an FDF 1.2 with one SquareImage annotation per *centres* entry.
    *pageNum0* is zero‑based for /Page.
    """
    objects, annotRefs = [], []
    objNum = 2

    for idx, (cx, cy) in enumerate(centres, start=1):
        x0, y0 = cx - wPt/2, cy - hPt/2
        x1, y1 = x0 + wPt, y0 + hPt
        annotId, streamId = objNum, objNum + 1
        objNum += 2

        # Annotation object
        objects.append(textwrap.dedent(f"""
            {annotId} 0 obj
            <<
              /Type /Annot
              /Subtype /Square
              /IT /SquareImage
              /Rect [{x0} {y0} {x1} {y1}]
              /NM (Img{idx})
              /T  (Img{idx})
              /F  4
              /Image 999 0 R
              /AP << /N {streamId} 0 R >>
              /Page {pageNum0}
            >>
            endobj
        """))

        # Appearance stream
        stream = f"q {wPt} 0 0 {hPt} {x0} {y0} cm /Image Do Q"
        objects.append(textwrap.dedent(f"""
            {streamId} 0 obj
            <<
              /Type /XObject
              /Subtype /Form
              /FormType 1
              /BBox [{x0} {y0} {x1} {y1}]
              /Resources << /XObject << /Image 999 0 R >> /ProcSet [/PDF /ImageC] >>
              /Length {len(stream)}
            >>
            stream\r
            {stream}\r
            endstream\r
            endobj
        """))
        annotRefs.append(f"{annotId} 0 R")

    # JPEG image object (ID 999 0 R)
    imgObj  = textwrap.dedent(f"""
        999 0 obj
        <<
          /Type /XObject
          /Subtype /Image
          /Width {wPx}
          /Height {hPx}
          /ColorSpace /DeviceRGB
          /BitsPerComponent 8
          /Filter /DCTDecode
          /Length {len(imgData)}
        >>
        stream\r
    """).encode("latin-1") + imgData + b"\r\nendstream\r\nendobj\r\n"

    # Root
    root = textwrap.dedent(f"""
        %FDF-1.2
        %âãÏÓ
        1 0 obj
        <<
          /FDF <<
            /F ({pdf})
            /Annots [{' '.join(annotRefs)}]
          >>
        >>
        endobj
    """)

    return root.encode("latin-1") + b"".join(o.encode("latin-1") for o in objects) + imgObj + \
           b"trailer\r\n<< /Root 1 0 R >>\r\n%%EOF\r\n"

# ── main ─────────────────────────────────────────────────────────────────
def main() -> None:
    polys    = extractPolyPoints(polyFdf)
    centres  = [getCentroid(p) for p in polys]
    wPt, hPt = calculateScaledSizePt(realObjectSizeMm, scale)
    wPx, hPx, imgBytes = resizeImageToPt(imagePath, (wPt, hPt))

    outFdf   = nextOutputName()
    fdfBytes = buildFdf(pdf=pdfName,
                        imgData=imgBytes,
                        centres=centres,
                        wPt=wPt, hPt=hPt,
                        wPx=wPx, hPx=hPx,
                        pageNum0=page-1)

    Path(outFdf).write_bytes(fdfBytes)
    print(f"✅  Wrote {outFdf} with {len(centres)} image(s) "
          f"at 1:{scale} → {realObjectSizeMm[0]}×{realObjectSizeMm[1]} mm real size.")

if __name__ == "__main__":
    main()
