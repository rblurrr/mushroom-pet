"""Turn one-animation-per-image sprite strips into a character pack animation.

The original pipeline (cort_extract.py + cort_build.py) cut ~80 poses out of two big
reference sheets and mapped them to animations by hand-written index. That works, but
every new animation means re-indexing a table by eye, and it's why most animations
ended up with a single frame.

This is the replacement, matched to SPRITE_PROMPTS.md: one image per animation, frames
in a row. Slicing a row is easy and unambiguous, so the frame count comes from the art
rather than from a table someone has to keep in sync.

    python assets/_raw/build_from_strips.py cortana
    python assets/_raw/build_from_strips.py cortana --only walk climb
    python assets/_raw/build_from_strips.py cortana --dry-run

Reads   assets/_raw/<pack>/strips/<anim>.png
Writes  assets/characters/<pack>/<anim>/NN.png   and updates manifest.json

Needs pillow and numpy. scipy is used if present for slightly cleaner keying, but the
script works without it.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

try:
    from scipy import ndimage
except ImportError:                       # optional
    ndimage = None

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")

# Frames-per-second and looping for anything new. Anything already in the pack's
# manifest keeps its existing timing, so re-running never undoes hand tuning.
TIMING = {
    "idle": (5, True), "idle_alt": (4.5, True), "look": (4, True),
    "walk": (12, True), "run": (15, True), "climb": (10, True), "hang": (3.5, True),
    "jump": (12, False), "fall": (9, True), "land": (10, False), "turn": (9, False),
    "sit": (1.5, True), "lie": (1.5, True), "sleep": (1.6, True),
    "wave": (5, False), "cheer": (6, False), "clap": (7, True), "dance": (5, True),
    "happy": (8, False), "look": (4, True), "excited": (7, False),
    "startle": (9, False), "stretch": (4, False), "yawn": (3.5, False),
    "reach": (11, False), "grab": (4, True), "swing": (5, True),
    "bounce": (11, False), "flung": (12, True),
    "trip": (10, False), "dizzy": (6, True), "taunt": (4, True), "dangle": (2.5, True),
    "applaud": (7, True), "facepalm": (3, True),
    "dash": (14, True), "slide": (9, False), "hover": (6, True), "vault": (10, False),
    "wall_push": (12, False), "spin": (12, True),
}
DEFAULT_TIMING = (6, True)

LUM_T = 30          # background is flat #0a0a12, so a low luminance cut is enough
MIN_FRAME_W = 14
MIN_FRAME_H = 24


def key_alpha(rgb: np.ndarray) -> np.ndarray:
    """Boolean mask of 'this is the character, not the flat backdrop'."""
    lum = rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    m = lum > LUM_T
    if ndimage is not None:
        m = ndimage.binary_closing(m, np.ones((3, 3)))
        m = ndimage.binary_fill_holes(m)
    return m


def _runs(flags) -> list[tuple[int, int]]:
    spans, start = [], None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(flags)))
    return spans


def columns(mask: np.ndarray) -> list[tuple[int, int]]:
    """Split a strip into frames on the vertical bands of empty background.

    The character has its own internal gaps -- between the legs, between a swung arm
    and the body -- so a fixed gap threshold either merges frames together or shatters
    one frame into three. The gutters between frames are reliably the *widest* empty
    runs in the image, though, so the threshold is derived from the widest one found
    rather than guessed up front.
    """
    ink = mask.any(axis=0)
    blobs = _runs(ink)
    if len(blobs) <= 1:
        return [(a, b) for a, b in blobs if (b - a) >= MIN_FRAME_W]

    gaps = [(blobs[i][1], blobs[i + 1][0]) for i in range(len(blobs) - 1)]
    widest = max(b - a for a, b in gaps)
    cut = max(4.0, widest * 0.55)
    out, cur = [], list(blobs[0])
    for (a, b), nxt in zip(gaps, blobs[1:]):
        if (b - a) >= cut:
            out.append(tuple(cur))
            cur = list(nxt)
        else:
            cur[1] = nxt[1]
    out.append(tuple(cur))
    return [(a, b) for a, b in out if (b - a) >= MIN_FRAME_W]


def even_columns(mask: np.ndarray, n: int) -> list[tuple[int, int]]:
    """Fall back to an even split across the inked region -- for touching frames."""
    ink = np.where(mask.any(axis=0))[0]
    if not len(ink):
        return []
    x0, x1 = int(ink.min()), int(ink.max()) + 1
    pitch = (x1 - x0) / n
    return [(int(x0 + i * pitch), int(x0 + (i + 1) * pitch)) for i in range(n)]


def slice_strip(path: str, frames: int | None = None):
    """-> [RGBA frame images], left to right, background removed."""
    im = Image.open(path).convert("RGB")
    rgb = np.array(im)
    mask = key_alpha(rgb)
    if not mask.any():
        return []
    spans = even_columns(mask, frames) if frames else columns(mask)

    out = []
    for (x0, x1) in spans:
        sub = mask[:, x0:x1]
        rows = np.where(sub.any(axis=1))[0]
        if not len(rows) or (rows.max() - rows.min() + 1) < MIN_FRAME_H:
            continue
        y0, y1 = rows.min(), rows.max() + 1
        cut = rgb[y0:y1, x0:x1]
        a = (sub[y0:y1] * 255).astype(np.uint8)
        out.append(Image.fromarray(np.dstack([cut, a]), "RGBA"))
    return out


def place(im: Image.Image, canvas, baseline, target_h) -> Image.Image:
    """Scale to a common height, centre horizontally, sit on the baseline."""
    if im.height != target_h:
        w = max(1, round(im.width * target_h / im.height))
        im = im.resize((w, target_h), Image.NEAREST)
    if im.width > canvas[0]:
        s = canvas[0] / im.width
        im = im.resize((canvas[0], max(1, int(im.height * s))), Image.NEAREST)
    c = Image.new("RGBA", canvas, (0, 0, 0, 0))
    c.alpha_composite(im, ((canvas[0] - im.width) // 2, max(0, baseline - im.height)))
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack", help="character pack folder name, e.g. cortana")
    ap.add_argument("--only", nargs="*", default=None,
                    help="only rebuild these animations")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    ap.add_argument("--height", type=float, default=None,
                    help="character height in canvas px (default: keep the pack's "
                         "existing proportions)")
    ap.add_argument("--frames", type=int, default=None,
                    help="force an even N-way split instead of detecting the gutters; "
                         "use this when the generated frames touch each other")
    args = ap.parse_args(argv)

    strips = os.path.join(HERE, args.pack, "strips")
    dest = os.path.join(ASSETS, "characters", args.pack)
    man_path = os.path.join(dest, "manifest.json")
    if not os.path.isdir(strips):
        sys.exit(f"no strips folder: {strips}\n"
                 f"put one <animation>.png per animation in there first "
                 f"(see assets/_raw/SPRITE_PROMPTS.md)")
    if not os.path.exists(man_path):
        sys.exit(f"no manifest at {man_path} -- this only updates an existing pack")

    with open(man_path, encoding="utf-8") as fh:
        man = json.load(fh)
    canvas = (man["canvas"]["w"], man["canvas"]["h"])
    baseline = man["canvas"]["baseline"]
    target_h = int(args.height) if args.height else int(baseline * 0.67)

    files = sorted(f for f in os.listdir(strips) if f.lower().endswith(".png"))
    if args.only:
        want = set(args.only)
        files = [f for f in files if os.path.splitext(f)[0] in want]
    if not files:
        sys.exit("no matching strip images found")

    print(f"pack {args.pack}: canvas {canvas} baseline {baseline} "
          f"character height {target_h}px")
    changed = 0
    for fn in files:
        anim = os.path.splitext(fn)[0]
        frames = slice_strip(os.path.join(strips, fn), args.frames)
        if not frames:
            print(f"  !! {anim:12} no frames found -- is the background flat and dark?")
            continue
        if len(frames) == 1 and args.frames is None:
            print(f"  !! {anim:12} only found 1 frame -- the frames are probably "
                  f"touching. Re-run with --only {anim} --frames N")
        # one shared height keeps his feet from growing and shrinking between frames
        tallest = max(f.height for f in frames)
        scaled = [place(f, canvas, baseline,
                        max(1, round(f.height * target_h / tallest))) for f in frames]
        old = man["anims"].get(anim, {})
        fps, loop = TIMING.get(anim, DEFAULT_TIMING)
        note = ""
        if old:
            fps, loop = old.get("fps", fps), old.get("loop", loop)
            note = f"  (was {old.get('frames', '?')} frames, keeping fps={fps})"
        print(f"  {anim:12} {len(scaled):3} frames  fps={fps} loop={loop}{note}")
        changed += 1
        if args.dry_run:
            continue
        d = os.path.join(dest, anim)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for i, f in enumerate(scaled):
            f.save(os.path.join(d, f"{i:02d}.png"))
        man["anims"][anim] = {"frames": len(scaled), "fps": fps, "loop": loop,
                              "dir": anim, "scale": old.get("scale", 1.0)}

    if args.dry_run:
        print(f"\ndry run -- {changed} animations would be written")
        return
    tmp = man_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=2)
    os.replace(tmp, man_path)
    print(f"\nwrote {changed} animations and updated {man_path}")
    print("restart the pet to pick them up")


if __name__ == "__main__":
    main()
