#!/usr/bin/env python3

import os
import re
import sys
import textwrap
from pathlib import Path
from typing import List, Tuple
from PIL import Image
from io import BytesIO

# -------------------------------
# 🔧 Configurable Inputs
# -------------------------------
POLY_FDF = "test.fdf"
PDF_NAME = "Document1.pdf"
IMAGE = "images.jpg"
PAGE = 1  # 1-based

# Page setup
PAGE_SIZE_MM = (210, 297)              # A4 Portrait
SCALE = 11                             # 1:50 real-world to paper
REAL_OBJECT_SIZE_MM = (250, 250)       # Real size of object (e.g. 250mm x 250mm)
# -------------------------------

def mm_to_pt(mm: float) -> float:
    return mm * 72 / 25.4  # 1 inch = 72 pt, 1 inch = 25.4 mm

def extract_poly_points(poly_fdf_path: str) -> List[List[Tuple[float, float]]]:
    if not os.path.isfile(poly_fdf_path):
        sys.exit("❌  Cannot find file “%s”" % poly_fdf_path)

    with open(poly_fdf_path, "r", encoding="latin-1") as f:
        content = f.read()

    polys: List[List[Tuple[float, float]]] = []
    for block in re.findall(r"/Vertices\s*\[([^\]]+)\]", content):
        try:
            nums = list(map(float, block.strip().split()))
            polys.append(list(zip(nums[::2], nums[1::2])))
        except ValueError:
            print(f"⚠️  skipped malformed /Vertices block: {block[:40]}…")
    return polys

def centroid(vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(vertices) < 3:
        xs, ys = zip(*vertices)
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    a = cx = cy = 0.0
    for i in range(len(vertices)):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % len(vertices)]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    if a == 0:
        xs, ys = zip(*vertices)
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    a *= 0.5
    cx /= 6 * a
    cy /= 6 * a
    return (cx, cy)

def scale_real_object_to_pdf(real_mm: Tuple[float, float], scale: float) -> Tuple[float, float]:
    """Convert real-world size in mm → scaled pt on PDF"""
    printed_w_mm = real_mm[0] / scale
    printed_h_mm = real_mm[1] / scale
    return mm_to_pt(printed_w_mm), mm_to_pt(printed_h_mm)

def get_resized_image(image_path: str, target_size_pt: Tuple[float, float]) -> Tuple[int, int, bytes]:
    """Resize image to match target pt size (1 pt = 1 px at 72 DPI)"""
    width_px = round(target_size_pt[0])
    height_px = round(target_size_pt[1])

    with Image.open(image_path) as img:
        resized = img.resize((width_px, height_px), resample=Image.LANCZOS)
        buffer = BytesIO()
        resized.save(buffer, format="JPEG")
        img_bytes = buffer.getvalue()

    return width_px, height_px, img_bytes

def build_image_fdf(pdf_name: str, img_bytes: bytes, centres: List[Tuple[float, float]],
                    width_pt: float, height_pt: float, width_px: int, height_px: int, page: int) -> bytes:
    objects = []
    annot_refs = []
    obj_num = 2

    for idx, (cx, cy) in enumerate(centres, start=1):
        x0 = cx - width_pt / 2
        y0 = cy - height_pt / 2
        x1 = x0 + width_pt
        y1 = y0 + height_pt

        annot_id = obj_num
        stream_id = obj_num + 1
        obj_num += 2

        objects.append(textwrap.dedent(f"""\
            {annot_id} 0 obj
            <<
              /Type /Annot
              /Subtype /Square
              /IT /SquareImage
              /Rect [{x0} {y0} {x1} {y1}]
              /NM (Img{idx})
              /T (Img{idx})
              /F 4
              /Image 999 0 R
              /AP << /N {stream_id} 0 R >>
              /Page {page}
            >>
            endobj
        """))

        stream = f"q {width_pt} 0 0 {height_pt} {x0} {y0} cm /Image Do Q"
        objects.append(textwrap.dedent(f"""\
            {stream_id} 0 obj
            <<
              /Type /XObject
              /Subtype /Form
              /FormType 1
              /BBox [{x0} {y0} {x1} {y1}]
              /Resources << /XObject << /Image 999 0 R >> /ProcSet [/PDF /ImageC] >>
              /Length {len(stream)}
            >>
            stream
            {stream}
            endstream
            endobj
        """))

        annot_refs.append(f"{annot_id} 0 R")

    img_obj = textwrap.dedent(f"""\
        999 0 obj
        <<
          /Type /XObject
          /Subtype /Image
          /Width {width_px}
          /Height {height_px}
          /ColorSpace /DeviceRGB
          /BitsPerComponent 8
          /Filter /DCTDecode
          /Length {len(img_bytes)}
        >>
        stream
    """).encode("latin-1") + img_bytes + b"\nendstream\nendobj\n"

    root = textwrap.dedent(f"""\
        %FDF-1.2
        %âãÏÓ
        1 0 obj
        << /FDF <<
             /F ({pdf_name})
             /Annots [{' '.join(annot_refs)}]
        >> >>
        endobj
    """)

    return root.encode("latin-1") + b"".join(obj.encode("latin-1") for obj in objects) + img_obj + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"

def get_next_output_filename(base="output", ext="fdf") -> str:
    for i in range(1, 100):
        filename = f"{base}-{i:02d}.{ext}"
        if not Path(filename).exists():
            return filename
    sys.exit("❌ Could not find free output file name slot (output-01 to output-99).")

def main() -> None:
    polys = extract_poly_points(POLY_FDF)
    centres = [centroid(p) for p in polys]

    # Convert real-world object size → scaled pt size
    width_pt, height_pt = scale_real_object_to_pdf(REAL_OBJECT_SIZE_MM, SCALE)

    # Resize image to match that point size (1 pt = 1 px)
    width_px, height_px, img_bytes = get_resized_image(IMAGE, (width_pt, height_pt))

    # Build FDF
    out_fdf = get_next_output_filename()
    fdf_bytes = build_image_fdf(
        pdf_name=PDF_NAME,
        img_bytes=img_bytes,
        centres=centres,
        width_pt=width_pt,
        height_pt=height_pt,
        width_px=width_px,
        height_px=height_px,
        page=PAGE - 1,
    )

    Path(out_fdf).write_bytes(fdf_bytes)
    print(f"✅ Wrote {out_fdf} with {len(centres)} image(s) at 1:{SCALE} scale — {REAL_OBJECT_SIZE_MM[0]}×{REAL_OBJECT_SIZE_MM[1]} mm real-world size")

if __name__ == "__main__":
    main()
