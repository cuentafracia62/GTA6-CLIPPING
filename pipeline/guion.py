"""Guiones en inglés para shorts y videos largos de Leonida Report (GTA 6).

Proceso: borrador → editor (inglés natural, ritmo, fidelidad a las fuentes) → verificación de datos
(Claude + búsqueda web, si hay clave). El editor y el verificador devuelven solo correcciones.

Cada escena lleva una etiqueta que se ve en pantalla:
  confirmed (oficial / varias fuentes) · reported (un medio) · rumor · opinion (análisis del canal)
"""
import json
import random
import re

from . import db, ia
from .config import ANTHROPIC_API_KEY, CANAL, CLAUDE_VERIFICAR, DATA

TIPOS = ("confirmed", "reported", "rumor", "opinion")

ESTRUCTURAS_SHORT = {
    "fact_check": "Open with the claim people are repeating, then split it into what's confirmed and what isn't.",
    "why_it_matters": "Open with the news in one punchy line, then explain why it matters to players.",
    "question": "Open with a direct question to the viewer that the story answers.",
    "three_things": "Organize it as three things to know, from least to most surprising.",
    "before_after": "Contrast how things were before this news and what changes now.",
}

REGLAS_COMUNES = """TRUTH RULES (mandatory)
- Use ONLY facts that appear in the SOURCES. Never invent dates, names, numbers, prices, quotes or features.
- Every scene has a "tipo": "confirmed" (official or multiple sources), "reported" (one outlet, unconfirmed),
  "rumor" (leaks, insiders, social media) or "opinion" (the channel's own analysis). Never present a rumor or an
  opinion as fact; say it out loud ("reports say…", "this is a rumor…", "my take…").
- Never put a quote in someone's mouth unless the SOURCES contain it word for word. Keep quotes under 15 words.
- Attribute every claim to the RIGHT person or outlet (e.g. a Digital Foundry analyst is not a Rockstar spokesperson).
- No story spoilers (missions, twists, ending). No leaked content. No piracy. No graphic violence descriptions.
- Don't attack or mock real people; streamers and journalists are named only for what the sources say they did.
- The FIRST scene must be clean: no violence, no weapons, no shock imagery (YouTube monetization rule).
- Natural, conversational American English for an international audience. Short sentences. No emojis, no markdown.

VISUALS (per scene)
- "imagen": prompt IN ENGLISH, 20-40 words, for a STYLIZED ILLUSTRATION (never a fake game screenshot): neon
  coastal city, palm trees at sunset, highways, beaches, swamps, retro synthwave graphics, abstract shapes.
  No characters from the game, no logos, no real people's faces, no weapons, no text.
- "stock": 2-4 words to search a real stock clip (e.g. "miami beach drone", "florida highway night",
  "neon city street", "gaming controller closeup", "everglades airboat").
- "pantalla": 0-5 words of on-screen text that adds info (a number, date, price, or "OFFICIAL"), or "".
"""


def _aprendizajes(formato):
    a = db.leer(db.APRENDIZAJES, {})
    partes = []
    if a.get("titulos_top", {}).get(formato):
        partes.append("Best-performing titles on this channel: " + " | ".join(a["titulos_top"][formato][:5]))
    if a.get("consejos"):
        partes.append("Notes from the stats analysis: " + " ".join(a["consejos"][:4]))
    return ("\nWHAT WORKS ON THIS CHANNEL (use as guidance, don't copy):\n" + "\n".join(partes) + "\n") if partes else ""


def guia_contenido():
    """Guía de estilo editable en data/guia_contenido.md."""
    try:
        return (DATA / "guia_contenido.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


_RAROS = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)


def limpiar(s):
    s = (s or "").translate(_RAROS).replace("*", "").replace("_", " ").replace("#", "")
    return re.sub(r"\s+", " ", s).strip()


