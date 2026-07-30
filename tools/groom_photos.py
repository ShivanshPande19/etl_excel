#!/usr/bin/env python3
"""
Groom the raw staff photos in photos/ into clean, print-ready ID-card headshots.

What it does per photo (the originals in photos/ are never modified):

  1. Cuts the person out with a human-segmentation model (u2net_human_seg) and
     refines the matte so hair and shoulders stay soft instead of card-cut.
  2. Places them on a clean, even studio background (soft neutral-grey
     gradient). This is what removes the rough concrete wall, the cabinet
     seams, the dark panel edges and the pencil scribble on the office wall.
  3. Levels the head using the eye line (small rotations only), so the cards
     don't look hand-held.
  4. Reframes to a standard 3:4 ID crop using face landmarks: face centred,
     correct head height and headroom, identical framing across all five.
  5. Fixes colour and light: white balance, face-metered exposure, gentle
     local contrast, mild saturation.
  6. Light, natural retouch: evens skin tone and sensor noise on skin only,
     protecting eyes, brows, lips, hair and clothing edges.

Deliberately NOT done: no face reshaping, slimming, whitening or feature
editing. An ID photo has to stay a true likeness of the person.

Usage:
    python3 tools/groom_photos.py                  # -> photos/groomed/
    python3 tools/groom_photos.py --contact-sheet  # also build review sheets
    python3 tools/groom_photos.py --only anshu
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove

REPO = Path(__file__).resolve().parent.parent
SRC_DIR = REPO / "photos"
OUT_DIR = REPO / "photos" / "groomed"
REVIEW_DIR = OUT_DIR / "_review"

SLUGS = ["deepak", "delip", "anshu", "sunil", "vansh"]
SRC_EXTS = [".jpeg", ".jpg", ".png", ".webp", ".JPG", ".JPEG"]

YUNET_PATH = Path.home() / ".models" / "yunet.onnx"
YUNET_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
             "models/face_detection_yunet/face_detection_yunet_2023mar.onnx")

# --- output geometry -------------------------------------------------------
OUT_W, OUT_H = 900, 1200          # 3:4 portrait
HEAD_RATIO = 0.50                 # hair-top -> chin, as a share of frame height
TOP_GAP = 0.14                    # clear space above the top of the hair
MAX_ROLL_DEG = 7.0                # never rotate more than this
ALPHA_GAMMA = 0.85                # <1 firms up soft hair so it doesn't read grey

# --- studio background -----------------------------------------------------
BG_CENTER = (246, 247, 249)       # near-white behind the head
BG_EDGE = (204, 210, 220)         # cool grey vignette towards the corners

# Anthropometry used to turn 5 landmarks into crown/chin estimates:
# eyes sit ~0.50 down the crown->chin head height, mouth ~0.77 down.
EYE_FRAC, MOUTH_FRAC = 0.50, 0.77


# ==========================================================================
# background
# ==========================================================================
def studio_background(w: int, h: int, focus_x: float = 0.5, focus_y: float = 0.36) -> np.ndarray:
    """Soft radial gradient: bright behind the head, gently darker at the edges."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = (xx - focus_x * w) / (w * 0.95)
    dy = (yy - focus_y * h) / (h * 0.95)
    t = np.clip(np.sqrt(dx * dx + dy * dy) / 0.95, 0.0, 1.0) ** 1.25
    t = t[..., None]
    bg = np.array(BG_CENTER, np.float32) * (1 - t) + np.array(BG_EDGE, np.float32) * t
    # a whisper of grain so big flat areas don't band on a printed card
    bg += np.random.default_rng(7).normal(0, 0.9, bg.shape).astype(np.float32)
    return np.clip(bg, 0, 255)


