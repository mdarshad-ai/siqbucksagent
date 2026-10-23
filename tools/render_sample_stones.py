"""
Draws the sample stone photos in backend/sample_data/images/ (one per seed
stone). They are illustrations, not real photos, and carry a small
"SAMPLE IMAGE" mark. Rerun after changing a stone:

    pip install pillow numpy
    python tools/render_sample_stones.py

Each stone is drawn at 2x and scaled down for smooth edges: faceted cuts
from rings of facets shaded by a top-left light, cabochons and spheres as
lit domes, and a few special shapes (crystal point, slab, rough lot).
"""

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "sample_data" / "images"
SIZE = 1200
R = SIZE * 2  # render scale
CENTER = (R / 2, R * 0.47)
LIGHT = np.array([-0.55, -0.83])  # from the top left
LIGHT3 = np.array([-0.45, -0.6, 0.66])
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


# ---------- colour helpers ----------

def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


class Palette:
    def __init__(self, base, deep, light):
        self.base, self.deep, self.light = base, deep, light

    def at(self, b):
        """b: 0 (darkest) .. 1 (light) .. 1.3 (white sparkle)."""
        if b <= 0.5:
            return mix(self.deep, self.base, b / 0.5)
        if b <= 1.0:
            return mix(self.base, self.light, (b - 0.5) / 0.5)
        return mix(self.light, (255, 255, 255), (b - 1.0) / 0.3 * 0.75)


# ---------- drawing helpers ----------

def background():
    y, x = np.mgrid[0:R, 0:R].astype(np.float32)
    d = np.sqrt(((x - R / 2) / (R * 0.62)) ** 2 + ((y - R * 0.44) / (R * 0.62)) ** 2)
    t = np.clip(d, 0, 1)[..., None] ** 1.6
    center = np.array([252, 248, 240], np.float32)
    edge = np.array([230, 218, 198], np.float32)
    arr = center * (1 - t) + edge * t
    img = Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
    return img


def soft_ellipse(img, box, color, alpha, blur):
    pad = int(blur * 3)
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((pad, pad, pad + x1 - x0, pad + y1 - y0), fill=int(255 * alpha))
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    layer = Image.new("RGBA", (w, h), color + (0,))
    layer.putalpha(mask)
    img.alpha_composite(layer, dest=(x0 - pad, y0 - pad))


def ground(img, cx, cy, rx, ry, color):
    """Contact shadow plus the coloured light a gem throws on the cloth."""
    soft_ellipse(img, (cx - rx * 0.95, cy + ry * 0.55, cx + rx * 1.05, cy + ry * 1.25), (70, 52, 34), 0.30, rx * 0.12)
    soft_ellipse(img, (cx - rx * 0.6, cy + ry * 0.5, cx + rx * 0.8, cy + ry * 1.15), color, 0.22, rx * 0.18)


def poly_bbox(poly, pad=2):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return int(min(xs)) - pad, int(min(ys)) - pad, int(max(xs)) + pad + 1, int(max(ys)) + pad + 1


def gradient_poly(img, poly, c1, c2, p1, p2, alpha=255):
    """Fill a polygon with a linear gradient from c1 at p1 to c2 at p2."""
    x0, y0, x1, y1 = poly_bbox(poly)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in poly], fill=alpha)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    denom = vx * vx + vy * vy or 1.0
    t = np.clip(((xs + x0 - p1[0]) * vx + (ys + y0 - p1[1]) * vy) / denom, 0, 1)[..., None]
    arr = np.array(c1, np.float32) * (1 - t) + np.array(c2, np.float32) * t
    layer = Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
    layer.putalpha(mask)
    img.alpha_composite(layer, dest=(x0, y0))


def edges(img, polys, color=(255, 255, 255), alpha=70, width=3):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for poly in polys:
        d.line(list(poly) + [poly[0]], fill=color + (alpha,), width=width, joint="curve")
    img.alpha_composite(layer)


