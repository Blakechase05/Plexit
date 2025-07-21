#!/usr/bin/env python3
# plexit_insert_images.py – Fixed image size in mm

import os
import re
import sys
import textwrap
from pathlib import Path
from typing import List, Tuple
from PIL import Image

# -------------------------------
# 🔧 Configurable Inputs
# -------------------------------
POLY_FDF = "test.fdf"
PDF_NAME = "Document1.pdf"
IMAGE    = "image.jpg"
PAGE     = 1                         # 1-based page number
# FORCE_SIZE_MM = (25, 25)             # Desired image size (W, H) in mm
# -------------------------------

def extract_poly_points(poly_fdf_path: str) -> List[List[Tuple[float, float]]]:
    """Return a list of lists of (x, y) tuples for every polygon."""
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
    """Return centroid of a polygon."""
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


def get_image_dimensions_and_bytes(image_path: str) -> Tuple[float, float, bytes]:
    """Return (width, height) in points and raw image bytes."""
    with Image.open(image_path) as img:
        dpi = img.info.get("dpi", (72, 72))  # Default to 72 DPI if missing
        width_pt = img.width
        height_pt = img.height
    img_bytes = Path(image_path).read_bytes()
    return width_pt, height_pt, img_bytes


# def mm_to_pt(mm: float) -> float:
#     """Convert millimetres to PDF points (1 inch = 72 pt, 1 inch = 25.4 mm)."""
#     return mm * 72 / 25.4


def build_image_fdf(pdf_name: str, img_bytes: bytes, centres: List[Tuple[float, float]],
                    width: float, height: float, page: int) -> bytes:
    """Return full FDF as bytes with one SquareImage annotation per centre."""
    objects = []
    annot_refs = []
    obj_num = 2

    for idx, (cx, cy) in enumerate(centres, start=1):
        x0 = cx - width / 2
        y0 = cy - height / 2
        x1 = x0 + width
        y1 = y0 + height

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

        stream = f"{x0} {y0} {width} {height} re q {width} 0 0 {height} {x0} {y0} cm /Image Do Q"
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
          /Width {width}
          /Height {height}
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
    width_pt, height_pt, img_bytes = get_image_dimensions_and_bytes(IMAGE)
    out_fdf = get_next_output_filename()

    # 📏 Override image size using FORCE_SIZE_MM
    # if FORCE_SIZE_MM:
    #     width_pt = mm_to_pt(FORCE_SIZE_MM[0])
    #     height_pt = mm_to_pt(FORCE_SIZE_MM[1])

    fdf_bytes = build_image_fdf(
        pdf_name=PDF_NAME,
        img_bytes=img_bytes,
        centres=centres,
        width=width_pt,
        height=height_pt,
        page=PAGE - 1,
    )

    Path(out_fdf).write_bytes(fdf_bytes)
    print(f"✅ Wrote {out_fdf} with {len(centres)} image(s).")


if __name__ == "__main__":
    main()
