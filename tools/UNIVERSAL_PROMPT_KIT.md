# Universal Pixel Character Animation Prompt Kit

Use this kit to invent **any original pixel character** and generate a large, consistent animation library for it.

The kit uses three reusable prompts:

1. **Reference prompt** — creates and locks the character design.
2. **Animation-page prompt** — creates any new 8-frame animation page.
3. **Continuation/repair prompt** — creates frames 9–16 or fixes an incorrect page.

Generate **one page at a time**. Do not ask an image model for the entire pack in one image; the character will become tiny, inconsistent, or repetitive.

---

## 1. Fill out this character card

Replace the bracketed fields. Short answers are fine. If you leave something blank, the reference prompt tells the model to invent a sensible answer.

```text
CHARACTER NAME: [name]
ONE-SENTENCE IDEA: [example: a nervous swamp wizard made from reeds]
BODY TYPE: [humanoid / animal / robot / creature / other]
HEIGHT AND PROPORTIONS: [example: two heads tall, broad body, short legs]
MAIN COLORS: [3–6 colors or hex codes]
FACE AND EXPRESSION: [eyes, mouth, visor, mask, etc.]
CLOTHING OR ARMOR: [details]
DISTINCTIVE FEATURES: [at least 3 features that must never disappear]
MOVING/DRAG ELEMENTS: [tail, cape, antenna, hair, ears, straps, etc.]
MOVEMENT PHYSICS: [heavy, springy, feline, mechanical, floaty, clumsy, etc.]
FOOD OR RECHARGE PROP: [food, battery, magic crystal, fuel, etc.]
UNIQUE NORMAL ACTION: [repair, sword combo, magic trick, pounce, music, etc.]
ALT MODE NAME: [evil / rage / feral / corrupted / crazy / shadow / other]
ALT MODE COLORS: [what changes visibly]
ALT MODE PERSONALITY: [how it behaves]
ALT SIGNATURE ATTACK: [non-gory action]
```

---

# Prompt 1 — Create the locked reference sheet

Paste your completed character card where indicated.

```text
Use case: stylized-concept
Asset type: master pixel-character reference for a production 2D animation pack

Create exactly ONE original character from the character card below.

[PASTE COMPLETED CHARACTER CARD HERE]

If the card leaves a non-critical detail blank, invent a simple, tasteful detail that supports the stated concept. Do not add unrelated props, companions, logos, or story elements.

LAYOUT
- Landscape canvas.
- Upper row: three separated, full-body views at identical scale:
  1. front;
  2. three-quarter;
  3. right-facing side.
- Lower center: one larger front-facing head-and-shoulders close-up.
- Wide empty gutters between every view.
- All full-body views have the same height and share one foot/paw baseline.
- Every limb, accessory, tail, weapon, plume, antenna, or cape is fully visible and uncropped.

DESIGN LOCK
- Give the character a strong, readable silhouette.
- Use a limited palette of approximately 6–10 colors.
- Make the distinctive features unambiguous in every view.
- Keep anatomy, proportions, markings, clothing, equipment, palette, and outline identical across the views.
- The side and three-quarter views must clearly show how all equipment and moving parts attach to the body.
- Do not redesign or simplify the character between views.

PIXEL STYLE
- Detailed, true hand-authored pixel art.
- Crisp hard pixel clusters and a consistent 1-pixel dark outline.
- No anti-aliasing, blur, gradients, soft painting, 3D rendering, vector art, or smooth digital brushwork.
- Design for a game sprite approximately 96–128 pixels tall in its neutral pose.

BACKGROUND
- Flat, perfectly uniform #0a0a12.
- No transparency preview or checkerboard.
- No glow, shadow, floor, platform, border, panel, grid, labels, captions, numbers, letters, logo, or watermark.
- Keep every character pixel visibly lighter than #24242c so the background can be removed cleanly.

OUTPUT RULE
- Output only the reference sheet image.
- No written explanation or text inside the image.
```

Save the result as:

```text
[character_name]_reference.png
```

Attach this reference image to **every later prompt**.

---

# Prompt 2 — Generate a new animation page

Use this for a page whose animations begin at frame 1. Attach the reference sheet and paste one page block from the next section.

