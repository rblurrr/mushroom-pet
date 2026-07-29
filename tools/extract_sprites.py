"""Sprite extraction v3 — texture/edge based.

The renders have smooth radial *glow* behind each sprite that no colour-difference
model can separate from the sprite. But the backgrounds are smooth everywhere while
the sprites (pixel-art outlines, flames, dot patterns) carry strong local gradients.
So the mask is built from gradient energy, closed and hole-filled, which keeps flat
sprite interiors while rejecting the glow.
"""
import os, json
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

# Point these at your own sheets, or pass --input / --output on the command line.
# Keys become folder names under OUT; values are filenames inside SRC.
SRC = os.environ.get("SPRITE_SHEETS", "sheets")
OUT = os.environ.get("SPRITE_OUT", "work")

SHEETS = {
    # "walk": "my_walk_sheet.png",
    # "idle": "my_idle_sheet.png",
}


def energy(rgb):
    g = rgb.astype(np.float32) @ np.array([.299, .587, .114], np.float32)
    gx = ndimage.sobel(g, 1)
    gy = ndimage.sobel(g, 0)
    mag = np.hypot(gx, gy)
    # local colour variance catches textured-but-low-contrast areas (flames)
    f = rgb.astype(np.float32)
    var = np.zeros(g.shape, np.float32)
    for c in range(3):
        m = ndimage.uniform_filter(f[..., c], 5)
        var += ndimage.uniform_filter(f[..., c] ** 2, 5) - m ** 2
    return mag, np.sqrt(np.maximum(var, 0))


