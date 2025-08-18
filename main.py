#!/usr/bin/env python3
import re
import sys
import zlib
import textwrap
from pathlib import Path
from typing import List, Tuple

import numpy as np
from shapely.geometry import Polygon, MultiPolygon, box, Point
from shapely.geometry.polygon import orient

try:
    from PIL import Image
except ImportError:
    sys.exit("Please install Pillow: pip install Pillow")

# ─── USER CONFIG ─────────────────────────────────────────────
polyFdf            = "25111-PLX-SKT-MD-Schematic Design_03.fdf"
pdfName            = "25111-PLX-SKT-MD-Schematic Design_03.pdf"
page               = 1                      # 1-based; FDF uses 0-based internally
LATTICE_SPACING_PT = 10.0                   # fine lattice (debug/show only)
IMAGE_SPACING_PT   = 150.0                   # spacing for image stamps
IMG_SIZE_PT        = 12.0                   # displayed stamp size (points)
imagePath          = "b.png"                # the image to embed
EPS                = 1e-6
DEBUG_LATTICE      = False                  # draw the 10-pt lattice squares (thin) for sanity check
# ─────────────────────────────────────────────────────────────


# ─────────────────────────── FDF PARSE ───────────────────────────

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


# ───────────────────── LATTICE / GRID HELPERS ─────────────────────

