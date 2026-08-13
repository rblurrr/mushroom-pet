# Three new characters — prompt book

`SPRITE_PROMPTS.md` is the generic animation library: it assumes you already have a
character and gives you per-animation prompts for it. This file is the other half — it
**invents three new characters** and gives each one its own reference sheet plus five
animation prompts written for *its* body, weight and moving parts.

The three are deliberately nothing like each other, and nothing like the two you have:

| Pack   | Who                                                         | Voice                              |
|--------|-------------------------------------------------------------|------------------------------------|
| `bolt` | a dented little scrap robot, one amber lens for a face       | deadpan system logs                |
| `pip`  | a very small knight with a very large sword                  | grandiose, sincere, medieval       |
| `nyx`  | a charcoal cat with a violet rim-light and moon-green eyes   | haughty, hunting-brained, brief    |

Their speech is already written and wired in — see **Voices** at the bottom. Every
character now talks differently the moment you switch to it; nothing to do there.

---

## Why these five animations

Five strips per character, and this particular five, because of how `characters.py`
falls back. These five cover far more than five poses:

| Strip    | Frames | Also covers, through the fallback chain                                    |
|----------|--------|----------------------------------------------------------------------------|
| `idle`   | 10     | `idle_alt`, `look`, `sit`, `lie`, `sleep`, `think`, `peek`, `lean`, `turn`  |
| `walk`   | 12     | wandering, ledge patrol, `cut_approach`                                     |
| `run`    | 8      | come-here, chase, `dash`, `slide`, parkour combos                           |
| `climb`  | 10     | `hang`, **`grab`**, **`swing`**, `wall_push`, `evil_climb` — all cursor play |
| `happy`  | 8      | `wave`, `love`, `dance`, `cheer`, `clap`, `applaud`, `taunt`, click reactions |

`climb` and `happy` are the two that earn their place twice over: without `climb` the
pet can't grab your cursor properly, and without `happy` a click on it does nothing
visible. Do those two before you do `run` if you're short on patience.

Anything beyond these five: the prompts in `SPRITE_PROMPTS.md` are character-agnostic
and work fine with any of the three references below.

---

## What makes them *smooth*

Frame count is most of it, but not all of it. Five rules do the rest, and they're baked
into the setup prompt in step 1 so you don't have to repeat them:

1. **Even spacing.** The step between every pair of neighbouring frames is the same
   size. One frame that jumps twice as far as its neighbours is the single most common
   reason a generated cycle looks like it stutters.
2. **Arcs, not lines.** Hands, heads, tails and feet travel along curves. Straight-line
   motion reads as mechanical (which is right for `bolt` and wrong for `nyx`).
3. **Drag and settle.** The floppy parts — Bolt's antenna, Pip's plume, Nyx's tail —
   lag one frame behind the body when it moves and keep moving for one frame after it
   stops. This is what separates "animated" from "posed".
4. **Closed loops.** The last frame leads into the first with the same size step as
   every other pair, or the loop clicks once per cycle forever.
5. **Nothing changes but the pose.** Same height, same proportions, same palette, feet
   on the same line. Any drift in size or detail reads as flicker at 12fps.

**Frame counts and image size fight each other.** Twelve frames across one 1536px image
is 128px per frame and the art gets mushy. So for the 10- and 12-frame cycles, ask for
the cycle in **halves** — the prompts below are numbered so you can say *"same rules,
now only frames 7–12 of that cycle"* — save them as `walk_a.png` and `walk_b.png`, and
stitch them with:

```bash
python assets/_raw/join_strips.py walk_a.png walk_b.png -o nyx/strips/walk.png
```

`join_strips.py` re-lays every frame with identical gutters, which is what the builder
needs to split them cleanly. Half-strips are the difference between a 12-frame walk that
looks smooth and a 12-frame walk that looks like a flipbook drawn on a bus.

---

## Step 1 — paste this once per session

With the character's reference image attached (from step 2). It sets the rules so every
animation prompt afterwards can stay short.