def corto(texto, max_palabras):
    palabras = limpiar(texto).upper().split()[:max_palabras]
    vacias = {"OF", "THE", "A", "AN", "AND", "TO", "IN", "ON", "FOR", "WITH", "IS", "AT", "BY", "ALL", "YOU'LL",
              "YOU’LL", "YOU'RE", "YOU’RE", "IT'S", "IT’S", "WILL", "CAN", "WHAT", "THAT", "YOUR", "MY", "BUT"}
    while len(palabras) > 1 and palabras[-1].strip(",.;:") in vacias:
        palabras.pop()
    return " ".join(palabras).rstrip(",.;:")


def _palabras(escenas):
    return sum(len(e["narracion"].split()) for e in escenas)


def _normalizar(g, min_esc, max_esc, min_pal, max_pal):
    escenas = [e for e in (g.get("escenas") or []) if isinstance(e, dict)]
    for e in escenas:
        e["narracion"] = limpiar(e.get("narracion"))
        e["imagen"] = limpiar(e.get("imagen"))
        e["stock"] = limpiar(e.get("stock")) or "miami skyline night"
        e["pantalla"] = corto(e.get("pantalla") or "", 5)
        if not re.search(r"[A-Za-z0-9]", e["pantalla"]):  # descarta "-", "…" y similares
            e["pantalla"] = ""
        e["tipo"] = e.get("tipo") if e.get("tipo") in TIPOS else "reported"
        if not e["narracion"] or not e["imagen"]:
            raise ValueError("escena incompleta")
    if not (min_esc <= len(escenas) <= max_esc):
        raise ValueError(f"{len(escenas)} escenas (esperaba {min_esc}-{max_esc})")
    p = _palabras(escenas)
    if not (min_pal <= p <= max_pal):
        raise ValueError(f"{p} palabras (esperaba {min_pal}-{max_pal})")
    g["escenas"] = escenas
    for k in ("titulo", "descripcion"):
        if not g.get(k):
            raise ValueError(f"falta {k}")
        g[k] = limpiar(g[k]) if k == "titulo" else g[k].strip()
    g["gancho_pantalla"] = corto(g.get("gancho_pantalla"), 5)
    g["texto_miniatura"] = corto(g.get("texto_miniatura"), 4)
    g["hashtags"] = [re.sub(r"\W", "", h) for h in (g.get("hashtags") or []) if isinstance(h, str)][:14]
    g["tags"] = [limpiar(t) for t in (g.get("tags") or []) if isinstance(t, str)][:30]
    return g


# ---------- correcciones (editor y verificador) ----------
def _aplicar(g, resp, etiqueta):
    n = 0
    for c in resp.get("correcciones") or []:
        try:
            i = int(c["i"])
            if 0 <= i < len(g["escenas"]) and c.get("narracion"):
                g["escenas"][i]["narracion"] = limpiar(c["narracion"])
                if c.get("tipo") in TIPOS:
                    g["escenas"][i]["tipo"] = c["tipo"]
                n += 1
        except (KeyError, ValueError, TypeError):
            continue
    if resp.get("titulo"):
        g["titulo"] = limpiar(resp["titulo"])[:100]
    if resp.get("gancho_pantalla"):
        g["gancho_pantalla"] = corto(resp["gancho_pantalla"], 5)
    if resp.get("texto_miniatura"):
        g["texto_miniatura"] = corto(resp["texto_miniatura"], 4)
    print(f"[guion] {etiqueta}: {n} correcciones")
    return g


def _vista(g):
    return json.dumps({"titulo": g["titulo"], "gancho_pantalla": g.get("gancho_pantalla"),
                       "escenas": [{"i": i, "tipo": e["tipo"], "narracion": e["narracion"]}
                                   for i, e in enumerate(g["escenas"])]}, ensure_ascii=False, indent=1)