# ==========================================================================
# cutout
# ==========================================================================
def person_layers(pil_img: Image.Image, session) -> tuple[np.ndarray, np.ndarray]:
    """
    Return (rgb, alpha) for the person, where rgb is the original pixels with
    only the far background flattened to a neutral tone.

    Note on what is deliberately NOT used here: alpha matting also produces an
    "estimated foreground" with background spill divided out. In wispy hair,
    where alpha is small, that estimate amplifies noise into bright white
    strands - it visibly turned one person's dark hair silver. So the real
    pixels are kept, and wall-coloured fringe is dealt with by trimming the
    matte instead (see despill_hair).
    """
    raw = np.asarray(pil_img).astype(np.float32)
    cut = remove(
        pil_img,
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=248,
        alpha_matting_background_threshold=12,
        alpha_matting_erode_size=8,
        post_process_mask=True,
    )
    alpha = np.asarray(cut).astype(np.float32)[..., 3] / 255.0
    rgb = raw.copy()

    # keep only the largest blob - drops stray scraps of wall the net held on to
    binary = (alpha > 0.5).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if n > 1:
        biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha = np.where(labels == biggest, alpha, 0.0).astype(np.float32)

    # close pin-holes inside the body, then feather the boundary slightly
    solid = (alpha > 0.9).astype(np.uint8)
    solid = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    alpha = np.maximum(alpha, solid.astype(np.float32) * 0.995)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.1)
    alpha = np.clip(alpha, 0, 1)

    # firm up half-transparent hair so it keeps its colour on a light backdrop
    alpha = np.clip(alpha, 0, 1) ** ALPHA_GAMMA

    # Flatten the far background to a neutral tone. It gets replaced anyway,
    # and this stops later blurs/sharpening from dragging the old wall colour
    # back inwards across the silhouette.
    unknown = (alpha <= 0.02).astype(np.uint8)
    dist = cv2.distanceTransform(unknown, cv2.DIST_L2, 3)
    far = dist > max(12.0, 0.02 * min(alpha.shape))
    if far.any():
        rgb[far] = np.array(BG_CENTER, np.float32) * 0.86

    return rgb, alpha