def sparkle(img, x, y, size, alpha=1.0):
    layer = Image.new("L", (int(size * 4), int(size * 4)), 0)
    d = ImageDraw.Draw(layer)
    c = size * 2
    d.line((c - size * 1.8, c, c + size * 1.8, c), fill=int(230 * alpha), width=max(2, int(size * 0.07)))
    d.line((c, c - size * 1.8, c, c + size * 1.8), fill=int(230 * alpha), width=max(2, int(size * 0.07)))
    d.line((c - size * 0.7, c - size * 0.7, c + size * 0.7, c + size * 0.7), fill=int(150 * alpha), width=max(1, int(size * 0.04)))
    d.line((c - size * 0.7, c + size * 0.7, c + size * 0.7, c - size * 0.7), fill=int(150 * alpha), width=max(1, int(size * 0.04)))
    d.ellipse((c - size * 0.22, c - size * 0.22, c + size * 0.22, c + size * 0.22), fill=int(255 * alpha))
    glow = layer.filter(ImageFilter.GaussianBlur(size * 0.18))
    layer = Image.fromarray(np.maximum(np.array(layer), np.array(glow)))
    white = Image.new("RGBA", layer.size, (255, 255, 255, 0))
    white.putalpha(layer)
    img.alpha_composite(white, dest=(int(x - c), int(y - c)))


ZOOM = 0.8  # crop to the middle of the render so the stone fills the frame


def finish(img, path):
    half = R * ZOOM / 2
    img = img.crop((int(R / 2 - half), int(R * 0.49 - half), int(R / 2 + half), int(R * 0.49 + half)))
    out = img.resize((SIZE, SIZE), Image.LANCZOS).convert("RGB")
    d = ImageDraw.Draw(out)
    font = ImageFont.truetype(FONT, 18)
    d.text((SIZE - 28, SIZE - 26), "SAMPLE IMAGE", font=font, fill=(160, 146, 122), anchor="rs")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path, "WEBP", quality=86, method=6)


# ---------- faceted cuts ----------

def shape_point(shape, t, a, b):
    c, s = math.cos(t), math.sin(t)
    if shape == "round":
        return a * c, a * s
    if shape == "oval":
        return a * c, b * s
    if shape == "cushion":
        n = 3.4
        return a * math.copysign(abs(c) ** (2 / n), c), b * math.copysign(abs(s) ** (2 / n), s)
    if shape == "pear":
        # point at the top, round at the bottom
        return b * s * ((1 - math.cos(t)) / 2) ** 0.55, -a * math.cos(t)
    if shape == "trillion":
        k = 2 * math.pi / 3
        local = ((t + math.pi / 2) % k) - k / 2
        r = a * (0.5 / math.cos(local)) * 1.0
        r = 0.82 * r + 0.18 * a * 0.62
        return r * c, r * s
    raise ValueError(shape)


