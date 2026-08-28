#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CV Studio — génère le favicon et l'image Open Graph depuis la charte.

    python3 tools/make-icons.py

Produit dans assets/ : favicon.svg, favicon-32.png, favicon-180.png,
favicon.ico et og.png (1200x630, utilisée par WhatsApp / LinkedIn / X).
Ne dépend que de Pillow. Régénérez après tout changement de couleurs.
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")

BRAND = (99, 102, 241)      # --brand   #6366f1
BRAND2 = (139, 92, 246)     # --brand-2 #8b5cf6
INK = (31, 37, 51)          # --text    #1f2533
ACCENT = (37, 99, 235)      # --accent  #2563eb (modèle « Moderne »)

FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial.ttf"]


def font(size, bold=True):
    path = FONTS[0] if bold else FONTS[1]
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def gradient(size, c1, c2, diagonal=True):
    """Dégradé linéaire (135° si diagonal, sinon vertical)."""
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = ((x / max(w - 1, 1)) + (y / max(h - 1, 1))) / 2 if diagonal else y / max(h - 1, 1)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return img


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def centered(draw, box, text, fnt, fill):
    """Écrit `text` centré dans `box` = (x0, y0, x1, y1)."""
    l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
    x = box[0] + (box[2] - box[0] - (r - l)) / 2 - l
    y = box[1] + (box[3] - box[1] - (b - t)) / 2 - t
    draw.text((x, y), text, font=fnt, fill=fill)


# ------------------------------------------------------------------ favicon
def make_favicon(px):
    """Carré arrondi dégradé + « CV » blanc — le même mark que la navigation."""
    scale = 4                                    # rendu 4x puis réduction = bords lisses
    s = px * scale
    img = gradient((s, s), BRAND, BRAND2)
    img.putalpha(rounded_mask((s, s), int(s * 0.22)))
    d = ImageDraw.Draw(img)
    centered(d, (0, 0, s, s), "CV", font(int(s * 0.46)), (255, 255, 255, 255))
    return img.resize((px, px), Image.LANCZOS)


def make_favicon_svg():
    """Version vectorielle : nette à toute taille, et suit le thème du navigateur."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="CV Studio">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#{BRAND[0]:02x}{BRAND[1]:02x}{BRAND[2]:02x}"/>
      <stop offset="1" stop-color="#{BRAND2[0]:02x}{BRAND2[1]:02x}{BRAND2[2]:02x}"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <text x="32" y="33" text-anchor="middle" dominant-baseline="central"
        font-family="Inter,Helvetica,Arial,sans-serif" font-size="29" font-weight="800"
        fill="#fff" letter-spacing="-1">CV</text>
</svg>
'''


# ----------------------------------------------------------------------- OG
def make_og():
    """1200x630 : promesse à gauche, aperçu d'un CV à droite (ce que le produit fait)."""
    W, H = 1200, 630
    img = gradient((W, H), (79, 70, 229), (124, 58, 237))
    d = ImageDraw.Draw(img, "RGBA")

    # halo diffus pour éviter un aplat plat
    d.ellipse([-160, 300, 420, 880], fill=(255, 255, 255, 18))
    d.ellipse([820, -220, 1360, 320], fill=(255, 255, 255, 22))

    # --- marque
    mark = make_favicon(52)
    img.paste(mark, (72, 62), mark)
    d.text((140, 74), "CV Studio", font=font(30), fill=(255, 255, 255, 240))

    # --- promesse
    d.text((72, 178), "Créez un CV", font=font(62), fill="white")
    d.text((72, 250), "professionnel et", font=font(62), fill="white")
    d.text((72, 322), "optimisé ATS", font=font(62), fill=(252, 211, 77))
    d.text((72, 418), "En moins de 10 minutes, dans votre navigateur.",
           font=font(25, bold=False), fill=(233, 230, 255))

    # --- bandeau de réassurance (coche tracée : aucune police n'a le glyphe ✓)
    x, y = 72, 492
    for label in ("Gratuit", "Sans inscription", "Export PDF"):
        tw = d.textbbox((0, 0), label, font=font(21))[2]
        w = tw + 66
        d.rounded_rectangle([x, y, x + w, y + 48], radius=24, fill=(255, 255, 255, 40))
        d.line([(x + 22, y + 25), (x + 29, y + 32), (x + 42, y + 17)],
               fill="white", width=4, joint="curve")
        d.text((x + 52, y + 12), label, font=font(21), fill="white")
        x += w + 16

    # --- aperçu de CV (feuille A4 avec barre latérale, modèle « Moderne »)
    sx, sy, sw, sh = 760, 118, 350, 462
    d.rounded_rectangle([sx + 10, sy + 16, sx + sw + 10, sy + sh + 16], radius=12, fill=(23, 16, 60, 70))
    d.rounded_rectangle([sx, sy, sx + sw, sy + sh], radius=12, fill="white")
    d.rectangle([sx, sy + 12, sx + 108, sy + sh - 12], fill=(240, 244, 252))
    d.rounded_rectangle([sx, sy, sx + 12, sy + sh], radius=6, fill=ACCENT)
    d.ellipse([sx + 30, sy + 34, sx + 86, sy + 90], fill=(203, 213, 233))
    for i, w in enumerate((62, 74, 50, 68, 44, 70, 58)):      # colonne latérale
        d.rounded_rectangle([sx + 26, sy + 116 + i * 26, sx + 26 + w, sy + 124 + i * 26],
                            radius=4, fill=(206, 215, 232))
    d.rounded_rectangle([sx + 128, sy + 34, sx + 268, sy + 50], radius=5, fill=INK)
    d.rounded_rectangle([sx + 128, sy + 60, sx + 224, sy + 72], radius=4, fill=ACCENT)
    yy = sy + 100
    for block in (3, 4, 3):                                    # corps du CV
        d.rounded_rectangle([sx + 128, yy, sx + 196, yy + 11], radius=4, fill=ACCENT)
        yy += 26
        for _ in range(block):
            d.rounded_rectangle([sx + 128, yy, sx + 322, yy + 9], radius=4, fill=(219, 225, 238))
            yy += 18
        yy += 14
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "favicon.svg"), "w", encoding="utf-8").write(make_favicon_svg())
    make_favicon(32).save(os.path.join(OUT, "favicon-32.png"))
    make_favicon(180).save(os.path.join(OUT, "favicon-180.png"))   # apple-touch-icon
    make_favicon(512).save(os.path.join(OUT, "favicon-512.png"))   # PWA / Android
    make_favicon(64).save(os.path.join(OUT, "favicon.ico"),
                          sizes=[(16, 16), (32, 32), (48, 48)])
    make_og().save(os.path.join(OUT, "og.png"), optimize=True)
    print("assets/ : favicon.svg, favicon-32/180/512.png, favicon.ico, og.png")