> Here is the exact character I'm making a sprite sheet for. Study it carefully.
>
> For every image I ask for from now on, these rules always apply:
>
> **CHARACTER** — Match this reference exactly: same palette, same proportions, same
> silhouette, same face, same costume details, same outline weight, same art style. Do
> not redesign, restyle, recolour, age, or "improve" the character. Do not add new
> accessories. Between frames the **only** thing that changes is the pose.
>
> **LAYOUT** — All frames in ONE horizontal row, left to right, evenly spaced. Leave a
> wide band of empty background between each pair of frames so they never touch or
> overlap. In every frame the character is horizontally centred in its own cell, is
> **exactly the same height**, and its feet rest on the **same horizontal line**. Do not
> zoom in or out between frames.
>
> **MOTION QUALITY** — This is animation, not a set of poses. The change from each frame
> to the next must be the **same size step** — no frame may jump further than its
> neighbours. Limbs, heads and tails move along **curved arcs**, never straight lines.
> Loose parts trail one frame behind the body and settle one frame after it stops. If the
> animation is a cycle, the last frame must lead back into the first with that same even
> step, seamlessly.
>
> **BACKGROUND** — Flat solid `#0a0a12`, and absolutely nothing else on it. No glow, no
> drop shadow, no ground shadow, no floor, no platform, no panel borders, no grid lines,
> no captions, no numbers, no labels, no watermark. **No text of any kind anywhere in the
> image.**
>
> **CONTRAST** — No part of the character may be as dark as the background. Even its
> darkest outline must be clearly lighter than `#24242c`, or it will be cut away when the
> sprite is extracted.
>
> **STYLE** — True pixel art. Hard 1-pixel dark outline. No anti-aliasing, no gradients,
> no blur, no soft edges. Character about 260 pixels tall.
>
> **SIZE** — Landscape, 1536 × 1024.
>
> Reply "ready" and then wait for my first animation.

If quality slips later in a session, re-attach the reference and append this to the
offending prompt:

> Reminder: match the attached reference exactly, flat #0a0a12 background, no text or
> labels anywhere, wide gaps between frames, every frame the same height with feet on the
> same line, even spacing between frames.

---

# 1. `bolt` — the scrap robot

**Who he is.** Nine kilos of salvaged plating that was built to repair things and now
has nothing to repair. Rigid, deliberate, weirdly sincere. He does not squash or stretch
— he is metal — so all his life comes from **timing and rotation**: joints pivot, the
chassis stays a solid shape, and his one bent antenna whips around a frame late.

**Palette.** Gunmetal plating `#6f7684`, lighter worn edges `#9aa3b2`, rust-orange
patches `#b4643a`, warm amber lens and antenna bead `#ffb02e`, deep steel shadow
`#3a4050` (never darker than that — see the contrast rule).

### Reference sheet — run this first

```
A pixel-art character reference sheet of ONE original character, three full-body views
in a row plus one large head close-up centred below them, all on a flat solid #0a0a12
background with nothing else on it.

THE CHARACTER: a small chibi scrap robot, two heads tall, boxy and stout. His body is a
riveted gunmetal box with worn lighter edges and two rust-orange patches, a small hinged
hatch on the chest. His head is a rounded steel bucket with ONE large round amber lens
filling most of the face like a porthole, with a fine hairline chip in the glass at the
lower left. A single thin antenna rises from the top of his head, bent forward at the
tip, with a small glowing amber bead on the end. Stubby segmented arms end in
three-fingered claws. Short thick legs end in wide flat boot-feet. A small vent grille
sits on his upper back.

THE VIEWS, left to right: 1) front view standing straight, arms relaxed at his sides;
2) three-quarter view; 3) side profile. Below them, one head-and-shoulders close-up,
front on, twice the size of the others.

All three full-body views are exactly the same height with their feet on the same
horizontal line.

STYLE: true pixel art, hard 1-pixel dark outline, no anti-aliasing, no gradients, no
blur. Colours: gunmetal #6f7684 plating, worn edges #9aa3b2, rust #b4643a, amber lens
#ffb02e, steel shadow #3a4050. Nothing darker than #24242c anywhere on the character.

No text, no labels, no numbers, no watermark, no borders, no ground shadow, no glow,
nothing on the background. Landscape 1536 x 1024.
```

Save it as `assets/_raw/bolt_reference.png` and attach it to everything below.

### `idle` — 10 frames

