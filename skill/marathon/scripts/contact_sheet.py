"""Combine screenshots into one labelled contact sheet (half scale by default) to keep reviews cheap.
Usage: python contact_sheet.py out.png img1.png img2.png ... [--scale 0.5] [--cols 3]"""
import argparse
import os

from PIL import Image, ImageDraw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--cols", type=int, default=3)
    a = ap.parse_args()
    ims = []
    for p in a.images:
        im = Image.open(p).convert("RGB")
        im = im.resize((max(1, int(im.width * a.scale)), max(1, int(im.height * a.scale))), Image.LANCZOS)
        ims.append((os.path.basename(p), im))
    cols = max(1, min(a.cols, len(ims)))
    cw = max(im.width for _, im in ims)
    ch = max(im.height for _, im in ims) + 18
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(ims):
        x, y = (i % cols) * cw, (i // cols) * ch
        d.text((x + 4, y + 2), name, fill=(235, 235, 235))
        sheet.paste(im, (x, y + 18))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out)
    print(a.out, sheet.size)


if __name__ == "__main__":
    main()
