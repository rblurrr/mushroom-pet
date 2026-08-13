"""Cut sprites out of the animation pack's *source atlases*.

The pack ships pre-cut frames under `frames/<anim>/`, but its cell grid is offset from
where the sprites actually sit: most of those PNGs contain the right-hand half of one
pose and the left-hand half of the next. Importing them gives you animations that are
half of one drawing and half of another, which is what made the characters read as
glitchy and missing pixels -- no amount of cleaning fixes a frame that is genuinely two
half-poses.

So this ignores the pre-cut frames and goes back to `transparent_atlases/`, which are
the real, whole images.

Splitting them is the whole job. Neither an even grid nor gap-detection works alone:

  * an even grid is wrong because the sprites aren't evenly spaced,
  * gap-detection is wrong because neighbouring sprites touch (giving 6 cells where
    there are 8) while a sprite with a raised limb splits into several blobs (giving 12).

The manifest states the true row and column counts, so instead of guessing how many
cells there are, this looks for *where* they divide: near each evenly-spaced boundary it
searches a window for the emptiest column, and cuts there. That snaps to the real gutter
while never producing the wrong number of frames.
"""
from __future__ import annotations
import numpy as np
from PIL import Image

ALPHA_T = 16
# How far either side of the even-grid guess to hunt for a gutter, as a fraction of the
# cell pitch. No single value wins: a narrow window keeps evenly-spaced rows honest, a
# wide one rescues rows where the sprites crowd together. Each row is cut with all of
# them and keeps whichever produced the most usable frames.
SEARCHES = (0.22, 0.28, 0.34, 0.42)
SEARCH = 0.34          # used when a caller wants a single deterministic cut
GOOD_FRAC = 0.62       # a cell smaller than this share of its row's median is a scrap


def ink(mask, axis):
    """Ink profile along an axis: 0 -> one value per column, 1 -> one per row."""
    return mask.sum(axis=axis).astype(np.float64)


def split(profile, want, search=None):
    """Cut a profile into `want` bands, snapping each boundary to a local minimum.

    Returns want+1 boundary positions. The count is guaranteed, which is the point:
    the atlas is known to be an 8-wide grid, so the question is never "how many
    sprites are here" but "where exactly does each one end".
    """
    search = SEARCH if search is None else search
    nz = np.nonzero(profile > 0)[0]
    if not len(nz):
        return None
    lo, hi = int(nz.min()), int(nz.max()) + 1
    if want <= 1:
        return [lo, hi]
    pitch = (hi - lo) / want
    cuts = [lo]
    for i in range(1, want):
        guess = lo + i * pitch
        a = int(max(lo + 1, guess - pitch * search))
        b = int(min(hi - 1, guess + pitch * search))
        if b <= a:
            cuts.append(int(guess))
            continue
        window = profile[a:b + 1]
        best = np.flatnonzero(window == window.min())
        # among equally empty columns take the one nearest the even-grid guess, so a
        # wide gutter doesn't drag the cut to one side
        pick = a + int(best[np.argmin(np.abs((a + best) - guess))])
        cuts.append(pick)
    cuts.append(hi)
    return cuts


def _row_cells(im, band, y0, ccuts, cols):
    """Build the cell images for one row given a set of cut positions."""
    lbl, owner = _assign(band, ccuts, cols)
    row = []
    for c in range(cols):
        strip = np.zeros(band.shape, bool)
        strip[:, ccuts[c]:ccuts[c + 1]] = True
        keep = np.isin(lbl, np.flatnonzero(owner == c))
        spanning = np.isin(lbl, np.flatnonzero(owner == -1))
        if spanning.any():                      # cut the merged ones at the boundary
            keep = keep | (spanning & strip)
        if not keep.any():
            # Two sprites drawn touching became one blob and it went to the neighbour,
            # leaving this cell empty. A straight cut through the overlap beats a hole.
            keep = band & strip
        if not keep.any():
            row.append(None)
            continue
        ys, xs = np.where(keep)
        bb = (int(xs.min()), y0 + int(ys.min()), int(xs.max()) + 1, y0 + int(ys.max()) + 1)
        ca = np.array(im.crop(bb))
        ca[..., 3] = np.where(keep[ys.min():ys.max() + 1, xs.min():xs.max() + 1],
                              ca[..., 3], 0)
        row.append(Image.fromarray(ca, "RGBA"))
    return row


