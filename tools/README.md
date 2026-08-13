# Making your own sprites

The pet reads `assets/manifest.json` plus one folder of PNG frames per animation. Any art
works as long as it ends up in that shape.

If you have a sprite sheet (rows of frames on a plain or gradient background):

```bash
pip install pillow numpy scipy
python tools/extract_sprites.py      # cuts individual sprites out of the sheets
python tools/build_animations.py     # normalises them into assets/
```

`extract_sprites.py` finds sprites by *gradient energy* rather than background colour,
which is what makes it work on AI-generated sheets where a soft glow sits behind each
sprite. It writes numbered PNGs plus a labelled contact sheet so you can see which index
is which. Then edit the `ANIMS` table in `build_animations.py` to map those indices to
animation names, and the `TIMING` table for frames-per-second and looping.

Both scripts have hard-coded input/output paths at the top - point them at your own
folders before running.

Every frame is placed on a shared canvas with its feet on one baseline, which is what
stops the pet jittering vertically when it switches animations.

## Animations the pet looks for

Required: `idle`, `walk`, `run`, `look`, `sit`, `startle`
Nice to have: `lie`, `sleep`, `wave`, `happy`, `love`, `eat`, `fish`
Fire costume: `fire_walk`, `fire_idle`, `fire_glare`, `fire_roar`, `fire_calm`,
`fire_smoke`, `fire_wake`, `fire_down`

Anything missing falls back to `idle`, so a partial set still runs.

## Character packs

`assets/characters/<name>/` holds one pack per character: a `manifest.json` plus one
folder of PNG frames per animation. Five ship — `bolt`, `cortana`, `mushroom`, `nyx`
and `pip`.

| Tool | What it does |
|---|---|
| `new_pack.py <name>` | scaffolds an empty pack for a character you're about to draw |
| `build_from_strips.py <name>` | imports one-animation-per-image strips into a pack |
| `join_strips.py` | stitches a cycle generated in halves into one evenly-gutted strip |
| `import_pack.py <dir>` | imports a whole multi-character animation-pack export |

`SPRITE_PROMPTS.md`, `CHARACTER_PROMPTS.md` and `UNIVERSAL_PROMPT_KIT.md` are the
image-generation prompts that produce usable frames — one animation per image, every
frame described, explicit loop closure.

### manifest.json

```json
{
  "canvas": { "w": 142, "h": 134, "baseline": 118, "standing": 108 },
  "pixel_art": true,
  "faces": 1,
  "signature": "self_repair",
  "anims": { "walk": { "frames": 8, "fps": 12, "loop": true, "dir": "walk" } }
}
```

- `baseline` — y of the ground line inside the canvas. Every frame's feet sit on it, so
  changing animation never shifts the character vertically.
- `standing` — how tall it stands, which is separate from canvas height when a pack has
  one unusually tall pose.
- `faces` — which way the art points. `1` is right (the default the renderer assumes);
  `-1` for a pack drawn facing left, which is mirrored instead of walking backwards.
- `signature` — the one animation only this character has.