def despill_hair(raw: np.ndarray, alpha: np.ndarray, chin_y: float) -> np.ndarray:
    """
    Trim wall-coloured pixels that the mask kept along the top of the head.

    The segmentation edge is nearly binary, so individual hair strands that the
    camera already blended with the wall get classified as "person" and carry
    the old wall colour onto the new backdrop - that is the grey/green halo
    above the hair. Here we walk a thin band just inside the silhouette and,
    where a pixel still matches the measured wall colour, hand it back to the
    background by lowering its alpha.

    Restricted to above the chin so bright shirts and shoulders are never eaten.
    """
    interior = (alpha > 0.5).astype(np.uint8)
    outside = alpha < 0.02
    if outside.sum() < 500 or interior.sum() < 500:
        return alpha

    wall = np.median(raw[outside], axis=0).astype(np.float32)

    band_px = max(4.0, 0.011 * min(alpha.shape))
    d_in = cv2.distanceTransform(interior, cv2.DIST_L2, 3)
    band = (d_in > 0) & (d_in < band_px)
    band[int(max(chin_y, 0)):, :] = False
    if not band.any():
        return alpha

    lab_img = cv2.cvtColor(np.clip(raw, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    lab_wall = cv2.cvtColor(wall.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    dist = np.linalg.norm(lab_img - lab_wall.reshape(1, 1, 3), axis=2)

    # 1 where the pixel is indistinguishable from the wall, 0 where it clearly isn't
    similar = np.clip(1.0 - dist / 26.0, 0.0, 1.0) ** 0.8
    # fade the effect towards the inside of the silhouette
    depth = np.clip(1.0 - d_in / band_px, 0.0, 1.0)

    w = np.where(band, similar * depth * 0.92, 0.0).astype(np.float32)
    alpha = alpha * (1.0 - w)
    return np.clip(cv2.GaussianBlur(alpha, (0, 0), 0.9), 0, 1)


# ==========================================================================
# face detection (YuNet: box + 5 landmarks)
# ==========================================================================
def _yunet():
    if not YUNET_PATH.exists() or YUNET_PATH.stat().st_size < 100_000:
        YUNET_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
    return cv2.FaceDetectorYN_create(str(YUNET_PATH), "", (320, 320), 0.6, 0.3, 5000)


def detect_face(bgr: np.ndarray, detector):
    """
    Return (box, pts) in full-resolution coordinates, or (None, None).
    box = (x, y, w, h); pts = 5x2 array [right eye, left eye, nose,
    right mouth corner, left mouth corner] as seen in the image.
    """
    h, w = bgr.shape[:2]
    for long_side in (640, 1024, 480):
        sc = long_side / max(h, w)
        small = cv2.resize(bgr, (int(round(w * sc)), int(round(h * sc))),
                           interpolation=cv2.INTER_AREA)
        detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = detector.detect(small)
        if faces is None or not len(faces):
            continue
        f = max(faces, key=lambda r: r[2] * r[3])
        box = tuple(int(round(v / sc)) for v in f[:4])
        pts = (np.array(f[4:14], np.float32).reshape(5, 2) / sc)
        return box, pts
    return None, None


# ==========================================================================
# levelling + framing
# ==========================================================================
def level_eyes(layers: list[np.ndarray], pts: np.ndarray | None):
    """
    Rotate every layer so the eye line is horizontal. Small angles only.
    Returns (rotated_layers, rotated_pts, angle).
    """
    if pts is None:
        return layers, pts, 0.0
    (rx, ry), (lx, ly) = pts[0], pts[1]
    angle = float(np.degrees(np.arctan2(ly - ry, lx - rx)))
    if abs(angle) < 0.4 or abs(angle) > MAX_ROLL_DEG:
        return layers, pts, 0.0

    h, w = layers[0].shape[:2]
    m = cv2.getRotationMatrix2D(((rx + lx) / 2.0, (ry + ly) / 2.0), angle, 1.0)
    # BORDER_REPLICATE keeps the torso running to the frame edge, so the
    # rotation can't leave a diagonal cut where the body meets the border.
    out = [cv2.warpAffine(
               l, m, (w, h),
               flags=cv2.INTER_LINEAR if l.ndim == 2 else cv2.INTER_CUBIC,
               borderMode=cv2.BORDER_REPLICATE)
           for l in layers]
    pts_r = ((m[:, :2] @ pts.T).T + m[:, 2]).astype(np.float32)
    return out, pts_r, angle


def head_metrics(alpha: np.ndarray, box, pts: np.ndarray | None):
    """Estimate top-of-hair y, chin y and face centre x."""
    h, w = alpha.shape
    mask = alpha > 0.5

    if pts is not None:
        eye_y = float((pts[0][1] + pts[1][1]) / 2.0)
        mouth_y = float((pts[3][1] + pts[4][1]) / 2.0)
        centre_x = float((pts[0][0] + pts[1][0]) / 2.0)
        span = max(mouth_y - eye_y, 1.0)
        head_h = span / (MOUTH_FRAC - EYE_FRAC)
        skull_top = eye_y - EYE_FRAC * head_h
        chin = eye_y + EYE_FRAC * head_h
        face_w = box[2] if box else head_h * 0.62
    else:
        rows = mask.sum(axis=1)
        body_w = max(int(rows.max()), 1)
        skull_top = next((y for y in range(h) if rows[y] > max(6, 0.045 * body_w)), 0)
        cols = np.where(mask[int(skull_top):int(skull_top) + int(0.25 * h)].any(axis=0))[0]
        centre_x = float((cols.min() + cols.max()) / 2.0) if len(cols) else w / 2.0
        face_w = 0.30 * w
        chin = skull_top + max(0.20 * h, face_w * 1.45)

    # top of the hair, measured from the matte but only in the columns around
    # the face, so a raised hand or a shoulder can't be mistaken for hair
    x0 = int(max(0, centre_x - face_w * 0.85))
    x1 = int(min(w, centre_x + face_w * 0.85))
    band = mask[:, x0:x1] if x1 > x0 else mask
    counts = band.sum(axis=1)
    thresh = max(4, 0.05 * max(int(counts.max()), 1))
    hair_rows = np.where(counts > thresh)[0]
    hair_top = float(hair_rows[0]) if len(hair_rows) else float(max(skull_top, 0))

    # trust the matte, but don't let it run away from the anthropometric guess
    hair_top = float(np.clip(hair_top, skull_top - 0.55 * (chin - skull_top), skull_top + 0.10 * (chin - skull_top)))
    return hair_top, float(chin), float(centre_x)


def id_crop_box(alpha, box, pts, img_w: int, img_h: int):
    """
    3:4 crop window for an ID headshot. Padding above the head is fine (it
    becomes clean background); the bottom and sides are kept inside the photo
    so we never leave a torso or shoulder floating in mid-air.
    """
    hair_top, chin, centre_x = head_metrics(alpha, box, pts)
    head_h = max(chin - hair_top, 0.12 * img_h)

    box_h = head_h / HEAD_RATIO
    box_w = box_h * (OUT_W / OUT_H)

    # if the ideal window is wider/taller than the photo, fall back to the
    # largest 3:4 window the photo can actually give us
    if box_w > img_w:
        box_w = float(img_w)
        box_h = box_w * (OUT_H / OUT_W)
    if box_h > img_h:
        box_h = float(img_h)
        box_w = box_h * (OUT_W / OUT_H)

    top = hair_top - TOP_GAP * box_h
    bottom = top + box_h
    if bottom > img_h:                      # slide up instead of inventing a torso
        top -= bottom - img_h
        bottom = float(img_h)

    left = centre_x - box_w / 2.0
    right = left + box_w
    if left < 0:
        left, right = 0.0, box_w
    if right > img_w:
        right = float(img_w)
        left = max(0.0, right - box_w)

    return int(round(left)), int(round(top)), int(round(right)), int(round(bottom))


def crop_with_pad(img: np.ndarray, box, fill=0.0) -> np.ndarray:
    """Crop, padding with `fill` where the window falls outside the image."""
    l, t, r, b = box
    h, w = img.shape[:2]
    out = np.full((b - t, r - l) + img.shape[2:], fill, np.float32)
    sl, st = max(l, 0), max(t, 0)
    sr, sb = min(r, w), min(b, h)
    if sr > sl and sb > st:
        out[st - t:sb - t, sl - l:sr - l] = img[st:sb, sl:sr]
    return out


# ==========================================================================
# colour + light
# ==========================================================================
def white_balance(rgb: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Shades-of-grey balance measured on the subject only, applied gently."""
    wsum = weight.sum() + 1e-6
    means = np.sqrt(np.maximum(
        [(rgb[..., c] ** 2 * weight).sum() / wsum for c in range(3)], 1e-6))
    gain = means.mean() / means
    gain = np.clip(1.0 + (gain - 1.0) * 0.45, 0.93, 1.09)   # damped, no surprises
    return np.clip(rgb * gain, 0, 255)


def _smoothstep(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def face_exposure(rgb: np.ndarray, face_mask: np.ndarray, target_l: float = 63.0) -> np.ndarray:
    """
    Lift the face to a good print brightness.

    The lift is masked out of the deep shadows on purpose. A plain gamma curve
    raises everything, which turns black hair into grey hair - the single most
    ageing thing you can do to an ID photo. Here midtones (skin) move and the
    darkest tones (hair, dark uniforms) stay put.
    """
    if face_mask.sum() < 50:
        return rgb
    lab = cv2.cvtColor((np.clip(rgb, 0, 255) / 255).astype(np.float32), cv2.COLOR_RGB2LAB)
    cur = float(np.median(lab[..., 0][face_mask]))
    if cur <= 1:
        return rgb
    ratio = float(np.clip(target_l / cur, 0.80, 1.42))
    gamma = float(np.clip(1.0 / (1.0 + (ratio - 1.0) * 1.15), 0.62, 1.30))

    x = np.clip(rgb / 255.0, 0, 1)
    lifted = x ** gamma
    lum = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    w = _smoothstep(lum, 0.06, 0.30)[..., None]
    return np.clip((x * (1 - w) + lifted * w) * 255.0, 0, 255)


def local_contrast_and_colour(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    l2 = cv2.createCLAHE(clipLimit=1.25, tileGridSize=(8, 8)).apply(l)
    l = cv2.addWeighted(l, 0.45, l2, 0.55, 0)          # subtle, not HDR
    out = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2RGB).astype(np.float32)

    hsv = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.06, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    ycrcb = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    m = ((cr >= 133) & (cr <= 183) & (cb >= 77) & (cb <= 133) & (y >= 45)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), 6.0)


def retouch(rgb: np.ndarray, strength: float = 0.42) -> np.ndarray:
    """
    Even out skin tone and camera noise on skin only. Eyes, brows, lips, hair
    and clothing edges are protected by a detail mask, so nothing meaningful
    is smeared and the person still looks like themselves.
    """
    u8 = np.clip(rgb, 0, 255).astype(np.uint8)
    short = min(rgb.shape[:2])
    smooth = cv2.bilateralFilter(u8, 0, 26, max(3, int(short * 0.012))).astype(np.float32)

    gray = cv2.cvtColor(u8, cv2.COLOR_RGB2GRAY)
    detail = np.abs(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1.2), cv2.CV_32F, ksize=3))
    detail = cv2.GaussianBlur(cv2.dilate(detail, np.ones((5, 5), np.uint8)), (0, 0), 2.0)
    keep = np.clip(detail / (np.percentile(detail, 96) + 1e-6), 0, 1) ** 0.6   # 1 = protect

    w = (skin_mask(rgb) * (1.0 - keep) * strength)[..., None]
    return rgb * (1 - w) + smooth * w


def _lum(rgb01: np.ndarray) -> np.ndarray:
    return rgb01 @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def preserve_dark_tones(rgb: np.ndarray, raw: np.ndarray, skin: np.ndarray,
                        lo: float = 0.34, hi: float = 0.62,
                        allow: float = 1.06) -> np.ndarray:
    """
    Hard guarantee that dark, non-skin tones never get brighter than they were.

    Brightening the face drags hair and dark uniforms up with it, and lifted
    black hair reads as grey hair - which visibly ages someone on an ID card.
    Luminance alone can't separate the two, because dark hair and dark skin
    overlap in brightness, so the skin mask is subtracted out here: skin keeps
    the full exposure lift while hair and the black work polos stay true.
    """
    x, r = np.clip(rgb / 255.0, 0, 1), np.clip(raw / 255.0, 0, 1)
    lum_out, lum_raw = _lum(x), _lum(r)
    darkness = (1.0 - _smoothstep(lum_raw, lo, hi)) * (1.0 - np.clip(skin, 0, 1))
    over = np.clip(lum_out - (lum_raw * allow + 0.012), 0, None) * darkness
    scale = np.where(lum_out > 1e-4, (lum_out - over) / np.maximum(lum_out, 1e-4), 1.0)
    return np.clip(rgb * scale[..., None], 0, 255)


def tame_shine(rgb: np.ndarray, strength: float = 0.55) -> np.ndarray:
    """Pull down specular hot spots on skin (forehead / nose / cheekbones)."""
    skin = skin_mask(rgb)
    sel = skin > 0.35
    if sel.sum() < 200:
        return rgb
    lab = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    l = lab[..., 0]
    thr = float(np.median(l[sel])) + 14.0
    excess = np.clip(l - thr, 0, None) * np.clip(skin, 0, 1)
    lab[..., 0] = np.clip(l - excess * strength, 0, 255)
    return cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32)


def unsharp(rgb: np.ndarray, amount: float = 0.55, radius: float = 1.5,
            protect: np.ndarray | None = None) -> np.ndarray:
    """
    Unsharp mask. `protect` (0..1) damps sharpening where it is 1 - used on the
    cutout boundary, because sharpening across a matte edge is what produces
    those tell-tale bright halos around hair.
    """
    blur = cv2.GaussianBlur(rgb, (0, 0), radius)
    sharp = rgb * (1 + amount) - blur * amount
    if protect is not None:
        p = np.clip(protect, 0, 1)[..., None]
        sharp = sharp * (1 - p) + rgb * p
    return np.clip(sharp, 0, 255)


# ==========================================================================
# per-photo pipeline
# ==========================================================================
def find_source(slug: str) -> Path | None:
    return next((SRC_DIR / f"{slug}{e}" for e in SRC_EXTS if (SRC_DIR / f"{slug}{e}").exists()), None)


def groom(slug: str, session, detector) -> dict:
    src = find_source(slug)
    if src is None:
        raise FileNotFoundError(f"no source photo for {slug}")

    pil = Image.open(src).convert("RGB")
    raw_full = np.asarray(pil).astype(np.float32)
    img_h, img_w = raw_full.shape[:2]

    # face detection runs on the raw frame; colour work runs on the
    # spill-corrected foreground estimate
    box, pts = detect_face(cv2.cvtColor(raw_full.astype(np.uint8), cv2.COLOR_RGB2BGR), detector)
    rgb_full, alpha_full = person_layers(pil, session)

    # ---- level the eye line -------------------------------------------
    (rgb_full, alpha_full, raw_full), pts, roll = level_eyes(
        [rgb_full, alpha_full, raw_full], pts)
    alpha_full = np.clip(alpha_full, 0, 1)

    # ---- trim the wall-coloured fringe above the head ------------------
    _, chin_full, _ = head_metrics(alpha_full, box, pts)
    alpha_full = despill_hair(raw_full, alpha_full, chin_full)

    # ---- reframe to a 3:4 ID crop -------------------------------------
    cbox = id_crop_box(alpha_full, box, pts, img_w, img_h)
    ch, cw = cbox[3] - cbox[1], cbox[2] - cbox[0]
    scale = max(OUT_W / cw, OUT_H / ch)
    interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    dsize = (int(round(cw * scale)), int(round(ch * scale)))
    y0, x0 = (dsize[1] - OUT_H) // 2, (dsize[0] - OUT_W) // 2

    def to_output(layer, linear=False):
        c = crop_with_pad(layer, cbox, 0.0)
        c = cv2.resize(c, dsize, interpolation=cv2.INTER_LINEAR if linear else interp)
        return c[y0:y0 + OUT_H, x0:x0 + OUT_W]

    rgb = to_output(rgb_full)
    raw = to_output(raw_full)                     # aligned reference for tone limits
    alpha = np.clip(to_output(alpha_full, linear=True), 0, 1)

    subject = alpha > 0.5
    # skin measured on the untouched frame, so the tone guard below has a
    # reference that later colour steps can't skew
    skin_ref = skin_mask(raw) * (alpha > 0.3)

    # face region in output coordinates, used to meter exposure
    if box is not None:
        fx = (box[0] - cbox[0]) * scale - x0
        fy = (box[1] - cbox[1]) * scale - y0
        fw, fh = box[2] * scale, box[3] * scale
        fm = np.zeros((OUT_H, OUT_W), bool)
        fm[max(0, int(fy)):max(0, int(fy + fh)), max(0, int(fx)):max(0, int(fx + fw))] = True
        face_mask = fm & subject
    else:
        face_mask = subject & (skin_mask(rgb) > 0.5)
    if not face_mask.any():
        face_mask = subject

    # soft 0..1 mask of the cutout boundary, used to keep sharpening off the edge
    edge_soft = cv2.GaussianBlur(
        ((alpha > 0.02) & (alpha < 0.98)).astype(np.float32), (0, 0), 2.5)
    edge_soft = np.clip(edge_soft * 2.2, 0, 1)

    # ---- colour, light, retouch ---------------------------------------
    rgb = white_balance(rgb, alpha)
    rgb = face_exposure(rgb, face_mask)
    rgb = local_contrast_and_colour(rgb)
    rgb = tame_shine(rgb)
    rgb = preserve_dark_tones(rgb, raw, skin_ref)
    rgb = retouch(rgb)
    rgb = unsharp(rgb, amount=0.62 if scale > 1.05 else 0.45, protect=edge_soft)
    rgb = preserve_dark_tones(rgb, raw, skin_ref, allow=1.12)   # again, post-sharpen

    # ---- composite on the studio background ---------------------------
    bg = studio_background(OUT_W, OUT_H)
    a = alpha[..., None]
    out = rgb * a + bg * (1 - a)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst = OUT_DIR / f"{slug}.jpeg"
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(
        dst, "JPEG", quality=93, subsampling=1, optimize=True, dpi=(300, 300))

    hair_top, chin, _ = head_metrics(alpha_full, box, pts)
    head_frac = chin - hair_top
    return {
        "slug": slug, "src": src, "src_size": (img_w, img_h), "dst": dst,
        "face": box is not None, "roll": roll, "box": cbox,
        "head_frac_out": round(head_frac * scale / OUT_H, 3),
    }


# ==========================================================================
# review sheets
# ==========================================================================
def contact_sheets(results: list[dict]) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pane_h, pad = 620, 18
    rows = []

    for r in results:
        panes = []
        for im in (Image.open(r["src"]).convert("RGB"), Image.open(r["dst"]).convert("RGB")):
            panes.append(im.resize((int(im.width * pane_h / im.height), pane_h), Image.LANCZOS))
        row_w = sum(p.width for p in panes) + pad * 3
        row = Image.new("RGB", (row_w, pane_h + pad * 2), (24, 26, 30))
        x = pad
        for p in panes:
            row.paste(p, (x, pad))
            x += p.width + pad
        row.save(REVIEW_DIR / f"{r['slug']}-before-after.jpg", quality=88, optimize=True)
        rows.append(row)

    sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (24, 26, 30))
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    sheet.save(REVIEW_DIR / "all-before-after.jpg", quality=86, optimize=True)

    cell_w, cell_h = 300, 400
    grid = Image.new("RGB", (cell_w * len(results), cell_h), (24, 26, 30))
    for i, r in enumerate(results):
        grid.paste(Image.open(r["dst"]).resize((cell_w, cell_h), Image.LANCZOS), (i * cell_w, 0))
    grid.save(REVIEW_DIR / "groomed-strip.jpg", quality=90, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contact-sheet", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    session = new_session("u2net_human_seg")
    detector = _yunet()

    results = []
    for slug in (args.only or SLUGS):
        r = groom(slug, session, detector)
        results.append(r)
        print(f"{r['slug']:8s} {str(r['src_size']):12s} -> {OUT_W}x{OUT_H}  "
              f"crop={r['box']}  roll={r['roll']:+.1f}deg  "
              f"head={r['head_frac_out']:.2f}H  face={'yes' if r['face'] else 'matte-only'}")

    if args.contact_sheet:
        contact_sheets(results)
        print(f"review sheets -> {REVIEW_DIR}")


if __name__ == "__main__":
    main()
