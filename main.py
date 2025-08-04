#!/usr/bin/env python3
import os
import re
import sys
import zlib
import textwrap
from pathlib import Path
from typing import List, Tuple
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, Point
from shapely.geometry.polygon import orient

# ─── USER INPUT ──────────────────────────────────────────────
polyFdf              = "25111-PLX-SKT-MD-Schematic Design_03.fdf"
pdfName              = "25111-PLX-SKT-MD-Schematic Design_03.pdf"
imagePath            = "b.png"
page                 = 1
scale                = 50
realObjectSizeMm     = (250, 250)
dpi                  = 1000.0
spacingPt            = 100.0  # spacing between lights (in points)
realWorldMarginMm    = 250.0  # real-world wall clearance in mm
# ─────────────────────────────────────────────────────────────

def mmToPt(mm: float) -> float:
    return mm * 72 / 25.4

def calculateScaledSizePt(realMm: Tuple[float, float], scale: float) -> Tuple[float, float]:
    return mmToPt(realMm[0] / scale), mmToPt(realMm[1] / scale)

def resizeImageToRawStreams(path: str, sizePt: Tuple[float, float], dpi: float) -> Tuple[int, int, bytes, bytes]:
    widthPx = round(sizePt[0] * dpi / 72)
    heightPx = round(sizePt[1] * dpi / 72)

    with Image.open(path).convert("RGBA") as img:
        img = img.resize((widthPx, heightPx), Image.LANCZOS)
        r, g, b, a = img.split()
        rgb = Image.merge("RGB", (r, g, b))
        rgbBytes = rgb.tobytes()
        alphaBytes = a.tobytes()
        return widthPx, heightPx, zlib.compress(rgbBytes), zlib.compress(alphaBytes)

def extractPolyPoints(fdfPath: str) -> List[List[Tuple[float, float]]]:
    with open(fdfPath, "r", encoding="latin-1") as f:
        content = f.read()
    polys = []
    for block in re.findall(r"/Vertices\s*\[([^\]]+)\]", content):
        try:
            nums = list(map(float, block.strip().split()))
            polys.append(list(zip(nums[::2], nums[1::2])))
        except ValueError:
            pass
    return polys