```
10 frames of ONE seamless IDLE loop, facing the viewer, standing still.

1   rest pose: arms at his sides, lens level
2-3 the chassis settles down about two pixels, servos easing off
4   lowest point, held
5   a small puff of steam escapes the back vent, body rises one pixel
6-7 rising back up, the antenna still lagging behind, bent backward
8   at rest height again, antenna overshooting forward
9   antenna swings back past centre
10  antenna settles, leading straight back into frame 1

The body motion is TINY — two or three pixels of vertical travel, no squash, the box
never deforms. The antenna is the only part with real movement: it always trails the
body by one frame and takes two frames to settle. The amber lens stays the same
brightness throughout. The feet never move.
```

### `walk` — 12 frames

```
12 frames of ONE seamless side-view WALK CYCLE, facing right. He is heavy and
mechanical: the chassis stays perfectly rigid, all the motion is in the hip and knee
joints, and he lands flat-footed.

1  contact: right foot forward and flat, left foot back on its toe, arms opposite
2  down: weight drops onto the right leg, body at its lowest, both knees bent
3  passing low: left leg swinging forward under the body
4  passing: left leg directly under the hips, body starting to rise
5  up: pushing off the left toe, body at its highest, a puff from the back vent
6  reach: right leg extends forward, arms at full opposite swing
7  contact mirrored: left foot forward and flat, right foot back on its toe
8  down mirrored: weight drops onto the left leg, body lowest again
9  passing low mirrored
10 passing mirrored: right leg under the hips, body rising
11 up mirrored: pushing off the right toe, body highest
12 reach mirrored: left leg extends forward, landing back into frame 1

The body rises and falls by the same amount each step. The antenna sways in a lazy S
one frame behind the body's bob. The arms swing from the shoulder joint only — the
elbows barely bend. Frame 12 leads straight into frame 1 with no jump.
```

### `run` — 8 frames

```
8 frames of ONE seamless side-view RUN CYCLE, facing right. Faster and lower than his
walk, chassis pitched forward, arms pumping hard, both feet leaving the ground.

1 right foot contact, body low and leaning forward, left arm forward
2 deepest compression on the right leg, sparks at the foot
3 push off, body rising, left leg swinging through
4 airborne, both feet off the ground, legs crossing, steam trailing from the vent
5 left foot contact, body low, right arm forward
6 deepest compression on the left leg
7 push off, body rising, right leg swinging through
8 airborne again, leading straight back into frame 1

The antenna is swept fully backward and whipping throughout. Still no squash — he is a
rigid box travelling on a bouncing arc. Frame 8 leads back into frame 1.
```

### `climb` — 10 frames

```
10 frames of ONE seamless CLIMBING CYCLE. He climbs UP the right-hand edge of a vertical
surface: he faces left and grips a plain vertical ledge running down the RIGHT side of
every frame. His claws lock onto the edge like clamps.

1  right claw high and clamped, left claw low, right knee raised
2  hauling up on the right arm, body rising
3  body risen, left claw releasing with a small spark
4  left claw reaching straight up past his head
5  left claw clamps high, weight shifting across
6  hauling up on the left arm, left knee raised (mirror of frame 1)
7  body rising on the left arm
8  right claw releasing
9  right claw reaching up past his head
10 right claw clamps high, leading straight back into frame 1

CRITICAL: the whole robot — head, both arms, both legs, antenna — is completely inside
its frame in all 10 frames, never cropped by the frame edge. The climb is even and
unhurried, the same distance gained each frame. The antenna bounces once per grip.
Frame 10 leads back into frame 1.
```

### `happy` — 8 frames

```
8 frames of Bolt DELIGHTED, facing the viewer — the closest a rigid robot gets to a
cheer. Not a loop; one continuous burst.

1 rest pose, lens level
2 both arms snapping up and outward, chassis lifting slightly
3 arms straight overhead, body up on the balls of his feet, antenna whipped backward
4 a small hop: both feet just off the ground, arms wide, steam bursting from the vent
5 the peak of the hop, arms at full spread, antenna trailing straight down
6 landing, knees bent, arms coming down, antenna overshooting forward
7 upright again, one claw raised in a small stiff wave, antenna settling
8 back near the rest pose, lens tilted a fraction, claw still half-raised

The amber lens brightens over frames 3-5 and returns to normal by frame 8. Still no
squash or stretch — the joy is all in the timing and the antenna.
```

