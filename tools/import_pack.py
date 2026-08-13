"""Import a `pixel_character_animation_pack` export into pet character packs.

The animation-pack format and the pet's format disagree in four ways that all have to be
reconciled or the character jitters, drifts in size, or floats off the floor:

1. **Per-animation cell sizes.** The pack exports each animation at whatever its source
   atlas used -- 181x181, 192x205, 176x242. The pet needs one canvas for the whole
   character so switching pose never moves its feet.

2. **No shared baseline.** Where the character sits inside its cell varies per animation,
   and by up to 90px. Bottom-aligning every frame individually would fix the feet but
   flatten genuine airborne motion (falls, pounces). So each animation is aligned by *its
   own lowest frame* -- that frame is the ground contact -- and every other frame keeps
   its relative rise.

3. **Scale.** The character is drawn at slightly different sizes across atlas pages. One
   scale per character, derived from the `idle` standing height, brings them together
   without squashing poses that are legitimately taller (a rearing cat, a climb reach).

4. **Speckle.** Some frames carry a few stray keyed pixels away from the body. Left in,
   they widen the bounding box and throw the centring off.

    python assets/_raw/import_pack.py "../pixel_character_animation_pack"
    python assets/_raw/import_pack.py <src> --only nyx --dry-run

Needs pillow, numpy and scipy.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import shutil
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")

# On-screen standing height, in canvas pixels. Cortana stands 98px in a 148px canvas and
# the mushroom 116px in 168px; matching that keeps every character the same size on the
# desktop at a given size setting.
TARGET_STANDING = 108.0
ALPHA_T = 16                # alpha above this counts as the character
SPECKLE_FRAC = 0.005        # drop blobs smaller than this share of the biggest one
NEAR_FRAC = 0.10            # a detached blob further than this from the body is bleed

# Which way each pack's art points. The pet assumes right and mirrors from there, so a
# character generated facing left has to say so or it walks backwards -- and climbs with
# its back to the window. Judged by eye once per pack; there's no reliable way to infer
# "which way is this creature looking" from pixels.
FACES = {"pip": -1}


def clean(im: Image.Image):
    """-> (RGBA image with only the character on it, bbox) or (None, None) if empty.

    The pack exports fixed-size cells, and where a source atlas row was taller than its
    cell the neighbouring row bleeds into the bottom of the frame -- Nyx's run frames
    each carry a slice of the cats from the row below. That bleed is a separate blob some
    distance from the body, so anything detached and far from the largest component goes.
    Detached blobs *near* the body are kept: a raised paw, a thrown washer, a sword glint
    are all legitimately disconnected.
    """
    arr = np.array(im)
    solid = arr[..., 3] > ALPHA_T
    if not solid.any():
        return None, None
    lbl, n = ndimage.label(solid, np.ones((3, 3)))
    if n > 1:
        sizes = ndimage.sum(solid, lbl, range(1, n + 1))
        boxes = ndimage.find_objects(lbl)
        main = int(np.argmax(sizes)) + 1
        my, mx = boxes[main - 1]
        pad = max(6.0, max(im.size) * NEAR_FRAC)
        keep_ids = []
        for i in range(1, n + 1):
            if i == main:
                keep_ids.append(i)
                continue
            if sizes[i - 1] < sizes.max() * SPECKLE_FRAC:
                continue
            ys, xs = boxes[i - 1]
            gap_y = max(my.start - ys.stop, ys.start - my.stop, 0)
            gap_x = max(mx.start - xs.stop, xs.start - mx.stop, 0)
            if math.hypot(gap_x, gap_y) <= pad:
                keep_ids.append(i)
        keep = np.isin(lbl, keep_ids)
        if not keep.all():
            arr = arr.copy()
            arr[..., 3] = np.where(keep, arr[..., 3], 0)
            im = Image.fromarray(arr, "RGBA")
            solid = keep
    ys, xs = np.where(solid)
    return im, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


FOOT_WIDTH_FRAC = 0.18      # a row this wide is body/feet, not a dangling tail tip


def foot_line(im: Image.Image, bb) -> int:
    """The y where the character actually meets the ground.

    Not the bounding box bottom: a cat's tail, a cape or a trailing strap can hang below
    the feet, and using the lowest *pixel* makes whichever frame has the droopiest tail
    define the floor -- which then lifts every other frame in the animation off the
    ground. So walk up from the bottom until a row is wide enough to be body rather than
    a trailing wisp.
    """
    a = np.array(im)[bb[1]:bb[3], bb[0]:bb[2], 3] > ALPHA_T
    if not a.any():
        return bb[3]
    widths = a.sum(axis=1)
    thresh = max(2.0, widths.max() * FOOT_WIDTH_FRAC)
    rows = np.where(widths >= thresh)[0]
    return bb[1] + int(rows.max()) + 1 if len(rows) else bb[3]


def foot_centre(im: Image.Image, bb, foot) -> float:
    """Horizontal anchor: the middle of the feet, not the middle of the bounding box.

    Centring on the bounding box makes a swinging tail or an outstretched sword drag the
    whole body sideways from frame to frame, which reads as the character sliding about
    while it walks. The feet are the part that's supposed to stay put.
    """
    a = np.array(im)[..., 3] > ALPHA_T
    lo = max(bb[1], foot - max(4, int((foot - bb[1]) * 0.25)))
    band = a[lo:foot, bb[0]:bb[2]]
    if band.any():
        xs = np.where(band.any(axis=0))[0]
        return bb[0] + (int(xs.min()) + int(xs.max()) + 1) / 2.0
    return (bb[0] + bb[2]) / 2.0


def load_anim(src_root, meta):
    """-> [(image, bbox, foot_y, foot_cx)] for one animation, cleaned."""
    out = []
    for rel in meta["frames"]:
        p = os.path.join(src_root, rel)
        if not os.path.exists(p):
            continue
        im, bb = clean(Image.open(p).convert("RGBA"))
        if im is not None:
            foot = foot_line(im, bb)
            out.append((im, bb, foot, foot_centre(im, bb, foot)))
    return out


def convert(src_root, char_id, cmeta, dry=False, faces=None):
    faces = FACES.get(char_id, 1) if faces is None else faces
    man_path = os.path.join(src_root, cmeta["manifest"])
    with open(man_path, encoding="utf-8") as fh:
        src = json.load(fh)
    src_dir = os.path.dirname(man_path)

    anims = {}
    for name, meta in src["animations"].items():
        frames = load_anim(src_root, meta)
        if frames:
            anims[name] = (meta, frames)
    if not anims:
        print(f"  !! {char_id}: no frames found")
        return None

    # ---- one scale for the whole character, keyed off its standing pose ----
    ref = "idle" if "idle" in anims else next(iter(anims))
    ref_h = max(bb[3] - bb[1] for _, bb, _, _ in anims[ref][1])
    scale = TARGET_STANDING / max(1.0, ref_h)

    # ---- first pass: where does every frame land, and how big must the canvas be? ----
    placed = {}
    need_l = need_r = need_h = 0
    for name, (meta, frames) in anims.items():
        # the animation's lowest foot line is its ground contact; everything else rises
        floor = max(f for _, _, f, _ in frames)
        entries = []
        for im, bb, foot, cx in frames:
            w = max(1, round((bb[2] - bb[0]) * scale))
            h = max(1, round((bb[3] - bb[1]) * scale))
            # measured at the feet, but the sprite is placed by its bounding box, so
            # carry the offsets from the anchor through into the paste position
            rise = round((floor - foot) * scale)      # 0 for the grounded frame
            below = round((bb[3] - foot) * scale)     # tail/cape hanging under the feet
            left = round((cx - bb[0]) * scale)        # anchor's offset inside the sprite
            entries.append((im, bb, w, h, rise, below, left))
            need_l = max(need_l, left)
            need_r = max(need_r, w - left)
            need_h = max(need_h, h + rise - below)
        placed[name] = entries

    # room below the baseline for anything that legitimately hangs under the feet
    overhang = max((e[5] for lst in placed.values() for e in lst), default=0)
    canvas_w = int(2 * max(need_l, need_r) + 12)
    baseline = int(need_h + 4)
    canvas_h = baseline + int(overhang) + 8
    canvas = (canvas_w, canvas_h)

    print(f"  {char_id:8} {len(anims):2} anims  scale={scale:.3f}  "
          f"canvas={canvas_w}x{canvas_h} baseline={baseline}  "
          f"standing={round(ref_h * scale)}px  "
          f"art faces {'left' if faces < 0 else 'right'}")
    if dry:
        return None

    dest = os.path.join(ASSETS, "characters", char_id)
    os.makedirs(dest, exist_ok=True)
    # Standing height, not canvas height, is what the pet should hang from when it
    # catches the cursor -- a tall canvas (Nyx rears up in feral_idle) would otherwise
    # put its "hands" above its own head.
    out_man = {"canvas": {"w": canvas_w, "h": canvas_h, "baseline": baseline,
                          "standing": round(ref_h * scale)},
               "pixel_art": True, "max_anim_scale": 1.0,
               "faces": faces,
               "source": f"pixel_character_animation_pack/{char_id}",
               "display_name": cmeta.get("display_name", char_id.title()),
               "signature": src.get("signature_animation"),
               "anims": {}}

    for name, entries in placed.items():
        meta = anims[name][0]
        d = os.path.join(dest, name)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for i, (im, bb, w, h, rise, below, left) in enumerate(entries):
            body = im.crop(bb).resize((w, h), Image.NEAREST)
            c = Image.new("RGBA", canvas, (0, 0, 0, 0))
            # feet on the baseline (minus any rise) and under the canvas centre line;
            # tail, cape or sword free to hang past either
            c.alpha_composite(body, (canvas_w // 2 - left, baseline - h - rise + below))
            c.save(os.path.join(d, f"{i:02d}.png"))
        # These packs author complete 8- and 16-frame cycles that already close on
        # themselves. characters.PLAYBACK exists to stretch the older five-frame packs
        # -- ping-ponging or holding a frame here would put a visible hitch in a loop
        # that was fine. Say so explicitly so the shared table can't reach in.
        out_man["anims"][name] = {"frames": len(entries),
                                  "fps": float(meta.get("fps", 8)),
                                  "loop": bool(meta.get("loop", True)),
                                  "dir": name, "scale": 1.0,
                                  "pingpong": False, "hold": {}, "fps_scale": 1.0,
                                  "category": meta.get("category", "normal")}

    # icon from the first idle frame
    ic_src = placed.get(ref) or next(iter(placed.values()))
    im, bb = ic_src[0][0], ic_src[0][1]
    body = im.crop(bb)
    side = max(body.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.alpha_composite(body, ((side - body.width) // 2, (side - body.height) // 2))
    sq = sq.resize((256, 256), Image.NEAREST)
    sq.save(os.path.join(dest, "icon.png"))
    try:
        sq.save(os.path.join(dest, "icon.ico"),
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except Exception:
        pass
    ref_png = os.path.join(src_dir, src.get("reference", "reference.png"))
    if os.path.exists(ref_png):
        shutil.copy2(ref_png, os.path.join(dest, "reference.png"))

    tmp = os.path.join(dest, "manifest.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out_man, fh, indent=2)
    os.replace(tmp, os.path.join(dest, "manifest.json"))
    return out_man


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="folder holding pack_manifest.json")
    ap.add_argument("--only", nargs="*", default=None, help="only these character ids")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--faces", type=int, choices=(1, -1), default=None,
                    help="which way the art points; -1 if the character is "
                         "drawn facing left (default: the FACES table)")
    args = ap.parse_args(argv)

    src_root = os.path.abspath(args.source)
    pm = os.path.join(src_root, "pack_manifest.json")
    if not os.path.exists(pm):
        sys.exit(f"no pack_manifest.json in {src_root}")
    with open(pm, encoding="utf-8") as fh:
        pack = json.load(fh)

    print(f"importing from {src_root}")
    done = 0
    for char_id, cmeta in pack["characters"].items():
        if args.only and char_id not in args.only:
            continue
        if convert(src_root, char_id, cmeta, args.dry_run, args.faces) is not None:
            done += 1
    if args.dry_run:
        print("\ndry run -- nothing written")
    else:
        print(f"\nimported {done} characters into {os.path.join(ASSETS, 'characters')}")
        print("restart the pet; they appear under menu -> Character")


if __name__ == "__main__":
    main()