def generateLatticePoints(polygon: Polygon, spacing: float, marginPt: float, widthPx: int, heightPx: int) -> List[Tuple[float, float]]:
    polygon = orient(polygon)
    inset = polygon.buffer(-marginPt)
    if inset.is_empty or not inset.is_valid:
        inset = polygon

    minx, miny, maxx, maxy = inset.bounds
    width = maxx - minx
    height = maxy - miny

    xCount = int(width // spacing)
    yCount = int(height // spacing)
    xOffset = minx + (width - xCount * spacing) / 2
    yOffset = miny + (height - yCount * spacing) / 2

    xs = np.arange(xOffset, maxx, spacing)
    ys = np.arange(yOffset, maxy, spacing)

    return [(x, y) for x in xs for y in ys if inset.contains(Point(x, y))]

def buildMarginAnnots(polygons: List[Polygon], marginPt: float, pageNum0: int, startObjNum: int = 100) -> Tuple[List[str], List[str]]:
    objects = []
    refs = []
    objNum = startObjNum
    for poly in polygons:
        inset = poly.buffer(-marginPt)
        if inset.is_empty or not inset.is_valid:
            continue
        if hasattr(inset, "geoms"):
            parts = list(inset.geoms)
        else:
            parts = [inset]
        for part in parts:
            coords = list(part.exterior.coords)
            flat = " ".join(f"{x:.2f} {y:.2f}" for x, y in coords)
            objects.append(textwrap.dedent(f"""
                {objNum} 0 obj
                <<
                  /Type /Annot
                  /Subtype /Polygon
                  /Rect [0 0 0 0]
                  /Vertices [{flat}]
                  /C [0 1 0]
                  /T (Margin)
                  /F 4
                  /Page {pageNum0}
                >>
                endobj
            """))
            refs.append(f"{objNum} 0 R")
            objNum += 1
    return objects, refs

def nextOutputName(base="output", ext="fdf") -> str:
    for i in range(1, 100):
        name = f"{base}-{i:02d}.{ext}"
        if not Path(name).exists():
            return name
    sys.exit("No free output slot.")

def buildFdf(pdf: str, rgbData: bytes, alphaData: bytes,
             centres: List[Tuple[float, float]], marginPolys: List[Polygon],
             wPt: float, hPt: float, wPx: int, hPx: int, pageNum0: int) -> bytes:
    objects, annotRefs = [], []
    objNum = 2
    for idx, (cx, cy) in enumerate(centres, start=1):
        x0, y0 = cx - wPt / 2, cy - hPt / 2
        x1, y1 = x0 + wPt, y0 + hPt
        stream = f"q {wPt} 0 0 {hPt} {x0} {y0} cm /Image Do Q"
        annotId, streamId = objNum, objNum + 1
        objNum += 2
        objects.append(textwrap.dedent(f"""
            {annotId} 0 obj
            <<
              /Type /Annot
              /Subtype /Square
              /IT /SquareImage
              /Rect [{x0} {y0} {x1} {y1}]
              /NM (Img{idx})
              /T (Img{idx})
              /F 4
              /Border [0 0 0]
              /Image 999 0 R
              /AP << /N {streamId} 0 R >>
              /Page {pageNum0}
            >>
            endobj
        """))
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

    marginObjs, marginRefs = buildMarginAnnots(marginPolys, mmToPt(realWorldMarginMm / scale), pageNum0, objNum)
    annotRefs.extend(marginRefs)
    objects.extend(marginObjs)

    imgObj = textwrap.dedent(f"""
        999 0 obj
        <<
          /Type /XObject
          /Subtype /Image
          /Width {wPx}
          /Height {hPx}
          /ColorSpace /DeviceRGB
          /BitsPerComponent 8
          /Filter /FlateDecode
          /SMask 998 0 R
          /Length {len(rgbData)}
        >>
        stream\r
    """).encode("latin-1") + rgbData + b"\r\nendstream\r\nendobj\r\n"

    smaskObj = textwrap.dedent(f"""
        998 0 obj
        <<
          /Type /XObject
          /Subtype /Image
          /Width {wPx}
          /Height {hPx}
          /ColorSpace /DeviceGray
          /BitsPerComponent 8
          /Filter /FlateDecode
          /Length {len(alphaData)}
        >>
        stream\r
    """).encode("latin-1") + alphaData + b"\r\nendstream\r\nendobj\r\n"

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
    return (root.encode("latin-1")
            + b"".join(o.encode("latin-1") for o in objects)
            + imgObj + smaskObj
            + b"trailer\r\n<< /Root 1 0 R >>\r\n%%EOF\r\n")

def main():
    marginPt = mmToPt(realWorldMarginMm / scale)
    polys = [Polygon(verts) for verts in extractPolyPoints(polyFdf)]
    validPolys = [p for p in polys if p.is_valid and not p.is_empty]

    wPt, hPt = calculateScaledSizePt(realObjectSizeMm, scale)
    wPx, hPx, rgbData, alphaData = resizeImageToRawStreams(imagePath, (wPt, hPt), dpi)

    allCentres = []
    for poly in validPolys:
        dots = generateLatticePoints(poly, spacingPt, marginPt, wPx, hPx)
        allCentres.extend(dots)

    fdfBytes = buildFdf(pdfName, rgbData, alphaData, allCentres, validPolys, wPt, hPt, wPx, hPx, page - 1)
    outFdf = nextOutputName()
    Path(outFdf).write_bytes(fdfBytes)
    print(f"Wrote {outFdf} with {len(allCentres)} image(s) and margin outlines.")

if __name__ == "__main__":
    main()