---

# 2. `pip` — the very small knight

**Who he is.** Two heads tall, in dented pewter plate, carrying a sword nearly as long
as he is. Everything he does is **heavy and committed**: slow rise, fast drop, and a
half-frame of recovery afterwards. His plume and cape are the drag elements; the sword's
weight pulls his whole body around.

**Palette.** Pewter plate `#8b93a1`, polished highlights `#c3cad6`, brass trim `#c9922f`,
crimson plume and tabard `#c0392b`, deep crimson shadow `#7a2320`, oak shield `#8a5a34`,
steel shadow `#454b5c`.

### Reference sheet — run this first

```
A pixel-art character reference sheet of ONE original character, three full-body views
in a row plus one large head close-up centred below them, all on a flat solid #0a0a12
background with nothing else on it.

THE CHARACTER: a tiny chibi knight, two heads tall, in full dented pewter plate armour
with brass trim. His helmet is an oversized bucket helm with a horizontal T-visor slit,
a faint warm white glow showing in the dark of the slit where his eyes would be, and a
tall crimson plume arching backward from the crest. A short crimson tabard hangs to his
knees over the armour. A small round oak shield with a brass boss is strapped to his
left arm. In his right hand he carries a plain steel longsword nearly as tall as he is,
point resting on the ground. Stubby armoured boots, gauntlets too big for him.

THE VIEWS, left to right: 1) front view standing at attention, sword point down in front
of him; 2) three-quarter view; 3) side profile. Below them, one head-and-shoulders
close-up of the helmet, front on, twice the size of the others.

All three full-body views are exactly the same height with their feet on the same
horizontal line.

STYLE: true pixel art, hard 1-pixel dark outline, no anti-aliasing, no gradients, no
blur. Colours: pewter #8b93a1, highlights #c3cad6, brass #c9922f, crimson plume and
tabard #c0392b, oak shield #8a5a34, steel shadow #454b5c. Nothing darker than #24242c
anywhere on the character — the visor slit is dark grey, not black.

No text, no labels, no numbers, no watermark, no borders, no ground shadow, no glow,
nothing on the background. Landscape 1536 x 1024.
```

Save as `assets/_raw/pip_reference.png`.

### `idle` — 10 frames

```
10 frames of ONE seamless IDLE loop: standing vigil, facing the viewer, sword point
resting on the ground in front of him, both gauntlets on the pommel.

1   rest pose, helm level, shoulders square
2-3 a slow breath in: the breastplate rises two pixels, the helm lifts a fraction
4   top of the breath, held
5-6 breathing out, shoulders settling, the helm dipping slightly
7   lowest point of the breath
8   the crimson plume, which has been trailing the head all along, sways to one side
9   the plume swings back through centre
10  the plume settles, leading straight back into frame 1

The armour itself barely moves — three pixels of travel at most, and it never deforms.
The plume and the hem of the tabard are the only parts with real movement, and both lag
one frame behind the body. The sword never leaves the ground. The feet never move.
```

### `walk` — 12 frames

```
12 frames of ONE seamless side-view WALK CYCLE, facing right. A small knight under real
weight: he plants each boot deliberately, the sword rests on his right shoulder, and the
armour stays perfectly rigid.

1  contact: right boot forward heel first, left boot back on its toe
2  down: weight drops onto the right leg, body at its lowest, the sword dipping
3  passing low: left leg swinging through under the body
4  passing: left boot directly under the hips, body rising
5  up: pushing off the left toe, body at its highest, sword at its highest
6  reach: right leg extends forward, shield arm swinging back
7  contact mirrored: left boot forward heel first, right boot back on its toe
8  down mirrored: weight drops onto the left leg, body lowest again
9  passing low mirrored
10 passing mirrored: right boot under the hips, body rising
11 up mirrored: pushing off the right toe, body highest
12 reach mirrored: left leg extends forward, landing back into frame 1

The plume bobs one frame behind the head and the tabard hem swings one frame behind the
hips. The sword on his shoulder rocks with the body but always stays touching it. Same
size step every frame. Frame 12 leads straight into frame 1.
```