```text
Use case: stylized-concept
Asset type: production pixel-art animation atlas for a 2D character

INPUT IMAGE
Image 1 is the exact locked character reference.

CHARACTER LOCK
Study Image 1 closely and match it exactly in every frame: same identity, silhouette, height, proportions, anatomy, face, palette, markings, clothing, armor, equipment, moving parts, outline weight, and pixel-art technique.

Do not redesign, recolor, age, simplify, exaggerate, replace equipment, change handedness, add accessories, remove distinctive features, or change the number of limbs. Between frames, only the pose, expression, explicitly named temporary prop, and explicitly requested alternate-mode effects may change.

PAGE SPECIFICATION
[PASTE ONE PAGE BLOCK HERE]

ATLAS LAYOUT
- Exactly 6 horizontal rows.
- Exactly 8 frames in every row: 48 frames total.
- Frames read left to right.
- Equal-sized cells with very wide empty gutters.
- No character or moving part may touch another cell.
- Character remains the same scale throughout the page.
- Within a grounded row, feet or paws share one stable baseline.
- Every body part, weapon, tail, cape, plume, antenna, effect, and specified prop stays completely inside its cell.

ANIMATION QUALITY
- Every adjacent frame must be a visibly different, meaningful step in the motion.
- No duplicated or near-duplicated filler poses.
- Use anticipation, action, overshoot, follow-through, recovery, and settle where appropriate.
- Keep the distance between neighboring poses even; no unexplained jumps.
- Limbs and loose parts follow curved arcs.
- Secondary parts trail the body by approximately one frame and settle after it.
- Loops must connect from frame 8 back to frame 1 with the same size step used everywhere else.
- Heavy or rigid characters rotate at joints and show weight.
- Soft or animal characters flex through the spine and body mass.

PIXEL STYLE
- Detailed true pixel art.
- Crisp hard pixel clusters and a consistent 1-pixel outline.
- No anti-aliasing, blur, gradients, soft edges, smooth painting, 3D, or vector style.
- Neutral poses approximately 96–128 pixels tall.

BACKGROUND
- Flat, perfectly uniform #0a0a12 only.
- Nothing darker than #24242c on the character.
- No transparency checkerboard, scene, floor, shadow, glow field, panels, cell borders, grid, captions, text, letters, numbers, logo, or watermark.
- Include only temporary props explicitly named in the row descriptions.

OUTPUT RULE
- Output only the atlas image.
- No written labels inside the image.
```

---

# Prompt 3 — Continue frames 9–16

Use this with the reference sheet and the matching frames 1–8 page attached.

```text
Use case: stylized-concept
Asset type: continuation of a production pixel-art animation atlas

INPUT IMAGES
- Image 1: exact locked character reference.
- Image 2: Part A containing frames 1–8 of six animations.

Create Part B containing ONLY frames 9–16 of those same six animations.

CHARACTER AND PAGE LOCK
- Match Image 1 exactly.
- Match Image 2 exactly in scale, palette, rendering, outline, row order, cell spacing, viewpoints, props, effects, and animation intent.
- Do not restart any animation.
- Do not copy frames from Part A.
- Begin each row with the immediate next pose after Part A frame 8.

CONTINUATION SPECIFICATION
[PASTE THE MATCHING PART-B PAGE BLOCK HERE]

LAYOUT
- Exactly 6 rows by 8 columns: 48 frames total.
- Row N continues row N from Image 2.
- Frames read left to right as frames 9–16.
- Equal cells, wide gutters, stable scale and baseline, nothing cropped or overlapping.

MOTION
- Every frame must advance the action with no repeated filler.
- Preserve velocity and direction from Part A.
- Use even increments, curved arcs, follow-through, recovery, and secondary-part drag.
- For a loop, frame 16 must flow naturally back to Part A frame 1.
- For a one-shot, frame 16 must provide a clean final pose or return transition.

STYLE AND BACKGROUND
- Exact detailed pixel style of Images 1 and 2.
- Flat uniform #0a0a12 background.
- No labels, captions, text, numbers, grid, borders, shadow, floor, scenery, logo, or watermark.

OUTPUT RULE
- Output only the Part B atlas image.
```

---

# Page blocks

## Page A — Normal core movement

Paste into Prompt 2.