EDITOR = """You are the editor-in-chief of "{canal}". Review this script ({formato}) about "{titulo}".
Story status according to research: {estado}.

Find and fix:
1. English that sounds unnatural out loud, filler, repeated ideas.
2. Facts NOT in the SOURCES or wrong (dates, numbers, prices, platforms). Check WHO said each thing: a
   statement must be attributed to the exact person/outlet the SOURCES name (don't mix up a studio statement
   with an analyst's or a journalist's opinion).
3. Rumors or opinions presented as facts: rewrite them ("reports say…", "this is unconfirmed…", "my take…") and
   fix the "tipo". If the story status is "rumor", NO scene about the main claim may be "confirmed".
4. Spoilers, leaked content, graphic violence, or anything in the first scene that isn't ad-friendly.
5. {extra}

Don't change what's already right. Keep each scene's length similar.

FIRST OF ALL: is the script about the SAME story the SOURCES describe, and are its main facts in the SOURCES?
If not, reply "fiel_a_fuente": false and explain in "problema". That script will not be published.

Reply ONLY with JSON:
{{"fiel_a_fuente": true, "problema": "",
  "correcciones": [{{"i": 0, "narracion": "fixed text", "tipo": "confirmed|reported|rumor|opinion"}}],
  "titulo": "only if you improve it", "gancho_pantalla": "only if you improve it", "texto_miniatura": "only if you improve it"}}

SCRIPT:
{guion}

SOURCES:
{fuente}
"""

VERIFICADOR = """You are the fact-checker of "{canal}", a GTA 6 news channel. Today is {hoy}. Using web search
(prefer Rockstar Newswire, Take-Two investor releases, and major outlets like IGN, GamesRadar, Eurogamer, VGC,
PC Gamer, Kotaku, Polygon, Bloomberg, Reuters), check the dates, numbers, prices, platforms and claims in this
script about "{titulo}". At most 5 searches, on the most important claims. Also check that nothing important
changed in the last 24 hours (e.g. Rockstar confirmed or denied a rumor).

If a claim is wrong or can't be confirmed, fix it or soften it ("according to one report…") and set the right "tipo".

Reply ONLY with JSON:
{{"correcciones": [{{"i": 0, "narracion": "fixed text", "tipo": "confirmed|reported|rumor|opinion"}}],
  "fuentes": ["url1", "url2"], "nota": "one-sentence summary of what you verified"}}

SCRIPT:
{guion}
"""


class GuionNoFiel(RuntimeError):
    pass


def _revisar(g, art, formato, extra):
    import datetime as dt
    fuente = art["texto_en"][:40000]
    try:
        resp = ia.generar_json(EDITOR.format(canal=CANAL, formato=formato, titulo=art["titulo"], extra=extra,
                                             estado=art.get("estado", "reported"), guion=_vista(g), fuente=fuente),
                               intentos=1)
    except Exception as e:  # noqa: BLE001
        resp = None
        print(f"[guion] editor no disponible ({e})")
    if resp is None and art.get("categoria") == "noticia":
        raise GuionNoFiel("noticia sin revisión del editor: no la publico")
    if resp is not None and resp.get("fiel_a_fuente") is False:
        raise GuionNoFiel(f"el editor detectó que el guion no sale de las fuentes: {resp.get('problema', '')[:200]}")
    if resp is not None:
        g = _aplicar(g, resp, "editor")
    # Candado: si la historia es un rumor, nada sobre ella puede quedar como "confirmed"
    if art.get("estado") == "rumor":
        g["sello"] = "rumor"
    g["verificacion"] = "solo contra las fuentes del artículo"
    if ANTHROPIC_API_KEY and CLAUDE_VERIFICAR:
        try:
            resp = ia.generar_json(VERIFICADOR.format(canal=CANAL, titulo=art["titulo"], guion=_vista(g),
                                                      hoy=dt.date.today().isoformat()),
                                   intentos=1, buscar_web=True, solo_claude=True)
            g = _aplicar(g, resp, "verificador")
            g["fuentes_extra"] = [u for u in (resp.get("fuentes") or []) if isinstance(u, str)][:8]
            g["verificacion"] = resp.get("nota") or "verificado con búsqueda web"
        except Exception as e:  # noqa: BLE001
            print(f"[guion] verificación web no disponible ({e})")
    elif art.get("categoria") == "noticia":
        print("[guion] AVISO: noticia sin verificación web (falta ANTHROPIC_API_KEY): revísala antes de publicar")
    g.setdefault("sello", {"confirmed": "confirmed", "reported": "reported", "rumor": "rumor"}.get(
        art.get("estado"), "reported"))
    # Candado de sellos: sin verificación web, ninguna escena puede quedar "más segura" que la historia
    # (en una historia REPORTED no hay escenas CONFIRMED; en una RUMOR, todo lo que no es opinión es RUMOR).
    if not g.get("fuentes_extra"):
        nivel = {"rumor": 0, "reported": 1, "confirmed": 2}
        tope = g["sello"]
        for e in g["escenas"]:
            if e["tipo"] != "opinion" and nivel.get(e["tipo"], 1) > nivel[tope]:
                e["tipo"] = tope
    return g


