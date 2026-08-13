# Sprite sheet prompts (reference-image workflow)

The first Cortana sheets packed ~80 poses into two images. That's why the animations look
rushed: the walk cycle got 6 frames, the run got 4, and nearly everything else got
**one**. No amount of code makes a one-frame animation move.

These prompts fix that at the source, using a **reference image** so the character stays
identical across every generation.

## Reference images

Attach one of these with every prompt:

- `assets/_raw/cortana_reference.png`
- `assets/_raw/mushroom_reference.png`

Each shows three full-body views plus a head close-up on the same flat backdrop the
prompts ask for — so the model can read the palette, proportions, outline weight and face
without you describing any of it in words. Describing a character in words is where drift
comes from; the reference removes that entirely.

## How to run a session

**Step 1 — paste this once, with the reference image attached.** It sets the rules for
everything that follows, so the per-animation prompts afterwards stay short.

> Here is the exact character I'm making a sprite sheet for. Study it carefully.
>
> For every image I ask for from now on, these rules always apply:
>
> **CHARACTER** — Match this reference exactly: same palette, same proportions, same hair
> shape and volume, same face, same costume details, same outline weight, same art style.
> Do not redesign, restyle, recolour, age, or "improve" the character. Do not add new
> accessories. Between frames, the **only** thing that changes is the pose.
>
> **LAYOUT** — All frames in ONE horizontal row, left to right, evenly spaced. Leave a
> wide band of empty background between each pair of frames so they never touch or
> overlap. In every frame the character is horizontally centred in its own cell, is
> **exactly the same height**, and its feet rest on the **same horizontal line**. Do not
> zoom in or out between frames.
>
> **BACKGROUND** — Flat solid `#0a0a12`, and absolutely nothing else on it. No glow, no
> drop shadow, no ground shadow, no floor, no platform, no panel borders, no grid lines,
> no captions, no numbers, no labels, no watermark. **No text of any kind anywhere in the
> image.**
>
> **STYLE** — True pixel art. Hard 1-pixel dark outline. No anti-aliasing, no gradients,
> no blur, no soft edges. Character about 320 pixels tall.
>
> **SIZE** — Landscape, 1536 × 1024.
>
> Reply "ready" and then wait for my first animation.

**Step 2 — paste one animation prompt per message.** Re-attach the reference every few
images; models drift over a long conversation.

**Step 3 — if quality slips**, paste this at the end of the offending prompt:

> Reminder: match the attached reference exactly, flat #0a0a12 background, no text or
> labels anywhere, wide gaps between frames, every frame the same height with feet on the
> same line.

---

# The prompts

Ordered by how much difference each makes. The first four are the ones you actually
*watch* all day.

---

### 1. `walk` — 12 frames

```
12 frames of ONE seamless side-view WALK CYCLE, facing right.

1  contact: right leg forward heel down, left leg back toe down, arms opposite
2  down: weight drops onto the right leg, body at its lowest, knees bent
3  passing low: left leg swinging under the body, still low
4  passing: left leg directly under the hips, body rising, legs closest together
5  up: pushing off the right toe, body at its highest point
6  reach: left leg extends forward, arms at full opposite swing
7  contact mirrored: left leg forward heel down, right leg back toe down
8  down mirrored: weight drops onto the left leg, body lowest again
9  passing low mirrored
10 passing mirrored: right leg under the hips, body rising
11 up mirrored: pushing off the left toe, body highest
12 reach mirrored: right leg extends forward, ready to land back into frame 1

The body rises and falls smoothly across the cycle. Hair and arms trail slightly behind
the body's motion. Frame 12 must lead straight back into frame 1 with no visible jump.
```

### 2. `idle` — 10 frames

```
10 frames of ONE seamless IDLE BREATHING loop, facing the viewer, standing still.

1-4   slow inhale: chest and shoulders rise a little, head lifts very slightly, hair
      settles upward
5     top of the breath, held
6-9   slow exhale: shoulders drop, head tips down a fraction, hair settles down
10    lowest point, leading straight back into frame 1

The motion is TINY — a few pixels of vertical movement only. The feet never move. This is
a subtle loop, not a bounce. Frame 10 must flow back into frame 1 seamlessly.
```

### 3. `climb` — 10 frames

The current one is 6 frames and reads as scrambling.

