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