def _contexto(art):
    partes = [f"STORY: {art['titulo']}", f"STATUS FROM RESEARCH: {art.get('estado', 'reported')}"]
    if art.get("enfoque"):
        partes.append(f"ANGLE: {art['enfoque']}")
    if art.get("medios"):
        partes.append(f"OUTLETS: {', '.join(art['medios'])}")
    return "\n".join(partes)


# ---------- SHORT ----------
PROMPT_SHORT = """You are the scriptwriter of "{canal}", an unofficial English-language YouTube channel about GTA 6.
Its promise: "the GTA 6 channel that tells you what's actually true". Tone: fast, smart, a bit of humor, never
hype for hype's sake.

Write ONE YouTube Short of 35-50 seconds about the story below.

STRUCTURE FOR THIS VIDEO: {estructura}
{guia}

RETENTION (mandatory)
- First sentence = hook of max 10 words, concrete and surprising. No greetings, no "in this video".
- Total: 100-135 words. 6-9 scenes of 1-2 sentences (max 22 words per scene).
- The second-to-last scene gives the takeaway (what it means for players). Last scene (very short): loops back
  to the first line and asks viewers a concrete question to answer in the comments. {cta}

{reglas}
METADATA
- "titulo": max 60 characters, starts with "GTA 6" when natural, honest curiosity, no hashtags, no all-caps,
  no fake claims. If the story is a rumor, the title must make that clear ("rumor", "unconfirmed", "?").
- "gancho_pantalla": 2-5 words in CAPS shown at the top during the first seconds.
- "descripcion": 2-3 sentences about the story.
- "hashtags": 12 one-word hashtags without #, all relevant: 4 specific to the story, 4 about GTA (GTA6, GTAVI,
  GrandTheftAuto, ViceCity), 4 broad gaming (Gaming, GamingNews, PS5, Xbox). Nothing unrelated; no hashtags of
  other games (no GTA5) unless the story is about them.
- "tags": 20 search phrases people would type to find this story.
{aprendizajes}
Reply ONLY with JSON:
{{"titulo": "", "gancho_pantalla": "", "descripcion": "", "hashtags": [], "tags": [],
  "escenas": [{{"narracion": "", "tipo": "confirmed", "pantalla": "", "imagen": "", "stock": ""}}]}}

{contexto}

SOURCES:
{texto_en}
"""