def brilliant(img, cx, cy, a, b, shape, pal, rng, m=8, table=0.52, fire=0.12, color_for=None):
    """A brilliant-style crown: table, star, kite and upper girdle facets."""
    def ring(scale, angles, offset=0.0):
        pts = []
        for t in angles:
            x, y = shape_point(shape, t + offset, a, b)
            pts.append((cx + x * scale, cy + y * scale))
        return pts

    step = 2 * math.pi / m
    start = -math.pi / 2
    T = ring(table, [start + step * j + step / 2 for j in range(m)])
    Q = ring(0.80, [start + step * j for j in range(m)])
    G = ring(1.0, [start + step * k / 2 for k in range(2 * m)])

    facets = []
    for j in range(m):
        jn = (j + 1) % m
        facets.append(("star", [T[j - 1], T[j], Q[j]]))
        facets.append(("kite", [T[j], Q[j], G[2 * j + 1], Q[jn]]))
        facets.append(("girdle", [Q[j], G[2 * j], G[2 * j + 1]]))
        facets.append(("girdle", [Q[jn], G[2 * j + 1], G[(2 * j + 2) % (2 * m)]]))

    bright = []
    for kind, poly in facets:
        mx = sum(p[0] for p in poly) / len(poly)
        my = sum(p[1] for p in poly) / len(poly)
        u = np.array([(mx - cx) / a, (my - cy) / b])
        u = u / (np.linalg.norm(u) or 1)
        lam = float(u @ LIGHT)
        level = 0.55 + 0.32 * lam + rng.uniform(-0.22, 0.22)
        roll = rng.random()
        if roll < 0.24:
            level *= 0.45  # dark pavilion reflection
        elif roll < 0.24 + fire:
            level = 1.12 + rng.uniform(0, 0.15)
            bright.append((mx, my))
        if kind == "girdle":
            level -= 0.05
        p = color_for(rng) if color_for else pal
        far = max(poly, key=lambda q: (q[0] - cx) ** 2 + (q[1] - cy) ** 2)
        near = min(poly, key=lambda q: (q[0] - cx) ** 2 + (q[1] - cy) ** 2)
        gradient_poly(img, poly, p.at(level + 0.14), p.at(level - 0.2), far, near)

    # Table: a lit window with the pavilion reflected inside it.
    p = color_for(rng) if color_for else pal
    gradient_poly(img, T, p.at(0.95), p.at(0.38), (cx - a * 0.4, cy - b * 0.4), (cx + a * 0.45, cy + b * 0.45))
    inner = ring(table * 0.62, [start + step * j for j in range(m)])
    gradient_poly(img, inner, p.at(0.25), p.at(0.55), (cx + a * 0.2, cy + b * 0.2), (cx - a * 0.2, cy - b * 0.2), alpha=150)
    for j in range(m):
        if rng.random() < 0.5:
            gradient_poly(img, [(cx, cy), T[j], T[(j + 1) % m]], p.at(1.05), p.at(0.6), T[j], (cx, cy), alpha=90)

    edges(img, [poly for _, poly in facets] + [T], alpha=55, width=3)
    edges(img, [G], color=mix(pal.light, (255, 255, 255), 0.6), alpha=170, width=5)
    for x, y in rng.sample(bright, min(len(bright), 3)):
        sparkle(img, x, y, rng.uniform(a * 0.09, a * 0.15), alpha=0.9)
    sparkle(img, cx - a * 0.28, cy - b * 0.3, a * 0.16)


def step_cut(img, cx, cy, w, h, pal, rng, steps=3, inclusions=0):
    """Emerald cut: an octagon with step facets around a long table."""
    def octagon(inset):
        ww, hh = w - 2 * inset, h - 2 * inset
        k = min(ww, hh) * 0.2
        x0, y0, x1, y1 = cx - ww / 2, cy - hh / 2, cx + ww / 2, cy + hh / 2
        return [(x0 + k, y0), (x1 - k, y0), (x1, y0 + k), (x1, y1 - k), (x1 - k, y1), (x0 + k, y1), (x0, y1 - k), (x0, y0 + k)]

    depth = min(w, h) * 0.085
    rings = [octagon(depth * i) for i in range(steps + 1)]
    normals = []
    for i in range(8):
        a = rings[0][i]
        b = rings[0][(i + 1) % 8]
        n = np.array([b[1] - a[1], -(b[0] - a[0])])
        normals.append(n / np.linalg.norm(n))
    polys = []
    for s in range(steps):
        outer, inner = rings[s], rings[s + 1]
        for i in range(8):
            poly = [outer[i], outer[(i + 1) % 8], inner[(i + 1) % 8], inner[i]]
            lam = float(normals[i] @ LIGHT)
            level = 0.55 + 0.3 * lam + (0.16 if s % 2 == 0 else -0.16) + rng.uniform(-0.1, 0.1)
            gradient_poly(img, poly, pal.at(level + 0.12), pal.at(level - 0.15), outer[i], inner[i])
            polys.append(poly)
    table = rings[-1]
    gradient_poly(img, table, pal.at(0.9), pal.at(0.42), (cx - w * 0.3, cy - h * 0.3), (cx + w * 0.3, cy + h * 0.3))
    # Steps reflected in the table ("hall of mirrors").
    tw, th = w - 2 * depth * steps, h - 2 * depth * steps
    for i in range(1, 4):
        f = 1 - i * 0.2
        rect = [(cx - tw * f / 2, cy - th * f / 2), (cx + tw * f / 2, cy - th * f / 2),
                (cx + tw * f / 2, cy + th * f / 2), (cx - tw * f / 2, cy + th * f / 2)]
        edges(img, [rect], color=pal.light, alpha=45, width=4)
    for _ in range(inclusions):
        x = cx + rng.uniform(-tw * 0.35, tw * 0.35)
        y = cy + rng.uniform(-th * 0.35, th * 0.35)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        pts = [(x, y)]
        for _ in range(4):
            x += rng.uniform(-40, 40)
            y += rng.uniform(-25, 25)
            pts.append((x, y))
        d.line(pts, fill=(235, 250, 240, 60), width=6, joint="curve")
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(3)))
    edges(img, polys + [table], alpha=60, width=3)
    edges(img, [rings[0]], color=mix(pal.light, (255, 255, 255), 0.6), alpha=170, width=5)
    sparkle(img, cx - w * 0.22, cy - h * 0.28, min(w, h) * 0.12)
    sparkle(img, cx + w * 0.28, cy + h * 0.1, min(w, h) * 0.07, alpha=0.7)