### `run` — 8 frames

```
8 frames of ONE seamless side-view RUN CYCLE, facing right — a charge. He leans well
forward, sword held low and back in his right hand, shield tucked in front of his chest,
both boots leaving the ground.

1 right boot contact, body low and pitched forward, shield leading
2 deepest compression on the right leg
3 push off, body rising, left leg driving through, sword swinging forward
4 airborne, both boots off the ground, legs crossing, plume streaming straight back
5 left boot contact, body low, sword swinging back
6 deepest compression on the left leg
7 push off, body rising, right leg driving through
8 airborne again, leading straight back into frame 1

The plume and tabard stream backward the whole way and never go slack. The sword swings
in a shallow arc, one frame behind the body. Frame 8 leads back into frame 1.
```

### `climb` — 10 frames

```
10 frames of ONE seamless CLIMBING CYCLE. He climbs UP the right-hand edge of a vertical
surface: he faces left and grips a plain vertical ledge running down the RIGHT side of
every frame. The sword is sheathed across his back for the climb; the shield stays on
his left arm.

1  right gauntlet high on the edge, left gauntlet low, right knee raised
2  hauling up on the right arm, boots scraping for purchase
3  body risen, left gauntlet releasing
4  left gauntlet reaching up past the helm
5  left gauntlet grips high, weight transferring across
6  hauling up on the left arm, left knee raised (mirror of frame 1)
7  body rising on the left arm
8  right gauntlet releasing
9  right gauntlet reaching up past the helm
10 right gauntlet grips high, leading straight back into frame 1

CRITICAL: the whole knight — helm, plume, both arms, both boots, the sheathed sword — is
completely inside its frame in all 10 frames, never cropped by the frame edge. This is
hard work in armour: the pace is even and heavy, the same distance gained each frame,
the plume swinging down and out on every pull. Frame 10 leads back into frame 1.
```

### `happy` — 8 frames

```
8 frames of Pip TRIUMPHANT, facing the viewer. Not a loop; one continuous flourish.

1 standing at attention, sword point down
2 the sword sweeping up and out to his right, body starting to turn into it
3 sword raised high overhead in both gauntlets, body leaning back, plume trailing forward
4 a small jump: both boots off the ground, sword at the very top, shield arm flung wide
5 the peak, body stretched tall, plume streaming straight down behind him
6 landing, knees bent, sword swinging down across his body, plume overshooting forward
7 upright, sword brought to his visor in a formal salute, plume settling
8 holding the salute, helm tipped a fraction, plume at rest

The sword travels on one continuous curved arc from frame 2 to frame 6 — never a
straight line, never a jump between frames. The plume is always one frame behind the
helm.
```

---

# 3. `nyx` — the cat

**Who she is.** A charcoal cat with a violet rim-light and a kinked tail. She is the
opposite of the other two: **no rigid parts at all**. Her spine curves into every pose,
her ears lead her head, and her tail is a long trailing chain that is never straight and
never still.

**A note on the fur.** The sprite extractor throws away anything as dark as the
background, so a truly black cat would come out full of holes. She is charcoal-violet
`#3a3450` with a bright violet rim-light — which is why she reads so well against a dark
desktop.

**Palette.** Charcoal-violet fur `#3a3450`, lighter fur planes `#544c6e`, violet rim-light
`#8b6cff`, moon-green eyes `#7dfab2`, white chest tuft and toe-tips `#f2f0ea`, pink nose
`#d98f9c`. Nothing darker than `#24242c`.

### Reference sheet — run this first