def guion_short(art):
    nombre, estructura = random.choice(list(ESTRUCTURAS_SHORT.items()))
    cta = (f"In this one, briefly invite viewers to subscribe to {CANAL}." if random.random() < 0.34
           else "Do NOT ask for a subscription in this one.")
    prompt = PROMPT_SHORT.format(canal=CANAL, estructura=estructura, guia=guia_contenido(), cta=cta,
                                 reglas=REGLAS_COMUNES, aprendizajes=_aprendizajes("short"),
                                 contexto=_contexto(art), texto_en=art["texto_en"][:30000])
    g = ia.generar_json(prompt, validar=lambda d: _normalizar(d, 5, 11, 85, 175))
    g = _revisar(g, art, "45-second YouTube Short",
                 "The first sentence must be a concrete hook of max 10 words, 'gancho_pantalla' must add curiosity "
                 "without repeating the voice, and the last line must connect back to the first.")
    g["estructura"] = nombre
    return g


# ---------- VIDEO LARGO ----------
PROMPT_LARGO = """You are the lead writer of "{canal}", an unofficial English-language YouTube channel about GTA 6.
Its promise: "the GTA 6 channel that tells you what's actually true".

Write the script for an ANALYSIS VIDEO of 8-11 minutes about the story below. It must add real value: context,
explanation, comparison with the series' history or the industry, and a clearly labelled opinion at the end.

STRUCTURE
1. Intro (45-75 s): open with the most interesting fact, state the big question, promise what the viewer will
   learn. No greetings, no subscribe request at the start. The first scene must be ad-friendly.
2. 4-6 chapters with short titles (what happened, what's confirmed, what's not, context/history, what it means
   for players…). Each chapter ends with a question or turn that pushes to the next.
3. Close (45-60 s): recap what's confirmed, what's rumor and what's still open; give the channel's take
   (tipo "opinion"); invite comments, subscribing to {canal}, and the next video.

STYLE: like a sharp gaming podcast host. Vary rhythm.

LENGTH: 1,150-1,600 words total, split into 40-65 scenes of 1-3 sentences (15-40 words).
Each scene says which chapter it belongs to ("capitulo": index from 0; the intro is chapter 0).
{guia}
{reglas}
METADATA
- "titulo": max 70 characters, main keyword first (usually "GTA 6"), honest curiosity, no fake claims.
- "texto_miniatura": 2-4 punchy, honest words for the thumbnail (CAPS).
- "capitulos": list of chapter titles (the first is "Intro").
- "descripcion": 4-6 sentences for YouTube.
- "hashtags": 12 without #, all relevant. "tags": 20 search phrases.
{aprendizajes}
Reply ONLY with JSON:
{{"titulo": "", "texto_miniatura": "", "descripcion": "", "hashtags": [], "tags": [], "capitulos": [],
  "escenas": [{{"capitulo": 0, "narracion": "", "tipo": "confirmed", "pantalla": "", "imagen": "", "stock": ""}}]}}

{contexto}

SOURCES:
{texto_en}
"""


def guion_largo(art, prueba=False):
    minimos = (6, 20, 120, 600) if prueba else (32, 85, 950, 2100)
    prompt = PROMPT_LARGO.format(canal=CANAL, reglas=REGLAS_COMUNES, guia=guia_contenido(),
                                 aprendizajes=_aprendizajes("largo"), contexto=_contexto(art),
                                 texto_en=art["texto_en"][:40000])
    if prueba:
        prompt = prompt.replace("1,150-1,600 words total, split into 40-65 scenes",
                                "SHORT TEST: 200-350 words total, split into 8-12 scenes") \
                       .replace("4-6 chapters", "2 chapters")
    g = ia.generar_json(prompt, max_tokens=48000, validar=lambda d: _normalizar(d, *minimos))
    caps = [limpiar(c) for c in (g.get("capitulos") or []) if isinstance(c, str)] or ["Intro"]
    for e in g["escenas"]:
        try:
            e["capitulo"] = max(0, min(int(e.get("capitulo", 0)), len(caps) - 1))
        except (TypeError, ValueError):
            e["capitulo"] = 0
    g["capitulos"] = caps
    g = _revisar(g, art, "long analysis video",
                 "The intro must hook within 15 seconds and 'texto_miniatura' must be honest (no fake clickbait).")
    return g
