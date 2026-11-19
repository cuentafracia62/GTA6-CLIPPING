"""Miniatura 1280x720 para videos largos: imagen IA + texto grande legible + acento de color."""
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .config import ASSETS

ACENTOS = [(255, 62, 154), (255, 159, 67), (90, 220, 255)]  # rosa neón, naranja atardecer, cian
SELLOS = {"confirmed": ("CONFIRMED", (40, 180, 80)), "reported": ("REPORTED", (240, 160, 0)),
          "rumor": ("RUMOR", (224, 48, 48))}


def _fuente(tam):
    for nombre in ("Anton-Regular.ttf", "BebasNeue-Regular.ttf"):
        ruta = ASSETS / "fonts" / nombre
        if ruta.exists():
            return ImageFont.truetype(str(ruta), tam)
    return ImageFont.load_default(tam)


def _envolver(texto, fuente, ancho, dibujo):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if dibujo.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def crear(imagen, texto, salida, sello=None):
    img = Image.open(imagen).convert("RGB")
    # Recorta la franja de abajo (posible marca de agua) y ajusta a 16:9
    img = img.crop((0, 0, img.width, int(img.height * 0.93)))
    ratio = 1280 / 720
    if img.width / img.height > ratio:
        nuevo = int(img.height * ratio)
        x = (img.width - nuevo) // 2
        img = img.crop((x, 0, x + nuevo, img.height))
    else:
        nuevo = int(img.width / ratio)
        img = img.crop((0, 0, img.width, nuevo))
    img = img.resize((1280, 720), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Brightness(img).enhance(0.85)

    # Degradado oscuro a la izquierda para que el texto se lea
    sombra = Image.new("L", (1280, 720))
    d = ImageDraw.Draw(sombra)
    for x in range(1280):
        d.line([(x, 0), (x, 720)], fill=int(max(0, 210 - x * 0.28)))
    negro = Image.new("RGB", (1280, 720), (0, 0, 0))
    img = Image.composite(negro, img, sombra.filter(ImageFilter.GaussianBlur(20)))

    dibujo = ImageDraw.Draw(img)
    texto = (texto or "").upper().strip() or "GTA 6"
    acento = random.choice(ACENTOS)
    tam = 150
    while tam > 70:
        fuente = _fuente(tam)
        lineas = _envolver(texto, fuente, 700, dibujo)
        if len(lineas) <= 3:
            break
        tam -= 10
    cajas = [dibujo.textbbox((0, 0), ln, font=fuente, stroke_width=8) for ln in lineas]
    altos = [c[3] - c[1] for c in cajas]
    sep = int(tam * 0.12)
    y = (720 - (sum(altos) + sep * (len(lineas) - 1) + 40)) // 2
    for i, (linea, caja, alto) in enumerate(zip(lineas, cajas, altos)):
        color = acento if i == len(lineas) - 1 else (255, 255, 255)
        dibujo.text((60, y - caja[1]), linea, font=fuente, fill=color, stroke_width=8, stroke_fill=(0, 0, 0))
        y += alto + sep
    dibujo.rectangle([(64, y + 6), (64 + 180, y + 20)], fill=acento)
    if sello in SELLOS:  # etiqueta en la esquina: la marca del canal
        palabra, color = SELLOS[sello]
        f = _fuente(54)
        caja = dibujo.textbbox((0, 0), palabra, font=f)
        ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
        x0, y0 = 1280 - ancho - 70, 40
        dibujo.rectangle([(x0 - 18, y0 - 10), (x0 + ancho + 18, y0 + alto + 22)], fill=color)
        dibujo.text((x0, y0 - caja[1] + 4), palabra, font=f, fill=(255, 255, 255))
    img.save(salida, "JPEG", quality=92)
    return salida
