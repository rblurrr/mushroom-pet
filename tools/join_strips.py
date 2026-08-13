"""Join several part-strips into one clean, evenly-gutted animation strip.

Smoothness is frame count, and frame count fights image size: ask one 1536-wide image
for twelve frames and each frame gets 128 pixels, so the art gets small and mushy and
the poses stop being readable. The fix is to generate a long cycle in halves --
frames 1-6 in one image, 7-12 in another, both at full size -- and stitch them here.

    python assets/_raw/join_strips.py walk_a.png walk_b.png -o nyx/strips/walk.png

It does not simply paste the images together. Each input is sliced into its own frames
first, then every frame is re-laid onto one canvas with an identical gutter between
each pair. That matters: build_from_strips.py finds frame boundaries by looking for the
*widest* empty columns, so a seam that is wider than the gaps inside each half would
make it split the strip into two frames instead of twelve. Uniform gutters remove the
guesswork.

Frames keep their own size and sit on a common bottom line, which is exactly what
build_from_strips.py expects to see.
"""
from __future__ import annotations
import argparse
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_from_strips import slice_strip          # noqa: E402

BG = (10, 10, 18)          # the flat #0a0a12 the prompts ask for
GUTTER = 48                # empty columns between frames
MARGIN = 24                # empty border around the whole strip


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="part strips, in playback order")
    ap.add_argument("-o", "--out", required=True, help="strip to write")
    ap.add_argument("--frames", type=int, default=None,
                    help="frames per input image, if their own gutters are too tight "
                         "to detect (forces an even split of each input)")
    ap.add_argument("--gutter", type=int, default=GUTTER,
                    help=f"empty columns between frames (default {GUTTER})")
    args = ap.parse_args(argv)

    frames = []
    for path in args.inputs:
        p = path if os.path.isabs(path) else os.path.join(HERE, path)
        if not os.path.exists(p):
            p = path
        got = slice_strip(p, args.frames)
        if not got:
            sys.exit(f"no frames found in {path} -- is the background flat and dark?")
        print(f"  {os.path.basename(path):24} {len(got)} frames")
        frames += got

    if len(frames) < 2:
        sys.exit("only one frame in total -- nothing to join")

    w = MARGIN * 2 + sum(f.width for f in frames) + args.gutter * (len(frames) - 1)
    h = MARGIN * 2 + max(f.height for f in frames)
    out = Image.new("RGB", (w, h), BG)
    x = MARGIN
    for f in frames:
        out.paste(f, (x, h - MARGIN - f.height), f)      # common bottom line
        x += f.width + args.gutter

    dest = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    out.save(dest)
    print(f"\nwrote {dest}  ({len(frames)} frames, {w}x{h})")
    print("now run build_from_strips.py on the pack")


if __name__ == "__main__":
    main()