# ---------- domes: cabochons, opal, sphere ----------

def dome(img, cx, cy, a, b, color_field, spec=0.9, wobble=None, gloss=40, ambient=0.45):
    """A lit dome: color_field(u, v, rn) -> (h, w, 3) float array of base colours."""
    grow = 1.15 if wobble else 1.0  # a wobbly outline reaches past a and b
    x0, y0 = int(cx - a * grow) - 2, int(cy - b * grow) - 2
    x1, y1 = int(cx + a * grow) + 3, int(cy + b * grow) + 3
    h, w = y1 - y0, x1 - x0
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (xs + x0 - cx) / a
    v = (ys + y0 - cy) / b
    r = np.sqrt(u * u + v * v)
    if wobble:
        theta = np.arctan2(v, u)
        r = r / wobble(theta)
    inside = r <= 1.0
    z = np.sqrt(np.clip(1 - r * r, 0, 1))
    nu, nv = u / np.maximum(r, 1e-6) * r, v / np.maximum(r, 1e-6) * r
    n = np.stack([nu, nv, z], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
    diffuse = np.clip(n @ LIGHT3, 0, 1)
    half = LIGHT3 + np.array([0, 0, 1.0])
    half /= np.linalg.norm(half)
    specular = np.clip(n @ half, 0, 1) ** gloss
    base = color_field(u, v, r)
    shade = (ambient + (1.2 - ambient) * diffuse)[..., None]
    col = base * shade + 255 * spec * specular[..., None]
    # Gentle rim darkening (less for milky, translucent stones).
    col *= (1 - (1 - ambient) * 0.45 * (1 - z))[..., None]
    col = np.clip(col, 0, 255)
    alpha = np.clip((1.0 - r) * min(a, b) * 0.9, 0, 1) * 255
    layer = np.dstack([col, alpha]).astype(np.uint8)
    layer[~inside] = 0
    img.alpha_composite(Image.fromarray(layer, "RGBA"), dest=(x0, y0))


def noise_field(shape, rng, scale, octaves=3):
    h, w = shape
    total = np.zeros((h, w), np.float32)
    amp = 1.0
    for o in range(octaves):
        gh, gw = max(2, int(h / scale * 2 ** o)), max(2, int(w / scale * 2 ** o))
        grid = np.array([[rng.random() for _ in range(gw)] for _ in range(gh)], np.float32)
        layer = np.array(Image.fromarray((grid * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
        total += layer * amp
        amp *= 0.5
    total -= total.min()
    return total / (total.max() or 1)


# ---------- the stones ----------

def sapphire(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((38, 72, 175), (8, 18, 70), (125, 165, 245))
    ground(img, cx, cy, 560, 430, (60, 90, 200))
    brilliant(img, cx, cy, 560, 430, "oval", pal, rng)
    return img


def emerald(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((18, 128, 78), (4, 46, 28), (115, 212, 152))
    ground(img, cx, cy, 520, 380, (30, 150, 90))
    step_cut(img, cx, cy, 1040, 760, pal, rng, inclusions=4)
    return img


def ruby(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((192, 18, 52), (66, 0, 18), (255, 110, 140))
    ground(img, cx, cy, 500, 500, (210, 30, 70))
    brilliant(img, cx, cy, 500, 500, "round", pal, rng, m=8)
    return img


def paraiba(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((32, 205, 200), (0, 92, 112), (175, 255, 246))
    ground(img, cx, cy, 540, 420, (40, 210, 210))
    brilliant(img, cx, cy, 540, 420, "oval", pal, rng, fire=0.18)
    return img


def padparadscha(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((240, 138, 110), (150, 58, 48), (255, 205, 186))
    ground(img, cx, cy, 500, 470, (245, 140, 110))
    brilliant(img, cx, cy, 500, 470, "cushion", pal, rng)
    return img


def tanzanite(rng):
    img = background()
    cx, cy = CENTER[0], CENTER[1] + 40
    pal = Palette((88, 68, 190), (28, 14, 88), (172, 152, 255))
    ground(img, cx, cy - 40, 560, 470, (100, 80, 210))
    brilliant(img, cx, cy, 620, 620, "trillion", pal, rng, m=6, table=0.5)
    return img


def spinel(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((236, 58, 140), (110, 8, 60), (255, 165, 212))
    ground(img, cx, cy, 540, 420, (240, 70, 150))
    brilliant(img, cx, cy, 540, 420, "oval", pal, rng)
    return img


def aquamarine(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((72, 150, 200), (18, 68, 108), (175, 224, 246))
    ground(img, cx, cy, 540, 400, (80, 160, 210))
    step_cut(img, cx, cy, 1080, 800, pal, rng)
    return img


def alexandrite(rng):
    img = background()
    cx, cy = CENTER
    green = Palette((30, 128, 108), (6, 48, 40), (120, 205, 180))
    berry = Palette((150, 40, 108), (60, 10, 45), (220, 120, 180))
    ground(img, cx, cy, 480, 480, (90, 90, 120))
    brilliant(img, cx, cy, 480, 480, "round", green, rng, color_for=lambda r: berry if r.random() < 0.38 else green)
    return img


def black_opal(rng):
    img = background()
    cx, cy = CENTER
    ground(img, cx, cy, 560, 440, (40, 60, 90))
    a, b = 560, 440
    phase = [rng.uniform(0, 6.28) for _ in range(3)]

    def wobble(t):
        return 1 + 0.05 * np.sin(3 * t + phase[0]) + 0.035 * np.sin(5 * t + phase[1]) + 0.02 * np.sin(2 * t + phase[2])

    def field(u, v, r):
        h, w = u.shape
        base = np.zeros((h, w, 3), np.float32) + np.array([16, 20, 34], np.float32)
        # Broad flashes of colour, strongest in the middle of the stone.
        hues = [(30, 200, 110), (40, 110, 250), (250, 120, 30), (60, 230, 210), (220, 40, 80)]
        centre = np.clip(1.15 - r, 0, 1)[..., None]
        for hue in hues:
            n = noise_field((h // 5, w // 5), rng, 22, octaves=3)
            n = np.array(Image.fromarray((n * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
            patch = np.clip((n - 0.55) * 4.0, 0, 1)[..., None] * centre
            base = base * (1 - patch * 0.9) + np.array(hue, np.float32) * patch * 0.9
        return base

    dome(img, cx, cy, a, b, field, spec=0.75, wobble=wobble, gloss=70, ambient=0.6)
    return img


def citrine_lot(rng):
    img = background()
    pal_options = [
        Palette((236, 168, 40), (150, 88, 10), (255, 222, 125)),
        Palette((226, 150, 30), (130, 70, 8), (255, 210, 110)),
        Palette((242, 190, 70), (160, 110, 20), (255, 236, 160)),
    ]
    spots = [(820, 820), (1380, 760), (1700, 1150), (1150, 1250), (650, 1350), (1500, 1550), (980, 1700), (1800, 1700)]
    for x, y in spots:
        rad = rng.uniform(170, 250)
        soft_ellipse(img, (x - rad * 0.9, y + rad * 0.45, x + rad * 1.0, y + rad * 1.05), (70, 52, 34), 0.28, rad * 0.12)
        soft_ellipse(img, (x - rad * 0.5, y + rad * 0.4, x + rad * 0.8, y + rad * 1.0), (240, 170, 40), 0.18, rad * 0.2)
    for x, y in spots:
        rad = rng.uniform(170, 250)
        pal = rng.choice(pal_options)
        k = rng.randint(6, 9)
        angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(k))
        poly = [(x + math.cos(t) * rad * rng.uniform(0.75, 1.1), y + math.sin(t) * rad * rng.uniform(0.7, 1.0)) for t in angles]
        ix, iy = x + rng.uniform(-rad * 0.2, rad * 0.2), y + rng.uniform(-rad * 0.25, rad * 0.1)
        for i in range(k):
            tri = [(ix, iy), poly[i], poly[(i + 1) % k]]
            mx = (poly[i][0] + poly[(i + 1) % k][0]) / 2 - x
            my = (poly[i][1] + poly[(i + 1) % k][1]) / 2 - y
            u = np.array([mx, my]) / (math.hypot(mx, my) or 1)
            level = 0.6 + 0.35 * float(u @ LIGHT) + rng.uniform(-0.15, 0.15)
            gradient_poly(img, tri, pal.at(level + 0.15), pal.at(level - 0.15), (ix, iy), tri[1])
        edges(img, [poly], color=pal.light, alpha=140, width=4)
        sparkle(img, ix - rad * 0.2, iy - rad * 0.2, rad * 0.16, alpha=0.8)
    return img


def amethyst_point(rng):
    img = background()
    cx, cy = R / 2, R * 0.52
    d = np.array([math.cos(math.radians(-62)), math.sin(math.radians(-62))])
    p = np.array([-d[1], d[0]])
    width, body, tip = 520, 820, 420
    base = np.array([cx, cy]) - d * (body / 2 + tip / 3)
    top = base + d * body
    apex = top + d * tip
    soft_ellipse(img, (cx - 520, cy + 320, cx + 560, cy + 560), (70, 52, 34), 0.3, 60)
    soft_ellipse(img, (cx - 300, cy + 280, cx + 420, cy + 520), (150, 90, 200), 0.18, 80)
    offsets = [-width / 2, -width / 5, width / 5, width / 2]
    face_levels = [0.42, 0.7, 0.98]
    pal_body = Palette((140, 80, 188), (58, 22, 96), (208, 168, 246))
    for k in range(3):
        o0, o1 = offsets[k], offsets[k + 1]
        quad = [tuple(base + p * o0), tuple(base + p * o1), tuple(top + p * o1), tuple(top + p * o0)]
        lvl = face_levels[k]
        gradient_poly(img, quad, pal_body.at(lvl + 0.2), pal_body.at(lvl - 0.15), tuple(base), tuple(top))
        # growth lines across the prism faces
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        dr = ImageDraw.Draw(layer)
        for s in range(14):
            f = rng.uniform(0.05, 0.95)
            a_pt = base + d * body * f + p * o0
            b_pt = base + d * body * f + p * o1
            dr.line([tuple(a_pt), tuple(b_pt)], fill=(255, 255, 255, rng.randint(14, 34)), width=3)
        img.alpha_composite(layer)
        tri = [tuple(top + p * o0), tuple(top + p * o1), tuple(apex)]
        gradient_poly(img, tri, pal_body.at(lvl + 0.25), pal_body.at(lvl - 0.25), tuple(top), tuple(apex))
    # rough white base where it was broken from the cluster
    jag = [tuple(base + p * offsets[0])]
    for i in range(9):
        f = (i + 1) / 10
        jag.append(tuple(base + p * (offsets[0] + (offsets[-1] - offsets[0]) * f) - d * rng.uniform(20, 110)))
    jag.append(tuple(base + p * offsets[-1]))
    gradient_poly(img, jag, (236, 228, 240), (190, 176, 205), tuple(base - d * 100), tuple(base))
    outline = [tuple(base + p * offsets[0]), tuple(top + p * offsets[0]), tuple(apex), tuple(top + p * offsets[-1]), tuple(base + p * offsets[-1])]
    edges(img, [outline], color=(235, 215, 255), alpha=150, width=5)
    sparkle(img, *(top + p * offsets[2] * 0.6 + d * 80), 120)
    sparkle(img, *(base + d * body * 0.4 + p * offsets[1] * 0.2), 70, alpha=0.6)
    return img


def moonstone(rng):
    img = background()
    cx, cy = CENTER
    a, b = 500, 400
    ground(img, cx, cy, a, b, (150, 170, 220))

    def field(u, v, r):
        h, w = u.shape
        base = np.zeros((h, w, 3), np.float32) + np.array([236, 236, 240], np.float32)
        cloud = noise_field((h // 4, w // 4), rng, 20)
        cloud = np.array(Image.fromarray((cloud * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32)[..., None] / 255
        base = base * (0.9 + 0.1 * cloud)
        band = np.exp(-(((v + 0.15 - 0.25 * u) / 0.32) ** 2))[..., None]
        sheen = np.array([95, 150, 255], np.float32)
        return base * (1 - band * 0.75) + sheen * band * 0.75

    dome(img, cx, cy, a, b, field, spec=0.6, gloss=30, ambient=0.82)
    return img


def garnet_pack(rng):
    img = background()
    pal = Palette((150, 14, 32), (48, 0, 10), (232, 84, 96))
    spots = [(620, 980), (1200, 860), (1780, 980), (880, 1500), (1520, 1500)]
    for x, y in spots:
        ground(img, x, y, 230, 230, (190, 30, 50))
    for x, y in spots:
        brilliant(img, x, y, 230, 230, "round", pal, rng, m=8)
    return img


def peridot(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((128, 168, 38), (48, 78, 8), (202, 232, 112))
    ground(img, cx, cy, 480, 480, (140, 180, 40))
    brilliant(img, cx, cy, 480, 480, "round", pal, rng)
    return img


def smoky_quartz(rng):
    img = background()
    cx, cy = CENTER[0], CENTER[1] + 20
    pal = Palette((132, 92, 56), (48, 28, 14), (206, 166, 124))
    ground(img, cx, cy, 440, 600, (140, 100, 60))
    brilliant(img, cx, cy, 640, 440, "pear", pal, rng, m=8, table=0.5)
    return img


def labradorite(rng):
    img = background()
    cx, cy = CENTER
    k = 48
    bumps = [rng.uniform(0, 6.28) for _ in range(3)]
    poly = []
    for i in range(k):
        t = 2 * math.pi * i / k
        r = 1 + 0.06 * math.sin(2 * t + bumps[0]) + 0.04 * math.sin(3 * t + bumps[1]) + 0.025 * math.sin(5 * t + bumps[2])
        poly.append((cx + math.cos(t) * 600 * r, cy + math.sin(t) * 450 * r))
    soft_ellipse(img, (cx - 640, cy + 220, cx + 680, cy + 560), (70, 52, 34), 0.32, 60)
    x0, y0, x1, y1 = poly_bbox(poly)
    w, h = x1 - x0, y1 - y0
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in poly], fill=255)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.zeros((h, w, 3), np.float32) + np.array([58, 64, 66], np.float32)
    streaks = noise_field((h // 4, w // 4), rng, 18)
    streaks = np.array(Image.fromarray((streaks * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
    base *= (0.75 + 0.45 * streaks)[..., None]
    for hue, cut in (((40, 120, 235), 0.55), ((40, 200, 200), 0.65), ((230, 190, 60), 0.75)):
        n = noise_field((h // 4, w // 4), rng, 14)
        n = np.array(Image.fromarray((n * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
        band = np.clip(1 - np.abs((ys / h) - (xs / w) * 0.6 - 0.2) * 1.8, 0, 1)
        patch = (np.clip((n - cut) * 4, 0, 1) * band)[..., None]
        base = base * (1 - patch * 0.8) + np.array(hue, np.float32) * patch * 0.8
    sheen = np.clip(1 - np.abs((xs / w + ys / h) - 0.7) * 3, 0, 1)[..., None] * 60
    col = np.clip(base + sheen, 0, 255)
    layer = Image.fromarray(col.astype(np.uint8), "RGB").convert("RGBA")
    layer.putalpha(mask)
    img.alpha_composite(layer, dest=(x0, y0))
    edges(img, [poly], color=(205, 210, 212), alpha=200, width=8)
    return img


def blue_zircon(rng):
    img = background()
    cx, cy = CENTER
    pal = Palette((40, 168, 222), (0, 68, 120), (165, 232, 255))
    ground(img, cx, cy, 480, 480, (50, 170, 230))
    brilliant(img, cx, cy, 480, 480, "round", pal, rng, fire=0.22)
    return img


def rose_quartz(rng):
    img = background()
    cx, cy = CENTER
    rad = 520
    ground(img, cx, cy, rad, rad, (240, 170, 185))

    def field(u, v, r):
        h, w = u.shape
        cloud = noise_field((h // 4, w // 4), rng, 16)
        cloud = np.array(Image.fromarray((cloud * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32)[..., None] / 255
        base = np.array([246, 190, 204], np.float32) * (0.93 + 0.1 * cloud)
        return base

    dome(img, cx, cy, rad, rad, field, spec=0.9, gloss=60, ambient=0.78)
    return img


def turquoise(rng):
    img = background()
    cx, cy = CENTER
    a, b = 520, 400
    ground(img, cx, cy, a, b, (80, 180, 175))

    def field(u, v, r):
        h, w = u.shape
        base = np.zeros((h, w, 3), np.float32) + np.array([96, 196, 196], np.float32)
        tone = noise_field((h // 4, w // 4), rng, 10)
        tone = np.array(Image.fromarray((tone * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32)[..., None] / 255
        base *= 0.92 + 0.14 * tone
        # Spiderweb matrix: thin lines along the contours of a noise field.
        web = noise_field((h // 3, w // 3), rng, 26, octaves=2)
        web = np.array(Image.fromarray((web * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
        veins = np.exp(-(((web - 0.5) / 0.012) ** 2))
        veins += 0.7 * np.exp(-(((web - 0.3) / 0.01) ** 2))
        veins = np.clip(veins, 0, 1)[..., None]
        matrix = np.array([120, 92, 60], np.float32)
        return base * (1 - veins * 0.8) + matrix * veins * 0.8

    dome(img, cx, cy, a, b, field, spec=0.6, gloss=25, ambient=0.7)
    return img


STONES = {
    "ceylon-blue-sapphire": sapphire,
    "colombian-emerald": emerald,
    "burmese-ruby": ruby,
    "paraiba-tourmaline": paraiba,
    "padparadscha-sapphire": padparadscha,
    "tanzanite": tanzanite,
    "vivid-pink-spinel": spinel,
    "santa-maria-aquamarine": aquamarine,
    "alexandrite": alexandrite,
    "black-opal": black_opal,
    "citrine-cluster-lot": citrine_lot,
    "amethyst-point": amethyst_point,
    "rainbow-moonstone": moonstone,
    "garnet-melee-5-pack": garnet_pack,
    "peridot": peridot,
    "smoky-quartz": smoky_quartz,
    "labradorite-slab": labradorite,
    "blue-zircon": blue_zircon,
    "rose-quartz-sphere": rose_quartz,
    "turquoise-cabochon": turquoise,
}


if __name__ == "__main__":
    import sys

    only = set(sys.argv[1:])
    for i, (name, draw) in enumerate(STONES.items()):
        if only and name not in only:
            continue
        img = draw(random.Random(1000 + i))
        finish(img, OUT_DIR / f"{name}.webp")
        print("drew", name)
