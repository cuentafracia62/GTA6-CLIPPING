"""Ajustes del canal. Las claves NUNCA van aquí: se leen de variables de entorno (GitHub Secrets)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"
ASSETS = ROOT / "assets"
DOCS = ROOT / "docs"

CANAL = os.getenv("CANAL_NOMBRE", "Leonida Report")
IDIOMA = "en"

# ---------- IA de texto (se usa la primera que tenga clave) ----------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODELO = os.getenv("CLAUDE_MODELO", "claude-opus-5-5")
CLAUDE_ESFUERZO = os.getenv("CLAUDE_ESFUERZO", "medium")       # low | medium | high
CLAUDE_VERIFICAR = os.getenv("CLAUDE_VERIFICAR", "1") == "1"   # verificación con búsqueda web
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Si ninguno existe para tu clave, ia.py busca solo el modelo "flash" más nuevo disponible
GEMINI_MODELOS = [m.strip() for m in (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash,gemini-flash-latest").split(",")
                  if m.strip()]
POLLINATIONS_TOKEN = os.getenv("POLLINATIONS_TOKEN", "").strip()
# Pollinations escribe peor e inventa datos: por defecto NO se publica un guion escrito solo por él
PUBLICAR_CON_RESPALDO = os.getenv("PUBLICAR_CON_RESPALDO", "0") == "1"

# Precios por millón de tokens (entrada, salida) para calcular el costo real de cada video
PRECIOS = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
PRECIO_BUSQUEDA_WEB = 0.01  # ≈ $10 por 1,000 búsquedas

# ---------- Voz ----------
VOZ = os.getenv("VOZ", "en-US-ChristopherNeural")
# Si la voz principal no responde, se rehace toda la narración con la siguiente de esta lista
VOZ_RESPALDO = [v.strip() for v in os.getenv("VOZ_RESPALDO", "en-US-GuyNeural,en-US-EricNeural").split(",") if v.strip()]
VOZ_RATE = os.getenv("VOZ_RATE", "+6%")
VOZ_PITCH = os.getenv("VOZ_PITCH", "+0Hz")
VOZ_RATE_LARGO = os.getenv("VOZ_RATE_LARGO", "+0%")

# ---------- Visuales ----------
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()   # alternativa gratis a Pexels
IMG_MODELO = os.getenv("IMG_MODELO", "flux")
# Las imágenes IA son ILUSTRACIONES (nunca se hacen pasar por capturas del juego)
ESTILO_BASE = ("stylized illustration, clearly not a video game screenshot, no text, no letters, no watermark, "
               "no logo, no weapons, no violence, no real people")
# Carpeta con TU gameplay grabado (o material con permiso). Ver assets/footage/LEEME.md
FOOTAGE_PROPIO = ASSETS / "footage"

# ---------- Video ----------
FPS = 30
PAUSA_ESCENA = 0.30
VOLUMEN_MUSICA = float(os.getenv("VOLUMEN_MUSICA", "0.22"))

# ---------- Publicación ----------
PRIVACIDAD = os.getenv("YT_PRIVACIDAD", "public")       # public | unlisted | private
CATEGORIA_YT = os.getenv("YT_CATEGORIA", "20")          # 20 = Videojuegos
# Máximo de shorts automáticos por día de cuota de YouTube (el día de la cuota va de medianoche a medianoche,
# hora del Pacífico). Con 4 shorts + 1 largo diario quedan 5 de las 6 subidas posibles: 1 de reserva.
LIMITE_SHORTS_DIA = int(os.getenv("LIMITE_SHORTS_DIA", "4"))
# Si se define (p. ej. "10:00,13:00"), los videos se suben privados y YouTube los publica solo a esa hora
# (zona ZONA_HORARIA; por defecto Nueva York, porque el público es de habla inglesa)
HORA_PUBLICACION = os.getenv("YT_HORA_PUBLICACION", "")
ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/New_York")
# Modo revisión. Por defecto NO (canal 100 % automático desde 2026-11-19): cada video se programa y se publica
# solo. Ponlo en "1" si quieres volver a revisar todo antes de publicar (se sube PRIVADO).
MODO_REVISION = os.getenv("MODO_REVISION", "0") == "1"
# Candado del modo automático: una NOTICIA que no pasó la verificación con búsqueda web se sube PRIVADA
# (para que la revises) en vez de publicarse sola. Los temas atemporales sí se publican.
NOTICIA_SIN_VERIFICAR_PRIVADA = os.getenv("NOTICIA_SIN_VERIFICAR_PRIVADA", "1") == "1"

# Noticias: feeds RSS públicos de medios de videojuegos (solo se toman los artículos que hablan de GTA 6)
FEEDS = [x.strip() for x in os.getenv("FEEDS", ",".join([
    "https://www.ign.com/rss/articles/feed",
    "https://www.gamesradar.com/feeds/all/",
    "https://www.pcgamer.com/rss/",
    "https://www.eurogamer.net/feed",
    "https://www.videogameschronicle.com/feed/",
    "https://kotaku.com/feed",
    "https://www.polygon.com/rss/index.xml",
    "https://www.gamespot.com/feeds/mashup/",
    "https://www.dexerto.com/gta/feed/",
])).split(",") if x.strip()]
DIAS_NOTICIAS = int(os.getenv("DIAS_NOTICIAS", "3"))
# Probabilidad de hacer un tema "atemporal" (historia de la saga, análisis) en vez de noticia del día
PROB_ATEMPORAL = float(os.getenv("PROB_ATEMPORAL", "0.3"))
USER_AGENT = "Mozilla/5.0 (compatible; LeonidaReportBot/1.0)"