def _usable(row):
    """How many cells in this row look like a whole sprite rather than a scrap."""
    areas = [0 if im is None else int((np.array(im)[..., 3] > ALPHA_T).sum())
             for im in row]
    live = [a for a in areas if a > 0]
    if not live:
        return 0
    floor = float(np.median(live)) * GOOD_FRAC
    return sum(1 for a in areas if a >= floor)


def _assign(band_mask, ccuts, cols):
    """Which cell each connected blob in a row band belongs to.

    A straight vertical cut severs anything that leans across it -- a cat's tail, a
    knight's sword, a trailing antenna -- leaving a stump on one side and a floating
    fragment on the other. Blobs that sit inside a single cell are therefore kept whole
    and travel with their own body, wherever their tip happens to reach. Only a blob
    genuinely spanning more than one cell (two sprites drawn touching) gets cut, because
    there's nothing else to be done with it.
    """
    from scipy import ndimage
    lbl, n = ndimage.label(band_mask, np.ones((3, 3)))
    owner = np.zeros(n + 1, dtype=int) - 1          # -1 = cut it at the boundaries
    if n:
        boxes = ndimage.find_objects(lbl)
        centres = [(ccuts[c] + ccuts[c + 1]) / 2.0 for c in range(cols)]
        for i, (ys, xs) in enumerate(boxes, start=1):
            if ys is None:
                continue
            # which cells does this blob overlap?
            hit = [c for c in range(cols)
                   if xs.start < ccuts[c + 1] and xs.stop > ccuts[c]]
            if len(hit) <= 1:
                owner[i] = hit[0] if hit else 0
            else:
                # tolerate a small overhang: if nearly all of it is in one cell, keep it
                span = xs.stop - xs.start
                best = max(hit, key=lambda c: min(xs.stop, ccuts[c + 1])
                           - max(xs.start, ccuts[c]))
                inside = min(xs.stop, ccuts[best + 1]) - max(xs.start, ccuts[best])
                mid = (xs.start + xs.stop) / 2.0
                near = min(range(cols), key=lambda c: abs(centres[c] - mid))
                owner[i] = best if (inside / max(1, span)) >= 0.72 and best == near else -1
    return lbl, owner


def cells(path, rows, cols):
    """-> list of rows, each a list of `cols` RGBA sprite images (already trimmed)."""
    im = Image.open(path).convert("RGBA")
    mask = np.array(im)[..., 3] > ALPHA_T
    if not mask.any():
        return []
    rcuts = split(ink(mask, 1), rows)
    if rcuts is None:
        return []
    out = []
    for r in range(rows):
        y0, y1 = rcuts[r], rcuts[r + 1]
        band = mask[y0:y1]
        if not band.any():
            out.append([None] * cols)
            continue
        profile = ink(band, 0)
        best_row, best_score = None, -1
        for s in SEARCHES:
            ccuts = split(profile, cols, s)
            if ccuts is None:
                continue
            row = _row_cells(im, band, y0, ccuts, cols)
            score = _usable(row)
            if score > best_score:
                best_row, best_score = row, score
            if score == cols:
                break                                # can't do better than every cell
        out.append(best_row if best_row is not None else [None] * cols)
    return out


def check(path, rows, cols):
    """Report how cleanly this atlas split -- used to catch a bad cut before importing."""
    im = Image.open(path).convert("RGBA")
    mask = np.array(im)[..., 3] > ALPHA_T
    rcuts = split(ink(mask, 1), rows)
    if rcuts is None:
        return {"ok": False, "why": "empty"}
    touching = 0
    widths = []
    for r in range(rows):
        y0, y1 = rcuts[r], rcuts[r + 1]
        band = mask[y0:y1]
        if not band.any():
            continue
        ccuts = split(ink(band, 0), cols)
        for c in range(cols):
            x0, x1 = ccuts[c], ccuts[c + 1]
            sub = mask[y0:y1, x0:x1]
            if not sub.any():
                continue
            colink = sub.any(axis=0)
            # ink hard against a cut means the sprite was sliced, not separated
            if colink[0] or colink[-1]:
                touching += 1
            xs = np.where(colink)[0]
            widths.append(int(xs.max() - xs.min() + 1))
    return {"ok": touching == 0, "sliced": touching, "n": len(widths),
            "w_min": min(widths) if widths else 0, "w_max": max(widths) if widths else 0}