```text
PAGE NAME: NORMAL CORE

Row 1 — IDLE, 8-frame seamless loop:
Neutral front-facing stance. Show a subtle breathing, servo, hovering, or body-weight cycle appropriate to the character. The main body moves only slightly; the character's drag element performs a delayed sway and settle. Feet stay planted.

Row 2 — WALK, 8-frame seamless loop:
Right-facing walk. Show contact, down, passing, up, reach, then mirrored leg phases. Match the character's stated weight and movement physics. Head remains readable; loose parts trail.

Row 3 — RUN, 8-frame seamless loop:
Right-facing run or gallop. Show contact, compression, push, airborne, then the mirrored half. The silhouette and stride must differ clearly from the walk.

Row 4 — CLIMB CORE, 8-frame seamless loop:
Character faces left and climbs an implied vertical edge on the RIGHT. Alternate high hand/paw grips, releases, reaches, body pulls, and leg steps. Do not draw the wall or ledge.

Row 5 — HAPPY, 8-frame one-shot:
A character-specific positive reaction with anticipation, peak, and settle. It may include a hop, wave, flourish, tail motion, light pulse, or cheer consistent with the design.

Row 6 — THINK/LOOK, 8-frame seamless loop:
Character becomes curious, looks left, up, right, and down, pauses to think, then returns to neutral. Eyes, head, ears, visor, or antenna should lead the motion.
```

---

## Page B1 — Extended normal actions, frames 1–8

Paste into Prompt 2.

```text
PAGE NAME: EXTENDED NORMAL ACTIONS — PART A, FRAMES 1–8 OF 16

Row 1 — SLEEP frames 1–8:
Starts alert, becomes drowsy, lowers the body in several distinct stages, and reaches a half-settled sleeping pose by frame 8. The action must match the character's anatomy; rigid characters fold at joints, soft characters curl or lie down.

Row 2 — EAT OR RECHARGE frames 1–8:
Notices the specified food/recharge prop, approaches or reaches, picks it up or opens the correct body compartment, inspects it, and begins eating/recharging by frame 8. The prop stays consistent.

Row 3 — CLIMB frames 1–8 of a 16-frame seamless cycle:
Faces left at an implied RIGHT edge. Establishes the first grip, hauls upward, steps with the lower limbs, releases the opposite hand/paw, reaches high, and transfers weight. Do not draw the wall.

Row 4 — FALL frames 1–8:
Loses contact, becomes airborne, reacts, begins rotating through several distinct angles, and reaches a clear halfway-tumbled pose. Loose parts trail the rotation.

Row 5 — UNIQUE NORMAL ACTION frames 1–8:
Begin the UNIQUE NORMAL ACTION from the character card. Include anticipation, preparation, and the first half of the action. Every pose must reveal something specific about this character.

Row 6 — CURSOR HANG frames 1–8:
A small, plain, light-gray computer mouse cursor arrow remains fixed at the top center of every cell. The character notices it, jumps, reaches, grabs it with one hand/paw, adds the second grip, becomes fully airborne, and begins swinging right. The cursor stays identical and fixed.
```

---

## Page B2 — Extended normal actions, frames 9–16

Paste into Prompt 3.

```text
PAGE NAME: EXTENDED NORMAL ACTIONS — PART B, FRAMES 9–16 OF 16

Row 1 — SLEEP frames 9–16:
Settles fully asleep, shows a small breathing cycle and one character-specific sleep fidget, then either connects smoothly back to frame 1 or begins a gentle wake-up.

Row 2 — EAT OR RECHARGE frames 9–16:
Completes consumption/recharge, shows a visible decrease or disappearance of the prop, reacts with satisfaction, cleans up or closes the compartment, and returns to a usable neutral pose.

Row 3 — CLIMB frames 9–16:
Completes the alternating second half: opposite high grip, haul, lower-limb step, body rise, first hand/paw release and reach, then reconnects seamlessly to Part A frame 1.

Row 4 — FALL frames 9–16:
Continues the rotation, performs a species/body-appropriate recovery, orients feet/paws downward, braces, and ends in a clear landing crouch or just-before-impact pose.

Row 5 — UNIQUE NORMAL ACTION frames 9–16:
Completes the signature action with its strongest peak, follow-through, recovery, and a final characterful pose.

Row 6 — CURSOR HANG frames 9–16:
Reaches the right swing apex, swings through center to the left apex, briefly slips with one grip, rotates or stretches under the remaining grip, regrabs, and settles into a pose that loops back to Part A.
```

---

## Page C — Ambient fillers and random behavior

Paste into Prompt 2.

