"""Scaffold a brand-new character pack so build_from_strips.py has something to fill.

build_from_strips.py only ever *updates* a pack -- it needs a manifest to merge into so
that hand-tuned fps values survive a rebuild. That's the right call for cortana and
mushroom, and useless for a character that doesn't exist yet. This makes the empty shell:

    python assets/_raw/new_pack.py nyx
    python assets/_raw/new_pack.py pip --canvas 192 168 --baseline 162

Then drop your strips in assets/_raw/<name>/strips/ and run build_from_strips.py.

Nothing is overwritten: if the pack already exists the script says so and stops.
An empty pack is skipped by characters.discover() until it has real animations in it,
so a half-finished character can sit on disk without breaking the running pet.
"""
from __future__ import annotations
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="pack folder name, lowercase, e.g. nyx")
    ap.add_argument("--canvas", nargs=2, type=int, metavar=("W", "H"),
                    default=[192, 160],
                    help="frame canvas in pixels (default 192 160)")
    ap.add_argument("--baseline", type=int, default=None,
                    help="y of the ground line inside the canvas (default: H - 6)")
    ap.add_argument("--painterly", action="store_true",
                    help="smooth scaling instead of nearest-neighbour pixel art")
    args = ap.parse_args(argv)

    name = args.name.strip().lower().replace(" ", "_")
    w, h = args.canvas
    baseline = args.baseline if args.baseline is not None else h - 6

    dest = os.path.join(ASSETS, "characters", name)
    strips = os.path.join(HERE, name, "strips")
    man_path = os.path.join(dest, "manifest.json")
    if os.path.exists(man_path):
        sys.exit(f"{name} already exists at {dest} -- nothing changed")

    os.makedirs(dest, exist_ok=True)
    os.makedirs(strips, exist_ok=True)
    manifest = {
        "canvas": {"w": w, "h": h, "baseline": baseline},
        "pixel_art": not args.painterly,
        "max_anim_scale": 1.0,
        "anims": {},
    }
    with open(man_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"created  {man_path}")
    print(f"created  {strips}")
    print()
    print("next:")
    print(f"  1. save one image per animation as {os.path.join(strips, '<anim>.png')}")
    print(f"     (idle, walk, run, climb, happy -- see CHARACTER_PROMPTS.md)")
    print(f"  2. python assets/_raw/build_from_strips.py {name} --dry-run")
    print(f"  3. python assets/_raw/build_from_strips.py {name}")
    print(f"  4. copy a good idle frame to {os.path.join(dest, 'icon.png')}")
    print(f"  5. give it a voice in mushroom/voices.py, then restart the pet")


if __name__ == "__main__":
    main()
