#!/usr/bin/env python3
"""Render slide-deck PDFs (or .pptx via LibreOffice) into grid contact sheets.

Each deck becomes  <deck_dir>/<deck_stem>_grid/
    slides/slide-NN.png      one PNG per slide
    grid-01.png, grid-02...  ROWSxCOLS slides per sheet, slide numbers stamped
    overview.png             every slide as a small thumbnail on one sheet

Usage:
    .paper2code_venv/bin/python tools/pdf_to_grid.py design/            # all decks under a dir
    .paper2code_venv/bin/python tools/pdf_to_grid.py deck.pdf --cols 3 --rows 2

Needs: pdftoppm (poppler), Pillow; soffice only for .pptx input.
Duplicate files (same bytes, e.g. "deck (1).pdf") are rendered once.
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DECK_EXTS = {".pdf", ".pptx", ".ppt"}


def find_decks(paths):
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.suffix.lower() in DECK_EXTS and "_grid" not in f.parts[-2])
        elif p.suffix.lower() in DECK_EXTS:
            out.append(p)
    seen, uniq = set(), []
    for f in sorted(out, key=lambda f: (" (" in f.name, str(f))):  # prefer "deck.pdf" over "deck (1).pdf"
        h = hashlib.sha1(f.read_bytes()).hexdigest()
        if h in seen:
            print(f"skip duplicate: {f}")
            continue
        seen.add(h)
        uniq.append(f)
    return uniq


def to_pdf(deck, tmp):
    if deck.suffix.lower() == ".pdf":
        return deck
    if not shutil.which("soffice"):
        sys.exit(f"soffice (LibreOffice) needed to convert {deck}")
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(deck)], check=True)
    return Path(tmp) / (deck.stem + ".pdf")


def render_slides(pdf, slides_dir, width):
    slides_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftoppm", "-png", "-scale-to-x", str(width), "-scale-to-y", "-1",
                    str(pdf), str(slides_dir / "slide")], check=True)
    files = sorted(slides_dir.glob("slide-*.png"))
    # normalise names to slide-NN.png
    for i, f in enumerate(files, 1):
        f.rename(slides_dir / f"slide-{i:02d}.png")
    return sorted(slides_dir.glob("slide-*.png"))


def font(size):
    for name in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/System/Library/Fonts/Helvetica.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def sheet(images, numbers, cols, rows, cell_w, gap=12, label=True):
    first = Image.open(images[0])
    cell_h = int(cell_w * first.height / first.width)
    rows = min(rows, -(-len(images) // cols))
    W = cols * cell_w + (cols + 1) * gap
    H = rows * cell_h + (rows + 1) * gap
    canvas = Image.new("RGB", (W, H), (40, 40, 40))
    draw = ImageDraw.Draw(canvas)
    f = font(max(14, cell_w // 22))
    for k, (img_path, n) in enumerate(zip(images, numbers)):
        r, c = divmod(k, cols)
        x, y = gap + c * (cell_w + gap), gap + r * (cell_h + gap)
        im = Image.open(img_path).convert("RGB").resize((cell_w, cell_h), Image.LANCZOS)
        canvas.paste(im, (x, y))
        if label:
            tag = f" {n} "
            bbox = draw.textbbox((0, 0), tag, font=f)
            draw.rectangle([x, y, x + bbox[2] + 6, y + bbox[3] + 6], fill=(220, 60, 40))
            draw.text((x + 3, y + 2), tag, fill="white", font=f)
    return canvas


def process(deck, cols, rows, cell_w, render_w):
    out = deck.parent / f"{deck.stem}_grid"
    if out.exists():
        shutil.rmtree(out)
    with tempfile.TemporaryDirectory() as tmp:
        pdf = to_pdf(deck, tmp)
        slides = render_slides(pdf, out / "slides", render_w)
    per = cols * rows
    sheets = 0
    for i in range(0, len(slides), per):
        chunk = slides[i:i + per]
        sheet(chunk, range(i + 1, i + 1 + len(chunk)), cols, rows, cell_w).save(out / f"grid-{i // per + 1:02d}.png")
        sheets += 1
    ov_cols = 5
    sheet(slides, range(1, len(slides) + 1), ov_cols, 99, 360, gap=8).save(out / "overview.png")
    print(f"{deck} -> {out}  ({len(slides)} slides, {sheets} grids + overview)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="deck files or directories to scan")
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--rows", type=int, default=2)
    ap.add_argument("--cell-width", type=int, default=1000, help="px width of each slide in a grid sheet")
    ap.add_argument("--render-width", type=int, default=1600, help="px width of per-slide PNGs")
    a = ap.parse_args()
    decks = find_decks(a.paths)
    if not decks:
        sys.exit("no .pdf/.pptx decks found")
    for d in decks:
        process(d, a.cols, a.rows, a.cell_width, a.render_width)


if __name__ == "__main__":
    main()