def grid_cells(subpoly: Polygon, spacing: float) -> Tuple[np.ndarray, np.ndarray]:
    """Return bbox-centred grid lower-left coordinates for cell grid at given spacing."""
    minx, miny, maxx, maxy = subpoly.bounds
    width  = maxx - minx
    height = maxy - miny
    cols = int(width // spacing)
    rows = int(height // spacing)
    if cols <= 0 or rows <= 0:
        return np.array([]), np.array([])
    x0 = minx + (width  - cols * spacing) / 2.0
    y0 = miny + (height - rows * spacing) / 2.0
    xs = np.arange(x0, x0 + cols * spacing, spacing)
    ys = np.arange(y0, y0 + rows * spacing, spacing)
    return xs, ys


def grid_centres_in_polygon(polygon: Polygon, spacing: float) -> List[Tuple[float, float]]:
    """
    Centres of a bbox-centred grid (at `spacing`) that lie inside the polygon (holes respected).
    """
    polygon = orient(polygon)
    if polygon.is_empty or not polygon.is_valid:
        return []
    parts = list(polygon.geoms) if isinstance(polygon, MultiPolygon) else [polygon]
    centres: List[Tuple[float, float]] = []
    for subpoly in parts:
        xs, ys = grid_cells(subpoly, spacing)
        if xs.size == 0 or ys.size == 0:
            continue
        for x0 in xs:
            for y0 in ys:
                cx = x0 + spacing / 2.0
                cy = y0 + spacing / 2.0
                pt = Point(cx, cy)
                if subpoly.contains(pt) or subpoly.covers(pt):
                    centres.append((cx, cy))
    return centres


def lattice_squares_for_debug(polygon: Polygon, spacing: float) -> List[Polygon]:
    """
    Build the raw lattice squares (bbox-centred) at given spacing, without inside filtering.
    Debug visual only.
    """
    polygon = orient(polygon)
    parts = list(polygon.geoms) if isinstance(polygon, MultiPolygon) else [polygon]
    out = []
    for subpoly in parts:
        xs, ys = grid_cells(subpoly, spacing)
        for x0 in xs:
            for y0 in ys:
                out.append(box(x0, y0, x0 + spacing, y0 + spacing))
    return out


# ───────────────────── PDF/FDF BUILD HELPERS ─────────────────────

def _obj_header(obj_num: int, dict_txt: str) -> bytes:
    return f"{obj_num} 0 obj\n{dict_txt}\nendobj\n".encode("latin-1")

def _obj_stream(obj_num: int, dict_txt: str, stream_bytes: bytes) -> bytes:
    hdr = f"{obj_num} 0 obj\n{dict_txt}\nstream\n".encode("latin-1")
    ftr = b"\nendstream\nendobj\n"
    return hdr + stream_bytes + ftr


def build_pdf_image_xobject(obj_num: int, pil_img: Image.Image) -> Tuple[bytes, int, int]:
    """
    Build a PDF /XObject /Image as a deflated RGB stream.
    Returns (bytes, width, height).
    """
    if pil_img.mode not in ("RGB", "RGBA", "L"):
        pil_img = pil_img.convert("RGB")
    if pil_img.mode == "RGBA":
        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
        bg.paste(pil_img, mask=pil_img.split()[-1])
        pil_img = bg
    elif pil_img.mode == "L":
        pil_img = pil_img.convert("RGB")

    w, h = pil_img.size
    raw = pil_img.tobytes()
    comp = zlib.compress(raw, level=6)

    dict_txt = textwrap.dedent(f"""\
        <<
          /Type /XObject
          /Subtype /Image
          /Width {w}
          /Height {h}
          /ColorSpace /DeviceRGB
          /BitsPerComponent 8
          /Filter /FlateDecode
          /Length {len(comp)}
        >>""")
    return _obj_stream(obj_num, dict_txt, comp), w, h


def build_form_appearance(obj_num: int, image_ref: str, box_size: float) -> bytes:
    """
    Build a /Form XObject that draws the shared image scaled to (box_size x box_size).
    The image is referenced as /Im0 in the /Resources of the form.
    """
    content = f"q {box_size:.3f} 0 0 {box_size:.3f} 0 0 cm /Im0 Do Q".encode("latin-1")
    dict_txt = textwrap.dedent(f"""\
        <<
          /Type /XObject
          /Subtype /Form
          /BBox [0 0 {box_size:.3f} {box_size:.3f}]
          /Resources <<
            /XObject << /Im0 {image_ref} >>
          >>
          /Length {len(content)}
        >>""")
    return _obj_stream(obj_num, dict_txt, content)


def build_image_annot(obj_num: int, centre: Tuple[float, float], size: float, ap_ref: str, page0: int, name: str) -> bytes:
    cx, cy = centre
    half = size / 2.0
    x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    dict_txt = textwrap.dedent(f"""\
        <<
          /Type /Annot
          /Subtype /Square
          /Rect [{x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f}]
          /F 4
          /T ({name})
          /AP << /N {ap_ref} >>
          /Page {page0}
        >>""")
    return _obj_header(obj_num, dict_txt)


def build_image_fdf(pdf: str, page0: int, centres: List[Tuple[float, float]], image_path: str, size: float,
                    debug_tiles=None, debug_color=(0.6, 0.7, 1.0), debug_border_w=0.2) -> bytes:
    """
    Build an FDF with one shared image XObject and N image-stamp annots.
    Optionally append debug lattice squares as thin /Square annots.
    """
    img = Image.open(image_path)
    objects: List[bytes] = []
    refs: List[str] = []
    obj_num = 2  # 1 0 obj is FDF root; begin at 2

    # 1) Shared image
    img_obj_bytes, _, _ = build_pdf_image_xobject(obj_num, img)
    objects.append(img_obj_bytes)
    img_ref = f"{obj_num} 0 R"
    obj_num += 1

    # 2) Per-annot: unique Form appearance + annot
    for k, c in enumerate(centres, start=1):
        form_obj_num = obj_num
        objects.append(build_form_appearance(form_obj_num, img_ref, size))
        form_ref = f"{form_obj_num} 0 R"
        obj_num += 1

        annot_obj_num = obj_num
        objects.append(build_image_annot(annot_obj_num, c, size, form_ref, page0, f"Img{k}"))
        refs.append(f"{annot_obj_num} 0 R")
        obj_num += 1

    # 3) Optional debug lattice squares
    if debug_tiles:
        r, g, b = debug_color
        for idx, rect in enumerate(debug_tiles, start=1):
            minx, miny, maxx, maxy = rect.bounds
            dict_txt = textwrap.dedent(f"""\
                <<
                  /Type /Annot
                  /Subtype /Square
                  /Rect [{minx:.3f} {miny:.3f} {maxx:.3f} {maxy:.3f}]
                  /C [{r} {g} {b}]
                  /F 4
                  /BS << /W {debug_border_w} /S /S >>
                  /T (T{idx})
                  /Page {page0}
                >>""")
            objects.append(_obj_header(obj_num, dict_txt))
            refs.append(f"{obj_num} 0 R")
            obj_num += 1

    # 4) FDF root
    root = textwrap.dedent(f"""\
        %FDF-1.2
        %âãÏÓ
        1 0 obj
        <<
          /FDF <<
            /F ({pdf})
            /Annots [{' '.join(refs)}]
          >>
        >>
        endobj
    """).encode("latin-1")

    return root + b"".join(objects) + b"trailer\r\n<< /Root 1 0 R >>\r\n%%EOF\r\n"


# ─────────────────────────────── MAIN ───────────────────────────────

def nextOutputName(base="output", ext="fdf") -> str:
    for i in range(1, 200):
        name = f"{base}-{i:02d}.{ext}"
        if not Path(name).exists():
            return name
    sys.exit("No free output slot.")

def main():
    # load polygons
    poly_paths = extractPolyPoints(polyFdf)
    polys = [Polygon(p) for p in poly_paths if Polygon(p).is_valid and not Polygon(p).is_empty]
    if not polys:
        print("No valid polygons found in FDF.")
        return

    # Centres for image spacing (e.g., 50pt)
    centres_all: List[Tuple[float, float]] = []
    # Optional debug lattice squares at fine spacing (e.g., 10pt)
    debug_all = []

    for idx, poly in enumerate(polys, start=1):
        centres = grid_centres_in_polygon(poly, IMAGE_SPACING_PT)
        if not centres:
            print(f"Polygon {idx}: no image centres inside (IMAGE_SPACING_PT={IMAGE_SPACING_PT}).")
        centres_all.extend(centres)

        if DEBUG_LATTICE:
            debug_all.extend(lattice_squares_for_debug(poly, LATTICE_SPACING_PT))

    if not centres_all and not debug_all:
        print("Nothing to write — try reducing IMAGE_SPACING_PT or enable DEBUG_LATTICE to visualise the 10-pt grid.")
        return

    fdf_bytes = build_image_fdf(
        pdfName,
        page - 1,
        centres_all,
        imagePath,
        IMG_SIZE_PT,
        debug_tiles=debug_all if DEBUG_LATTICE else None
    )
    out_name = nextOutputName()
    Path(out_name).write_bytes(fdf_bytes)
    print(f"Wrote {out_name} with {len(centres_all)} image stamps (spacing {IMAGE_SPACING_PT} pt)"
          f"{' and debug lattice at ' + str(LATTICE_SPACING_PT) + ' pt' if DEBUG_LATTICE else ''}.")

if __name__ == "__main__":
    main()