```
10 frames of ONE seamless CLIMBING CYCLE. The character climbs UP the right-hand edge of
a vertical surface: it faces left and grips a plain vertical ledge that runs down the
RIGHT side of every frame.

1  right hand high and gripping, left hand low, right knee raised
2  pulling up on the right arm, body starting to rise
3  body risen, left hand releasing
4  left hand reaching upward past the head
5  left hand grips high, weight transfers across
6  pulling up on the left arm, left knee raised (mirror of frame 1)
7  body rising on the left arm
8  right hand releasing
9  right hand reaching upward past the head
10 right hand grips high, leading straight back into frame 1

CRITICAL: the whole body — head, both arms, both legs — must be completely inside its
frame in all 10 frames, never cropped or cut off by the edge of the frame. Include a
plain dark vertical ledge edge on the right of each frame to grip. Frame 10 leads back
into frame 1.
```

### 4. `run` — 8 frames

```
8 frames of ONE seamless side-view RUN CYCLE, facing right. Faster and lower than a walk:
body leans forward, arms pump hard, both feet leave the ground.

1  right foot contact, body low, left arm forward
2  full weight down on the right leg, deepest compression
3  push off, body rising, left leg swinging through
4  airborne, both feet off the ground, legs crossing
5  left foot contact, body low, right arm forward
6  full weight down on the left leg
7  push off, body rising, right leg swinging through
8  airborne again, leading straight back into frame 1

Hair streams backward throughout. Frame 8 must lead back into frame 1 with no jump.
```

---

## The cursor-play set

New — the pet now grabs your actual mouse pointer and swings off it. Save these as the
filenames in the headings; the code already knows those names.

### 5. `reach` — 4 frames

```
4 frames of the character jumping upward to catch something floating just above its head.

1  ANTICIPATION: crouched, knees bent, arms swung back behind the body, looking up
2  LAUNCH: legs snapping straight, both arms thrown up overhead, just leaving the ground
3  RISE: airborne, body stretched long and vertical, both arms fully extended overhead,
   fingers open and reaching
4  CATCH: both hands closing together at the very top of the reach, body still stretched

Not a loop — one continuous upward jump from frame 1 to frame 4.
```

### 6. `grab` — 6 frames

```
6 frames of ONE seamless loop of the character HANGING by both hands from a fixed point
directly above its head, facing the viewer.

The hands are together at the very top of the body, arms straight up, body hanging
straight down below them, legs relaxed and dangling.

1-3  legs swing gently forward and the body twists very slightly
4-6  legs swing gently back, returning exactly to frame 1's pose

CRITICAL: in all 6 frames the hands are at the topmost point of the character with the
arms straight and vertical — the game hangs the character from that exact point. Do not
draw a rope, bar, hook or anything else being held. The hands grip empty air. Frame 6
leads back into frame 1.
```

### 7. `swing` — 8 frames

```
8 frames of the character SWINGING from a fixed grip point above its head, like a child
on a swing. Both hands stay together above the head with arms straight in every frame;
the body pivots underneath that grip.

1  body hanging straight down, at rest
2  body swung out to the left at a shallow angle, legs trailing left
3  body swung further left, roughly 45 degrees, hair swept left
4  full extent left, body nearly horizontal, legs kicked out, delighted expression
5  back through the bottom, body vertical, moving fast
6  swung out to the right at roughly 45 degrees, hair swept right
7  full extent right, body nearly horizontal, legs kicked out
8  back toward the bottom, leading into frame 1

The arms stay straight and locked overhead throughout — the whole body rotates as one
piece around the hands. Do not draw a rope, swing, bar or chain.
```

### 8. `bounce` — 6 frames

```
6 frames of the character BOUNCING on an invisible trampoline point under its feet.

1  falling, legs reaching down, arms up, about to make contact
2  IMPACT: feet planted, knees fully bent, body squashed wide and short, arms flung out
3  compression held, the deepest squash, an excited expression
4  launching, legs snapping straight, body stretched tall and thin, arms coming down
5  rising fast, body stretched vertical, hair pushed down by the air
6  top of the bounce, body neutral, arms out, about to fall back into frame 1

Exaggerate the squash in frames 2-3 and the stretch in frames 4-5 — this should read as
springy and comic.
```

### 9. `flung` — 6 frames

```
6 frames of ONE seamless loop of the character TUMBLING through the air after being
thrown, arms and legs tucked in, hair whipped around by the spin.

Each frame rotates the character 60 degrees further around, so the six frames make one
complete 360-degree tumble: frame 1 upright, frame 2 tipped onto its side, frame 3 nearly
upside down, frame 4 fully inverted, frame 5 coming back round, frame 6 almost upright
and leading straight back into frame 1.

The expression is somewhere between thrilled and alarmed. Frame 6 loops to frame 1.
```

