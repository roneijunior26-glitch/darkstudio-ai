"""Compoe a capa estilo YouTube (1280x720) com Pillow: titulo grande com palavra em destaque, sublinhado vermelho,
rotulos vermelhos com seta e 'VS'. O fundo vem do FLUX; todo o texto e desenhado aqui (modelos de imagem erram letras)."""
from __future__ import annotations

import io
import math

W, H = 1280, 720
FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
FONT_BOLD_OBL = FONT_DIR + "DejaVuSansCondensed-BoldOblique.ttf"
YELLOW, RED, WHITE, BLACK = (255, 214, 10), (225, 20, 20), (255, 255, 255), (0, 0, 0)


def _font(size: int):
    from PIL import ImageFont
    return ImageFont.truetype(FONT_BOLD_OBL, size)


def _fit(text: str, max_w: int, start: int, floor: int = 40) -> int:
    f = _font(start)
    size = start
    while size > floor and f.getlength(text) > max_w:
        size -= 4
        f = _font(size)
    return size


def _text(d, xy, text, font, fill, stroke=8):
    x, y = xy
    d.text((x + 5, y + 7), text, font=font, fill=(0, 0, 0, 160), stroke_width=stroke, stroke_fill=(0, 0, 0, 160))  # sombra
    d.text((x, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=BLACK)


def _background(img_bytes: bytes):
    from PIL import Image, ImageEnhance, ImageDraw, ImageFilter
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((math.ceil(im.width * scale), math.ceil(im.height * scale)), Image.LANCZOS)
    l, t = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((l, t, l + W, t + H))
    im = ImageEnhance.Color(im).enhance(1.35)
    im = ImageEnhance.Contrast(im).enhance(1.15)
    im = ImageEnhance.Sharpness(im).enhance(1.4)
    # vinheta + faixa escura no topo para o titulo
    v = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(v)
    vd.ellipse((-W * 0.25, -H * 0.35, W * 1.25, H * 1.35), fill=255)
    v = v.filter(ImageFilter.GaussianBlur(120))
    im = Image.composite(im, Image.new("RGB", (W, H), (0, 0, 0)), v.point(lambda p: 90 + p * 165 // 255))
    top = Image.new("L", (W, H), 0)
    td = ImageDraw.Draw(top)
    for y in range(0, 300):
        td.line((0, y, W, y), fill=int(150 * (1 - y / 300)))
    return Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), im, top)


def _headline(base, lines: list[str], highlight: str | None) -> int:
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    sizes = [110, 150] if len(lines) == 2 else [140]
    y = 18
    for i, line in enumerate(lines):
        size = _fit(line, W - 90, sizes[min(i, len(sizes) - 1)])
        f = _font(size)
        words = line.split(" ")
        total = f.getlength(line)
        x = (W - total) / 2
        for wd in words:
            color = YELLOW if highlight and wd.strip("?!.,:;").upper() == highlight.upper() else WHITE
            _text(d, (x, y), wd, f, color, stroke=max(6, size // 14))
            x += f.getlength(wd + " ")
        y += int(size * 1.02)
    return y


def _underline(base, y: int):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    x0, x1 = 300, W - 300
    pts_top = [(x0 + (x1 - x0) * t / 20, y + 4 - 8 * math.sin(t / 20 * math.pi)) for t in range(21)]
    pts_bot = [(x0 + 40 + (x1 - x0 - 80) * t / 20, y + 4 + 16 * math.sin(t / 20 * math.pi) + 3) for t in range(20, -1, -1)]
    d.polygon(pts_top + pts_bot, fill=RED + (255,), outline=BLACK, width=3)


def _skew_box(base, x, y, w, h, color):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    sk = 26
    poly = [(x + sk, y), (x + w, y), (x + w - sk, y + h), (x, y + h)]
    d.polygon([(px + 6, py + 8) for px, py in poly], fill=(0, 0, 0, 150))
    d.polygon(poly, fill=color + (255,), outline=WHITE, width=5)
    return x + w / 2, y + h / 2


def _arrow(base, start, end, bend):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    (x0, y0), (x1, y1) = start, end
    cx, cy = (x0 + x1) / 2 + bend, (y0 + y1) / 2
    pts = [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1)
           for t in [i / 24 for i in range(25)]]
    ang = math.atan2(pts[-1][1] - pts[-4][1], pts[-1][0] - pts[-4][0])
    tip = pts[-1]
    head = [(tip[0] + 34 * math.cos(ang), tip[1] + 34 * math.sin(ang)),
            (tip[0] + 22 * math.cos(ang + 2.2), tip[1] + 22 * math.sin(ang + 2.2)),
            (tip[0] + 22 * math.cos(ang - 2.2), tip[1] + 22 * math.sin(ang - 2.2))]
    for width, col in ((24, WHITE), (14, RED)):
        d.line(pts, fill=col + (255,), width=width, joint="curve")
    d.polygon(head, fill=RED + (255,), outline=WHITE)


def _label(base, text: str, side: str, highlight: str | None):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    size = _fit(text, 400, 70, 36)
    f = _font(size)
    tw = f.getlength(text)
    bw, bh = int(tw + 90), int(size * 1.55)
    x = 40 if side == "left" else W - bw - 40
    y = H - bh - 40
    cx, cy = _skew_box(base, x, y, bw, bh, RED)
    tx = x + 45
    for wd in text.split(" "):
        col = YELLOW if highlight and wd.strip("?!.,").upper() == highlight.upper() else WHITE
        _text(d, (tx, cy - size * 0.62), wd, f, col, stroke=max(4, size // 16))
        tx += f.getlength(wd + " ")
    ax = x + bw * (0.22 if side == "left" else 0.78)
    _arrow(base, (ax, y - 6), (ax + (30 if side == "left" else -30), y - 150), -45 if side == "left" else 45)


def compose(bg_bytes: bytes, spec: dict) -> bytes:
    """spec: headline (1-2 linhas), highlight (palavra), labels [{text, side}], vs (bool)."""
    from PIL import ImageDraw
    base = _background(bg_bytes)
    y = _headline(base, spec["headline"], spec.get("highlight"))
    _underline(base, y + 2)
    if spec.get("vs"):
        d = ImageDraw.Draw(base, "RGBA")
        f = _font(190)
        tw = f.getlength("VS")
        _text(d, ((W - tw) / 2, H / 2 - 40), "VS", f, WHITE, stroke=14)
    for lb in spec.get("labels", []):
        _label(base, lb["text"], lb["side"], spec.get("highlight_label"))
    out = io.BytesIO()
    base.save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()