def build_mask(rgb, e_thr=34, v_thr=13, dil=4, min_area=2500):
    mag, sd = energy(rgb)
    m = (mag > e_thr) | (sd > v_thr)
    m = ndimage.binary_dilation(m, np.ones((dil, dil)))
    m = ndimage.binary_fill_holes(m)
    m = ndimage.binary_erosion(m, np.ones((dil, dil)))
    m = ndimage.binary_closing(m, np.ones((7, 7)))
    m = ndimage.binary_fill_holes(m)
    lbl, n = ndimage.label(m, np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(m, lbl, range(1, n + 1))
        drop = np.where(sizes < min_area)[0] + 1
        m[np.isin(lbl, drop)] = False
    return m


def runs(profile, thr, min_len):
    out, inb, s = [], False, 0
    for i, v in enumerate(profile):
        on = v > thr
        if on and not inb:
            s, inb = i, True
        elif not on and inb:
            if i - s >= min_len:
                out.append((s, i))
            inb = False
    if inb and len(profile) - s >= min_len:
        out.append((s, len(profile)))
    return out


def split_wide(prof, a, b, target):
    span = b - a
    n = max(1, int(round(span / target)))
    if n <= 1:
        return [(a, b)]
    seg, cuts = span / n, []
    for k in range(1, n):
        c = a + int(seg * k)
        lo, hi = max(a + 10, c - int(seg * .33)), min(b - 10, c + int(seg * .33))
        cuts.append(c if hi <= lo else lo + int(np.argmin(prof[lo:hi])))
    e = [a] + sorted(cuts) + [b]
    return [(e[i], e[i + 1]) for i in range(len(e) - 1)]


def extract(name, sheet, cell_w, skip_top=0, skip_bottom=0, e_thr=34, v_thr=13,
            min_w=48, min_h=42, pad=5, row_frac=.015, col_frac=.05):
    rgb = np.array(Image.open(os.path.join(SRC, sheet)).convert("RGB"))
    H, W, _ = rgb.shape
    m = build_mask(rgb, e_thr, v_thr)
    if skip_top:
        m[:skip_top] = False
    if skip_bottom:
        m[H - skip_bottom:] = False

    d_out = os.path.join(OUT, name)
    os.makedirs(d_out, exist_ok=True)
    for f in os.listdir(d_out):
        os.remove(os.path.join(d_out, f))

    rp = ndimage.uniform_filter1d(m.sum(1).astype(float), 5)
    bands = runs(rp, W * row_frac, 35)
    meta, k = [], 0
    for bi, (ry0, ry1) in enumerate(bands):
        strip = m[ry0:ry1]
        cp = ndimage.uniform_filter1d(strip.sum(0).astype(float), 5)
        cells = []
        for (a, b) in runs(cp, (ry1 - ry0) * col_frac, 25):
            cells += split_wide(cp, a, b, cell_w) if (b - a) > cell_w * 1.45 else [(a, b)]
        for (cx0, cx1) in cells:
            if cx1 - cx0 < min_w:
                continue
            sub = m[ry0:ry1, cx0:cx1]
            lbl, n = ndimage.label(sub, np.ones((3, 3)))
            if n == 0:
                continue
            sizes = ndimage.sum(sub, lbl, range(1, n + 1))
            big = int(np.argmax(sizes)) + 1
            keep = lbl == big
            near = ndimage.binary_dilation(keep, np.ones((19, 19)))
            for i in range(1, n + 1):
                if i != big and sizes[i - 1] > 80 and (near & (lbl == i)).any():
                    keep |= lbl == i
            keep = ndimage.binary_fill_holes(keep)
            ys, xs = np.where(keep)
            if not len(ys):
                continue
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            if (x1 - x0) < min_w or (y1 - y0) < min_h:
                continue
            ay0, ay1 = max(0, ry0 + y0 - pad), min(H, ry0 + y1 + pad)
            ax0, ax1 = max(0, cx0 + x0 - pad), min(W, cx0 + x1 + pad)
            am = np.zeros((ay1 - ay0, ax1 - ax0), bool)
            am[(ry0 + y0 - ay0):(ry0 + y1 - ay0), (cx0 + x0 - ax0):(cx0 + x1 - ax0)] = keep[y0:y1, x0:x1]
            a = ndimage.gaussian_filter(am.astype(np.float32), .8)
            a = np.clip((a - .3) / .45, 0, 1)
            out = np.dstack([rgb[ay0:ay1, ax0:ax1], (a * 255).astype(np.uint8)])
            Image.fromarray(out, "RGBA").save(os.path.join(d_out, f"{k:03d}.png"))
            meta.append({"i": k, "band": bi, "x": int(ax0), "y": int(ay0),
                         "w": int(ax1 - ax0), "h": int(ay1 - ay0)})
            k += 1
    json.dump(meta, open(os.path.join(d_out, "meta.json"), "w"), indent=1)
    print(f"{name}: {k} sprites in {len(bands)} bands")
    return meta


def contact(name, cols=9, cell=176):
    d = os.path.join(OUT, name)
    files = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 18)), (18, 20, 26))
    dr = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(os.path.join(d, f))
        im.thumbnail((cell - 10, cell - 10))
        cx, cy = (i % cols) * cell, (i // cols) * (cell + 18)
        tile = Image.new("RGB", im.size, (0, 160, 90))     # chroma-key green to spot halos
        tile.paste(im, (0, 0), im)
        sheet.paste(tile, (cx + (cell - im.width) // 2, cy + (cell - im.height) // 2))
        dr.text((cx + 6, cy + cell + 2), f[:-4], fill=(150, 210, 255))
    p = os.path.join(OUT, f"contact_{name}.png")
    sheet.save(p)
    print("  ->", p, sheet.size)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=SRC, help="folder holding your sprite sheets")
    ap.add_argument("--output", default=OUT, help="where to write the cut sprites")
    ap.add_argument("--cell-width", type=int, default=150,
                    help="approximate width of one sprite, used to split merged runs")
    ap.add_argument("--skip-top", type=int, default=0,
                    help="ignore this many pixels at the top (title text on the sheet)")
    a = ap.parse_args()

    globals()["SRC"], globals()["OUT"] = a.input, a.output
    sheets = dict(SHEETS)
    if not sheets:
        if not os.path.isdir(a.input):
            raise SystemExit(f"No such folder: {a.input}")
        for f in sorted(os.listdir(a.input)):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                sheets[os.path.splitext(f)[0]] = f
    if not sheets:
        raise SystemExit(f"No image files found in {a.input}")

    os.makedirs(a.output, exist_ok=True)
    for name, filename in sheets.items():
        extract(name, filename, cell_w=a.cell_width, skip_top=a.skip_top)
        contact(name)
    print(f"\nDone. Review the contact_*.png files in {a.output}, then run "
          "build_animations.py to map indices to animations.")


if __name__ == "__main__":
    main()