```
A pixel-art character reference sheet of ONE original character, three full-body views
in a row plus one large head close-up centred below them, all on a flat solid #0a0a12
background with nothing else on it.

THE CHARACTER: a small chibi cat, chunky and low to the ground, with a large head and
short legs. Her fur is charcoal-violet, never true black, with lighter violet-grey planes
on top and a bright violet rim-light along her back, ears and tail. She has very large
round moon-green eyes, a small pink nose, two tiny fangs showing, a white tuft on her
chest and white tips on all four paws. A distinct nick is missing from her left ear. Her
tail is long with a kink two-thirds of the way along and a white tip.

THE VIEWS, left to right: 1) front view sitting upright, tail curled around her paws;
2) three-quarter view standing on all fours; 3) side profile standing on all fours.
Below them, one head-and-shoulders close-up, front on, twice the size of the others.

The two standing views are exactly the same height with their paws on the same
horizontal line.

STYLE: true pixel art, hard 1-pixel dark outline, no anti-aliasing, no gradients, no
blur. Colours: fur #3a3450, lighter fur #544c6e, violet rim-light #8b6cff, eyes #7dfab2,
white tuft and toes #f2f0ea, nose #d98f9c. Nothing darker than #24242c anywhere on the
character, including the outline and the inside of the ears.

No text, no labels, no numbers, no watermark, no borders, no ground shadow, no glow,
nothing on the background. Landscape 1536 x 1024.
```

Save as `assets/_raw/nyx_reference.png`.

### `idle` — 10 frames

```
10 frames of ONE seamless IDLE loop: sitting upright, facing the viewer, tail curled
around her front paws.

1   rest pose, ears forward, eyes open, tail tip resting
2-3 a slow breath in: the chest swells, the head lifts a fraction
4   top of the breath, held
5-6 breathing out, the head settling, shoulders dropping
7   lowest point of the breath
8   the tail tip flicks up and to the left, one lazy curl
9   the tail tip sweeps back down through centre
10  the tail tip settles, leading straight back into frame 1

The body motion is tiny and soft — she is fur, so the outline of her sides changes shape
slightly as she breathes, unlike a rigid character. The ears twitch once, on frame 5
only, one pixel. The tail is the only part that really moves and it moves on a curve.
Frame 10 leads straight back into frame 1.
```

### `walk` — 12 frames

```
12 frames of ONE seamless side-view four-legged WALK CYCLE, facing right — a relaxed,
confident cat trot with the diagonal legs paired.

1  contact: front-right and back-left paws planted, front-left and back-right lifted
2  down: weight settling, the body at its lowest, the spine curving down
3  passing low: the lifted paws swinging forward under the belly
4  passing: lifted paws directly under the body, spine straightening, body rising
5  up: pushing off, body at its highest, all four paws briefly close together
6  reach: front-left and back-right stretching forward to land
7  contact mirrored: front-left and back-right planted, the other pair lifted
8  down mirrored: weight settling, body lowest again
9  passing low mirrored
10 passing mirrored: lifted paws under the body, body rising
11 up mirrored: pushing off, body highest
12 reach mirrored: front-right and back-left stretching forward, into frame 1

Her spine flexes through the whole cycle — it is never a straight rigid line. The head
stays level while the body rises and falls beneath it. The tail is held up in a relaxed
question-mark curve and sways one frame behind the hips, the tip curling last. The
nicked ear stays forward. Frame 12 leads straight into frame 1.
```

### `run` — 8 frames

```
8 frames of ONE seamless side-view four-legged GALLOP, facing right — a cat at full
speed, the body stretching and gathering like a spring.

1 gathered: all four paws bunched under her, spine arched up, body at its shortest
2 launch: back legs driving, body starting to extend, front paws reaching out
3 extended flight: body stretched long and low, spine curved down, all four paws off
  the ground, front paws forward and back paws trailing
4 front paws touching down, spine flattening
5 the body rolling over the front paws, back legs swinging forward under the belly
6 back paws planting ahead of where the front paws were, spine arching up
7 push off from the back paws, body gathering again
8 airborne and gathered, paws tucked under her, leading straight back into frame 1

The whole body squashes and stretches — long in frames 3 and 4, short in frames 1 and 8.
Ears are flat back and the tail streams out straight behind her with only a slight wave.
Frame 8 leads back into frame 1.
```

### `climb` — 10 frames