---

## The comedy set

### 10. `trip` — 5 frames

```
5 frames of the character TRIPPING while running to the right and going down.

1  running, right foot catching on nothing
2  overbalancing forward, arms starting to windmill
3  fully airborne and horizontal, face-first, arms flailing out ahead, one leg kicked up
   behind, thoroughly undignified
4  face-planting, body compressed against the ground, dust
5  sitting up on the ground, dazed, one hand rubbing its head, embarrassed expression

Not a loop — one continuous fall from frame 1 to frame 5.
```

### 11. `dizzy` — 6 frames

```
6 frames of ONE seamless loop of the character being DIZZY: standing but wobbling, eyes
as spirals, head lolling from side to side, arms out for balance.

1-3  head and body sway to the left, weight shifting onto the left foot
4-6  head and body sway to the right, returning exactly to frame 1's pose

Frame 6 leads back into frame 1.
```

### 12. comedy poses — 8 frames

Save as `taunt.png` and split, or generate individually — the builder handles either.

```
8 separate comedic poses. Each is a single still pose, not a cycle.

1  TAUNT: hands on hips, head tilted, smug, one eyebrow raised
2  SHRUG: both palms up, shoulders raised, head tilted, blank expression
3  FACEPALM: one hand covering the face, head bowed, shoulders slumped
4  STRETCH: arms stretched high overhead, back arched, up on tiptoes
5  YAWN: wide open-mouthed yawn, one hand covering the mouth, eyes squeezed shut
6  APPLAUD: mid-clap, both hands together in front of the chest, delighted
7  POINT: one arm extended straight out to the right, pointing, looking that way
8  THINK: one hand on the chin, head tilted up, eyes looking up and to the side

All 8 the same height with feet on the same baseline.
```

### 13. `dangle` — 6 frames

```
6 frames of ONE seamless loop of the character SITTING on the edge of a surface, seen
from the side, facing right, legs hanging over the front and kicking idly. Leaning back
on both hands, relaxed and content.

1-3  legs swing forward, the near leg leading
4-6  legs swing back, returning exactly to frame 1's pose

Do not draw the surface it's sitting on — just the character in a seated pose with its
legs hanging. Frame 6 leads back into frame 1.
```

---

## Movement extras

### 14. `jump` — 8 frames

```
8 frames covering one jump and its landing, facing right.
1-2  crouch and launch
3-4  rising, body stretched upward, legs trailing
5    apex, body neutral, arms out, looking ahead
6-7  falling, legs reaching down, hair pushed upward by the air
8    landing impact, knees deeply bent, body squashed, arms forward
```

### 15. `turn` — 6 frames

```
6 frames of the character TURNING ON THE SPOT from facing right to facing left.
1  full side profile facing right
2  rotated slightly toward the viewer
3  three-quarter view toward the viewer
4  facing the viewer straight on
5  three-quarter view toward the left
6  full side profile facing left
The feet pivot in place; the character does not move sideways.
```

### 16. `sleep` — 6 frames

```
6 frames of ONE seamless loop of the character ASLEEP, curled up on the ground, seen from
the side, eyes closed, peaceful.
1-3  slow deep inhale, the body swelling very slightly
4-6  slow exhale, settling back to exactly frame 1's pose
Tiny motion only. No "Z" letters, no symbols, no text. Frame 6 loops to frame 1.
```

---

## After the images land

1. Save each as `assets/_raw/<pack>/strips/<animation>.png`, named exactly as in the
   headings above: `walk`, `idle`, `climb`, `run`, `reach`, `grab`, `swing`, `bounce`,
   `flung`, `trip`, `dizzy`, `dangle`, `jump`, `turn`, `sleep`.
2. Run:

   ```bash
   python assets/_raw/build_from_strips.py cortana --dry-run   # check the frame counts
   python assets/_raw/build_from_strips.py cortana             # write them in
   ```

3. Restart the pet.

The builder slices on the gutters between frames, keys out the background, normalises
every frame to one height and baseline, and updates `manifest.json` — keeping any fps
you'd already hand-tuned.

**If it reports "only found 1 frame"**, the generated frames are touching each other.
Either regenerate with *"leave a much wider empty gap between each frame"*, or force an
even split:

```bash
python assets/_raw/build_from_strips.py cortana --only walk --frames 12
```

`characters.py` already has fallbacks for every animation name above, so you can add them
one at a time and everything keeps working in the meantime.
