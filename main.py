#!/usr/bin/env python3
import os
import re
import sys
import zlib
import textwrap
from io import BytesIO
from pathlib import Path
from typing import List, Tuple
from PIL import Image

# ─── USER INPUT ──────────────────────────────────────────────
polyFdf          = "25111-PLX-SKT-MD-Schematic Design_03.fdf"
pdfName          = "25111-PLX-SKT-MD-Schematic Design_03.pdf"
imagePath        = "b.png"
page             = 1
scale            = 50
realObjectSizeMm = (250, 250)
dpi              = 1000.0
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

        rgbBytes   = rgb.tobytes()
        alphaBytes = a.tobytes()
        return widthPx, heightPx, zlib.compress(rgbBytes), zlib.compress(alphaBytes)

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

def getCentroid(verts: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(verts) < 3:
        xs, ys = zip(*verts)
        return sum(xs)/len(xs), sum(ys)/len(ys)

    a = cx = cy = 0.0
    for i in range(len(verts)):
        x0, y0 = verts[i]
        x1, y1 = verts[(i + 1) % len(verts)]
        cross  = x0 * y1 - x1 * y0
        a  += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:
        xs, ys = zip(*verts)
        return sum(xs)/len(xs), sum(ys)/len(ys)
    a *= 0.5
    return cx / (6*a), cy / (6*a)

def nextOutputName(base="output", ext="fdf") -> str:
    for i in range(1, 100):
        name = f"{base}-{i:02d}.{ext}"
        if not Path(name).exists():
            return name
    sys.exit("❌  No free output slot (output-01 … output-99).")

def buildFdf(pdf: str, rgbData: bytes, alphaData: bytes,
             centres: List[Tuple[float, float]], wPt: float, hPt: float,
             wPx: int, hPx: int, pageNum0: int) -> bytes:

    objects, annotRefs = [], []
    objNum = 2

    for idx, (cx, cy) in enumerate(centres, start=1):
        x0, y0 = cx - wPt/2, cy - hPt/2
        x1, y1 = x0 + wPt, y0 + hPt
        annotId, streamId = objNum, objNum + 1
        objNum += 2

        # appearance stream (draw the image)
        stream = f"q {wPt} 0 0 {hPt} {x0} {y0} cm /Image Do Q"

        # annotation object – note /Border [0 0 0] to force zero‑thickness outline
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
              /Border [0 0 0]
              /Image 999 0 R
              /AP << /N {streamId} 0 R >>
              /Page {pageNum0}
            >>
            endobj
        """))

        # appearance XObject
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

    # embedded RGB image stream
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

    # alpha mask stream
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

    # FDF root object
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

def main() -> None:
    polys    = extractPolyPoints(polyFdf)
    centres  = [getCentroid(p) for p in polys]
    wPt, hPt = calculateScaledSizePt(realObjectSizeMm, scale)
    wPx, hPx, rgbData, alphaData = resizeImageToRawStreams(imagePath, (wPt, hPt), dpi)
    outFdf   = nextOutputName()

    fdfBytes = buildFdf(pdfName, rgbData, alphaData, centres, wPt, hPt, wPx, hPx, page-1)
    Path(outFdf).write_bytes(fdfBytes)
    print(f"✅  Wrote {outFdf} with {len(centres)} image(s) — outline set to 0 pt")

if __name__ == "__main__":
    main()