```
10 frames of ONE seamless CLIMBING CYCLE. She climbs UP the right-hand edge of a vertical
surface, claws out: she faces left and hooks a plain vertical ledge running down the
RIGHT side of every frame, body flat against it.

1  front-right paw hooked high, front-left low, back-right paw braced, haunches gathered
2  hauling up on the front-right, haunches driving, spine compressing
3  body risen, front-left paw releasing
4  front-left paw reaching up past her head, claws spread
5  front-left paw hooks high, weight transferring across, back paws stepping up
6  hauling up on the front-left, haunches gathered (mirror of frame 1)
7  body rising on the front-left
8  front-right paw releasing
9  front-right paw reaching up past her head
10 front-right paw hooks high, leading straight back into frame 1

CRITICAL: the whole cat — head, all four paws, the full tail — is completely inside its
frame in all 10 frames, never cropped by the frame edge. The climb is quick and light,
the same distance gained each frame. The tail lashes in a slow S the whole way up,
counterweighting each pull, one frame behind the body. Frame 10 leads back into frame 1.
```

### `happy` — 8 frames

```
8 frames of Nyx PLEASED, facing the viewer — smug rather than excitable. Not a loop;
one continuous move.

1 sitting upright, tail curled around her paws
2 rising onto her front paws, chest lifting, eyes narrowing happily
3 a big stretch: front paws pushed forward, back arched down, haunches high, tail up
4 up on all fours, front-right paw lifted mid-air in a slow deliberate wave
5 the paw at the top of its arc, head tilted, eyes closed and content
6 the paw coming down on a curve, body settling back
7 sitting again, tail sweeping around the front of her paws
8 settled, tail tip curling over her toes, one eye open looking straight at the viewer

Her spine curves through every frame — nothing about her is ever rigid or straight. The
tail leads into each pose and settles one frame after the body does.
```

---

## Building a pack from the images

```bash
# 1. scaffold the empty pack (once per character)
python assets/_raw/new_pack.py nyx

# 2. save your strips as assets/_raw/nyx/strips/{idle,walk,run,climb,happy}.png
#    (if you generated a cycle in halves, stitch first:)
python assets/_raw/join_strips.py walk_a.png walk_b.png -o nyx/strips/walk.png

# 3. check the frame counts before writing anything
python assets/_raw/build_from_strips.py nyx --dry-run

# 4. write them in
python assets/_raw/build_from_strips.py nyx

# 5. copy a good idle frame to assets/characters/nyx/icon.png  (tray icon)
# 6. restart the pet -- the new character appears under the right-click menu
```

Repeat for `bolt` and `pip`. The scaffolded pack is invisible to the pet until it has
real animations in it, so a half-finished character can sit on disk harmlessly.

**Nyx is a quadruped**, so height-matching makes her look oversized next to the others.
Build her a bit shorter:

```bash
python assets/_raw/build_from_strips.py nyx --height 78
```

### If it goes wrong

| Symptom | Fix |
|---|---|
| `only found 1 frame` | The frames are touching. Regenerate with *"leave a much wider empty gap between each frame"*, or force it: `--only walk --frames 12` |
| The sprite has holes in it | Something on the character is as dark as the background. Regenerate with the contrast rule; charcoal, not black |
| It jitters or bobs between frames | The frames aren't the same height. Regenerate with *"every frame exactly the same height, feet on the same line, do not zoom between frames"* |
| The loop clicks once a cycle | The last frame doesn't lead into the first. Ask for *"frame N must lead back into frame 1 with the same size step as every other pair"* |
| Too fast or too slow in the app | Edit `fps` for that animation in `assets/characters/<pack>/manifest.json` — a rebuild keeps your hand-tuned value |
| Frames look cramped and mushy | Too many frames in one image. Generate it in halves and use `join_strips.py` |

---

## Voices

Speech now lives in `mushroom/voices.py`, one pool per character, and the pet picks from
the pool belonging to whichever character is loaded. All five voices are already written:
the mushroom keeps its damp contentment, Cortana finally stops talking about spores, and
Bolt, Pip and Nyx each have their own ~150 lines across every moment the engine can
produce — clicks, drags, climbs, cursor grabs, tripping over nothing, having their window
closed under them.

To adjust one, edit its dict in `voices.py`:

```python
NYX = {
    "idle":  ["i knocked something off earlier. i regret nothing", ...],
    "click": ["mrrp", "what", "hm", ...],
    ...
}
```

The keys are listed at the top of that file with the moment each one fires. Anything you
leave out falls back to the mushroom's lines, so a new character can start with `idle`
and `click` and grow from there.
