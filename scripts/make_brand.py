"""Render the integration icon/logo into custom_components/airwallet/brand/.

    .venv/bin/python scripts/make_brand.py
"""

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "airwallet" / "brand"
S = 2048  # draw at 2x and downsample for clean edges

TOP_LEFT = (18, 184, 178)  # teal
BOTTOM_RIGHT = (26, 74, 160)  # deep blue
WHITE = (255, 255, 255)
WATER = (120, 222, 236)
WATER_DEEP = (60, 170, 214)
ALERT = (255, 122, 89)


def gradient(size, c1, c2):
    """Diagonal gradient from top-left c1 to bottom-right c2."""
    small = Image.new("RGB", (256, 256))
    px = small.load()
    for y in range(256):
        for x in range(256):
            t = (x + y) / 510
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2, strict=True))
    return small.resize((size, size), Image.BICUBIC)


def rounded_mask(size, box, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=radius, fill=255)
    return m


def render() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Tile
    tile_box = (64, 64, S - 64, S - 64)
    img.paste(gradient(S, TOP_LEFT, BOTTOM_RIGHT), (0, 0), rounded_mask(S, tile_box, 440))

    # Soft shadow under the machine
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((470, 430, 1578, 1690), radius=170, fill=(8, 30, 70, 110))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(48)))

    d = ImageDraw.Draw(img)

    # Machine body
    body = (450, 380, 1598, 1640)
    d.rounded_rectangle(body, radius=170, fill=WHITE)

    # Control strip: divider, display pill, two knobs
    d.rounded_rectangle((450 + 70, 640, 1598 - 70, 652), radius=6, fill=(214, 228, 240))
    d.rounded_rectangle((560, 470, 900, 552), radius=41, fill=(214, 228, 240))
    for cx in (1150, 1270):
        d.ellipse((cx - 46, 465, cx + 46, 557), fill=(214, 228, 240))

    # Porthole
    cx, cy, r = 1024, 1140, 380
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(28, 92, 168))
    inner = r - 58
    window = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    wd = ImageDraw.Draw(window)
    wd.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=(232, 246, 252))

    # Water with a wave on top
    def wave_poly(level, amp, phase):
        pts = [(cx - inner - 10, cy + inner + 10)]
        for i in range(0, 101):
            x = cx - inner - 10 + (2 * inner + 20) * i / 100
            y = cy + level + amp * math.sin(i / 100 * 2 * math.pi * 1.5 + phase)
            pts.append((x, y))
        pts.append((cx + inner + 10, cy + inner + 10))
        return pts

    wd.polygon(wave_poly(-10, 34, 0.0), fill=WATER)
    wd.polygon(wave_poly(70, 30, 2.2), fill=WATER_DEEP)

    # Bubbles
    for bx, by, br in ((cx - 120, cy - 140, 38), (cx + 60, cy - 210, 24), (cx + 150, cy - 90, 30)):
        wd.ellipse((bx - br, by - br, bx + br, by + br), outline=WATER_DEEP, width=14)

    # Glass highlight
    wd.arc((cx - inner + 60, cy - inner + 60, cx + inner - 60, cy + inner - 60), 200, 250, fill=WHITE, width=26)

    clip = Image.new("L", (S, S), 0)
    ImageDraw.Draw(clip).ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=255)
    window.putalpha(ImageChops.multiply(window.getchannel("A"), clip))
    img.alpha_composite(window)

    # Alert dot (the "your wash is done" ping), with a ring in the tile colour
    ax, ay, ar = 1560, 420, 170
    d.ellipse((ax - ar - 34, ay - ar - 34, ax + ar + 34, ay + ar + 34), fill=(22, 128, 170))
    d.ellipse((ax - ar, ay - ar, ax + ar, ay + ar), fill=ALERT)
    d.line((ax - 70, ay + 4, ax - 18, ay + 58), fill=WHITE, width=40, joint="curve")
    d.line((ax - 18, ay + 58, ax + 80, ay - 56), fill=WHITE, width=40, joint="curve")
    for px, py in ((ax - 70, ay + 4), (ax - 18, ay + 58), (ax + 80, ay - 56)):
        d.ellipse((px - 20, py - 20, px + 20, py + 20), fill=WHITE)

    return img.resize((1024, 1024), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon = render()
    for name, size in (("icon.png", 256), ("icon@2x.png", 512), ("logo.png", 256), ("logo@2x.png", 512)):
        icon.resize((size, size), Image.LANCZOS).save(OUT / name, optimize=True)
    print("written to", OUT)


if __name__ == "__main__":
    main()