```text
PAGE NAME: AMBIENT FILLERS

Row 1 — LOOK AROUND, 8-frame seamless loop:
Eyes/head/visor look left, up-left, up, right, down-right, down, and center. The character's ears, antenna, hair, or other drag element follows late.

Row 2 — CHILL, 8-frame seamless loop:
The character sits, lies, leans, loafs, hovers, or otherwise relaxes in an anatomy-appropriate way. Include a stretch, slow blink, crossed legs, tail curl, vent pulse, or comparable relaxed detail.

Row 3 — SELF-MAINTENANCE, 8-frame action:
A character-appropriate grooming, polishing, tightening, sharpening, cleaning, or equipment-check sequence. Use one small temporary tool only if natural.

Row 4 — RANDOM PERSONALITY FIDGET, 8-frame action:
Invent a harmless, funny behavior tied directly to the character design: playing with its tail, arguing with armor, chasing a loose screw, practicing magic, adjusting clothing, etc.

Row 5 — PEEK/LEAN, 8-frame loop:
Leans around an implied right edge, peeks with one eye, retracts, repeats left, looks down, startles slightly, and returns. Do not draw an edge.

Row 6 — TURN/OBSERVE, 8-frame loop:
Front, three-quarter-right, side-right, look over shoulder, rear three-quarter, side-left, three-quarter-left, front. Preserve all markings and equipment accurately through the rotation.
```

---

## Page D1 — Triple-click alternate mode, frames 1–8

Paste into Prompt 2. Replace the bracketed alt-mode fields using the character card.

```text
PAGE NAME: [ALT MODE NAME] — PART A, FRAMES 1–8 OF 16

ALT-MODE DESIGN LOCK
- The character remains recognizably the same individual.
- Change only the visual features stated in ALT MODE COLORS and behavior.
- Make the mode change immediately readable through eyes/visor, posture, silhouette, drag-element behavior, and a restrained set of energy pixels.
- Do not add horns, wings, limbs, gore, skulls, unrelated armor, or a completely different costume unless explicitly required by the character card.

Row 1 — TRIPLE-CLICK TRANSFORMATION frames 1–8:
Normal character receives three clearly separate mouse-click ripple impacts. Click 1 causes surprise; click 2 begins the color/energy shift; click 3 triggers a full-body reaction. Continue with posture change, drag-element flare, equipment readjustment, and finish frame 8 halfway into the alternate stance.

Row 2 — ALT IDLE frames 1–8 of a 16-frame loop:
A tense, angry, crazy, corrupted, feral, or evil idle appropriate to the card. Use scanning eyes, claw/hand flexes, weapon tension, twitching, shoulder rolls, tail lashes, warning pulses, or other character-specific details.

Row 3 — HOSTILE MOVEMENT frames 1–8:
Stalk, prowl, angry march, chase, low dash, or aggressive hover. Establish several movement phases and reach a strong halfway action pose.

Row 4 — ALT SIGNATURE ATTACK frames 1–8:
Begin the ALT SIGNATURE ATTACK from the card. It must be targetless and non-gory. Include anticipation, charge/windup, and the first impact/action phase.

Row 5 — ALT CURSOR INTERACTION frames 1–8:
A fixed light-gray cursor sits above. The character notices it, jumps or reaches, grabs it, hangs, and begins sabotaging, biting, shaking, shield-bashing, twisting, or dragging it in a character-appropriate way.

Row 6 — ALT TAUNT/CRAZY frames 1–8:
Build a distinctive alternate-mode taunt: unsettling head tilt, weapon clang, silent laugh, hiss, accusatory point, chest pound, tail coil, or similar behavior.
```

---

## Page D2 — Triple-click alternate mode, frames 9–16

Paste into Prompt 3.

```text
PAGE NAME: [ALT MODE NAME] — PART B, FRAMES 9–16 OF 16

Row 1 — TRANSFORMATION/RETURN frames 9–16:
Completes the full alternate stance, holds at peak intensity, then provides a clean reverse transition back toward the normal palette and neutral stance by frame 16. This allows an exit animation.

Row 2 — ALT IDLE frames 9–16:
Continues with new fidgets and secondary motion, then reconnects smoothly to Part A frame 1 without copying poses.

Row 3 — HOSTILE MOVEMENT frames 9–16:
Completes the movement, changes direction or performs a second burst, brakes or recovers, scans, and reconnects to Part A.

Row 4 — ALT SIGNATURE ATTACK frames 9–16:
Reaches the strongest action pose, follows through, handles recoil or recovery, resets equipment/body shape, and returns to a usable alternate-mode guard.

Row 5 — ALT CURSOR INTERACTION frames 9–16:
Drags or swings on the fixed cursor, reaches opposite apex, briefly loses one grip, rotates, regrabs, and returns the cursor overhead in a looping hang pose.

Row 6 — ALT TAUNT/CRAZY frames 9–16:
Escalates the taunt, reaches one memorable extreme pose, freezes briefly, settles, and returns to the alternate idle stance.
```

---

## Page E — Additional alternate-mode behaviors

Paste into Prompt 2.

