"""Turn the raw extracted sprites into a normalised, bottom-aligned animation pack.

Every frame lands on the same canvas with its feet on the same baseline, so the pet
doesn't jitter vertically when the animation changes. Fire frames are scaled a touch
larger than the cute frames because angry mushroom should read as bigger.
"""
import os, json, shutil
import numpy as np
from PIL import Image

# Input is whatever extract_sprites.py produced; output is the pet's assets folder.
W3 = os.environ.get("SPRITE_OUT", "work")
DEST = os.environ.get("ASSET_OUT", "assets")

CANVAS = (208, 168)          # w, h  -- generous so flames/props aren't clipped
BASELINE = 162               # feet sit here
CUTE_H = 116                 # normalised body height for cute frames
FIRE_H = 132                 # angry frames are chunkier

# animation name -> [(sheet folder, sprite index), ...]
# Look at the contact_*.png files from extract_sprites.py to find the indices.
ANIMS = {
    "idle":       [("cute2", i) for i in (0, 1, 2, 3, 4)] + [("cute1", 0)],
    "look":       [("cute2", i) for i in (10, 11, 12, 13, 14)],
    "walk":       [("walk", i) for i in range(0, 9)],
    "run":        [("walk", i) for i in range(9, 18)],
    "sit":        [("cute1", i) for i in (10, 11, 15, 16, 17)],
    "lie":        [("cute1", 9), ("cute1", 19), ("cute2", 9)],
    "sleep":      [("cute1", 29), ("cute1", 30), ("cute1", 27), ("cute1", 28)],
    "wave":       [("cute1", 31), ("cute1", 4), ("cute1", 3), ("cute1", 32)],
    "happy":      [("cute1", 23), ("cute1", 24), ("cute1", 21), ("cute1", 20)],
    "love":       [("walk", 23), ("cute1", 25), ("cute1", 22)],
    "eat":        [("cute1", 7), ("cute1", 13), ("cute1", 12)],
    "startle":    [("cute1", 5), ("cute1", 2), ("cute2", 18), ("cute2", 19)],
    "fish":       [("cute1", 34)],
    "box":        [("cute1", 33)],

    "fire_walk":  [("walk", i) for i in range(36, 48)],
    "fire_idle":  [("fire", i) for i in (3, 4, 5, 6, 7, 8)],
    "fire_glare": [("fire", i) for i in (21, 22, 23, 24, 25, 26)],
    "fire_roar":  [("fire", i) for i in (30, 31, 32, 39, 40, 41, 48, 49)],
    "fire_calm":  [("fire", i) for i in (18, 19, 20, 27, 28, 29)],
    "fire_smoke": [("fire", 36), ("fire", 37), ("fire", 47), ("fire", 50)],
    "fire_wake":  [("fire", 0), ("fire", 9), ("fire", 10), ("fire", 11)],
    "fire_down":  [("fire", 51), ("fire", 52), ("fire", 53)],
}

# frames-per-second + loop behaviour per animation
TIMING = {
    "idle": (5, True), "look": (4, True), "walk": (13, True), "run": (18, True),
    "sit": (3, True), "lie": (2, True), "sleep": (2.2, True), "wave": (7, False),
    "happy": (8, False), "love": (5, False), "eat": (4, True), "startle": (11, False),
    "fish": (1, True), "box": (1, True),
    "fire_walk": (15, True), "fire_idle": (7, True), "fire_glare": (6, True),
    "fire_roar": (11, False), "fire_calm": (5, True), "fire_smoke": (5, False),
    "fire_wake": (7, False), "fire_down": (6, False),
}


def trim(im):
    a = np.array(im)[..., 3]
    ys, xs = np.where(a > 8)
    if not len(ys):
        return im
    return im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def place(im, target_h):
    im = trim(im)
    s = target_h / im.height
    w, h = max(1, round(im.width * s)), max(1, round(im.height * s))
    im = im.resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    x = (CANVAS[0] - w) // 2
    y = BASELINE - h
    canvas.alpha_composite(im, (x, max(0, y)))
    return canvas


def main():
    if os.path.isdir(DEST):
        shutil.rmtree(DEST)
    os.makedirs(DEST)
    manifest = {"canvas": {"w": CANVAS[0], "h": CANVAS[1], "baseline": BASELINE}, "anims": {}}
    for anim, items in ANIMS.items():
        d = os.path.join(DEST, anim)
        os.makedirs(d, exist_ok=True)
        th = FIRE_H if anim.startswith("fire") else CUTE_H
        n = 0
        for (sheet, idx) in items:
            src = os.path.join(W3, sheet, f"{idx:03d}.png")
            if not os.path.exists(src):
                print("  !! missing", src)
                continue
            out = place(Image.open(src).convert("RGBA"), th)
            out.save(os.path.join(d, f"{n:02d}.png"))
            n += 1
        fps, loop = TIMING.get(anim, (6, True))
        manifest["anims"][anim] = {"frames": n, "fps": fps, "loop": loop, "dir": anim}
        print(f"{anim:12s} {n} frames")
    json.dump(manifest, open(os.path.join(DEST, "manifest.json"), "w"), indent=2)

    # a tray / window icon from a clean idle frame
    icon = Image.open(os.path.join(W3, "cute2", "001.png")).convert("RGBA")
    icon = trim(icon)
    side = max(icon.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.alpha_composite(icon, ((side - icon.width) // 2, (side - icon.height) // 2))
    sq.resize((256, 256), Image.LANCZOS).save(os.path.join(DEST, "icon.png"))
    sq.resize((256, 256), Image.LANCZOS).save(
        os.path.join(DEST, "icon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=W3, help="folder of cut sprites")
    ap.add_argument("--output", default=DEST, help="assets folder to write")
    a = ap.parse_args()
    W3, DEST = a.input, a.output
    main()