```text
PAGE NAME: [ALT MODE NAME] — EXTRA BEHAVIORS

Row 1 — ALT CLIMB, 8-frame seamless loop:
An aggressive climb on an implied RIGHT edge, alternating high grips and lower-limb pushes. Make it faster or more forceful than the normal climb. Do not draw a wall.

Row 2 — ALT FALL/RECOVERY, 8-frame one-shot:
A reckless or intentional leap, several distinct rotation angles, character-specific righting motion, and a forceful landing that immediately returns to a hostile stance.

Row 3 — TANTRUM/OVERLOAD/ZOOMIES, 8-frame action:
Character-specific burst of uncontrolled energy: stamping, vibrating, armor sparks, fur shake, magical overload, frantic loop, or similar non-destructive behavior.

Row 4 — CURSOR RIDE, 8-frame action:
The fixed light-gray cursor becomes something the character rides, balances on, hangs from, or uses like a sled/board. Include instability and recovery.

Row 5 — ALT RANDOM MISCHIEF, 8-frame action:
A small character-specific misbehavior involving one simple prop: steals a chip/button, hides an item, moves something, tampers with equipment, or plays an aggressive prank.

Row 6 — FALSE CALM/AMBUSH, 8-frame action:
Character pretends to be normal, cute, honorable, powered down, or harmless; one alternate-mode feature flashes; it performs a sudden targetless lunge/pounce/dash; then immediately pretends innocence again.
```

---

# Repair prompt — when a page has the wrong count or layout

Attach the incorrect page and paste this prompt.

```text
Use case: precise-object-edit
Asset type: corrected production pixel-art animation atlas

Image 1 is the exact edit target.

Correct ONLY the count and layout. The finished atlas must contain exactly 6 horizontal rows and exactly 8 isolated frames in every row: 48 frames total.

Preserve every existing valid frame in its exact row order and visual design. If a row has fewer than 8 frames, add only the missing number of unique in-between poses at the right side of that row. Each new pose must bridge smoothly from the preceding pose into the intended next pose or loop start.

Redistribute every row evenly into 8 equal cells with wide empty gutters. Maintain the exact character identity, scale, palette, proportions, markings, equipment, pixel style, animation direction, and flat #0a0a12 background.

Do not add rows, labels, text, numbers, grid lines, borders, scenery, floor, shadows, duplicate characters, extra limbs, cropped parts, logo, or watermark.

Output only the corrected atlas.
```

---

# Consistency repair prompt

Use when the frame count is correct but the character drifts or changes design.

```text
Use case: identity-preserve
Asset type: corrected pixel animation atlas

Inputs:
- Image 1: exact locked character reference.
- Image 2: animation atlas to correct.

Change only inconsistent character-design details in Image 2. Make every frame match Image 1 exactly in proportions, face, palette, markings, clothing, equipment, handedness, distinctive features, outline, and pixel-art style.

Preserve Image 2's poses, animation timing, frame order, row order, scale, cell spacing, props, effects, and flat #0a0a12 background. Do not replace poses or redesign the action.

Keep exactly the same number of rows and frames. No text, labels, grid, borders, floor, shadows, scenery, logo, or watermark.
```

---

# Recommended generation order

1. Reference sheet.
2. Page A — normal core.
3. Page B1 — extended actions frames 1–8.
4. Page B2 — extended actions frames 9–16.
5. Page C — ambient fillers.
6. Page D1 — alternate mode frames 1–8.
7. Page D2 — alternate mode frames 9–16.
8. Page E — extra alternate behaviors.

This produces:

- 6 core animations × 8 frames = 48 frames.
- 6 extended animations × 16 frames = 96 frames.
- 6 ambient animations × 8 frames = 48 frames.
- 6 primary alternate-mode animations × 16 frames = 96 frames.
- 6 extra alternate-mode animations × 8 frames = 48 frames.
- **336 animation frames per character**, before optional repairs or variants.

---

# Final practical notes

- Always attach the reference sheet.
- For Part B, attach both the reference and Part A.
- Generate one page per request.
- Reject a page with the wrong row/frame count; repair it before continuing.
- Use the flat `#0a0a12` background for reliable sprite extraction.
- When extracting, keep fixed cell sizes and bottom-align grounded frames to prevent jitter.
- In a game engine, use nearest-neighbor/point texture filtering.
- A useful triple-click rule is 3 clicks within 450 ms, followed by 18–30 seconds of alternate-mode playlist behavior.
- Do not treat generated atlas rows as perfectly production-safe until frame counts, alpha extraction, cell alignment, and loop transitions are checked.
