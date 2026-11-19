"""Investigación automática para Leonida Report (GTA 6): elige el tema del video y reúne las fuentes.

Dos tipos de tema:
  1. NOTICIA del día (lo normal): lee los feeds RSS públicos de medios de videojuegos (config.FEEDS), se queda
     con los artículos de los últimos días que hablan de GTA 6, la IA agrupa los titulares por historia y
     elige UNA que no se haya cubierto. Después descarga el texto de esos artículos: esas son las fuentes.
     El estado de la historia se marca así:
        confirmed = lo dice Rockstar/Take-Two, o varios medios citan una fuente oficial
        reported  = lo publica un medio serio, sin confirmación oficial
        rumor     = filtraciones, dataminers, "insiders", redes sociales
  2. ATEMPORAL (a veces, PROB_ATEMPORAL): análisis o historia de la saga desde data/temas.json, con
     Wikipedia como fuente. Sirve cuando no hay noticias nuevas y para variar el contenido.

Nunca se usa material filtrado como fuente principal, ni historias que solo hablen de la vida personal de
un streamer. Los textos de los artículos solo sirven de fuente: el guion se escribe con palabras propias.

Uso manual:  --tema "https://url-1,https://url-2"   → historia a partir de esos artículos
             --tema "Grand Theft Auto: Vice City"    → tema atemporal con ese artículo de Wikipedia
"""
import datetime as dt
import email.utils
import json
import random
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import requests

from . import db, ia
from .config import DATA, DIAS_NOTICIAS, FEEDS, PROB_ATEMPORAL, USER_AGENT

H = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
SEMILLAS = DATA / "temas.json"
GTA = re.compile(r"\bGTA ?(6|VI)\b|Grand Theft Auto (6|VI)\b|\bRockstar\b|\bLeonida\b|\bVice City\b", re.I)
# Historias que no tocamos: piratería, filtraciones de la historia, vida privada, tragedias
PROHIBIDO = re.compile(r"\bpira(cy|ted)\b|\bcrack(ed)?\b|torrent|free download|\bspoilers? (of|for) the ending\b|"
                       r"\bdied\b|\bdeath of\b|\bsuicide\b|\bshooting\b|\bswatt", re.I)


# ---------- utilidades web ----------
def _get(url, timeout=25):
    for intento in range(3):
        try:
            r = requests.get(url, headers=H, timeout=timeout)
            if r.ok:
                return r
            print(f"[investigacion] {urllib.parse.urlparse(url).netloc}: {r.status_code}")
            if r.status_code in (401, 403, 404, 410):
                return None
        except requests.RequestException as e:
            print(f"[investigacion] {urllib.parse.urlparse(url).netloc}: {e.__class__.__name__}")
        time.sleep(2 * (intento + 1))
    return None


def _fecha(texto):
    if not texto:
        return None
    try:
        f = email.utils.parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        try:
            f = dt.datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return f if f.tzinfo else f.replace(tzinfo=dt.timezone.utc)


def _sin_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&nbsp;|&#160;", " ", s)
    s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").replace("&rsquo;", "'")
    return re.sub(r"\s+", " ", s).strip()


def _medio(url):
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    return host


def leer_feeds(dias=DIAS_NOTICIAS):
    """Artículos recientes sobre GTA 6: [{titulo, url, medio, fecha, resumen}]"""
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)
    items = []
    for feed in FEEDS:
        r = _get(feed)
        if not r:
            continue
        try:
            raiz = ET.fromstring(r.content)
        except ET.ParseError:
            print(f"[investigacion] feed ilegible: {_medio(feed)}")
            continue
        atom = "{http://www.w3.org/2005/Atom}"
        entradas = raiz.findall(".//item") or raiz.findall(f".//{atom}entry")
        for e in entradas:
            titulo = _sin_html(e.findtext("title") or e.findtext(f"{atom}title"))
            enlace = (e.findtext("link") or "").strip()
            if not enlace and e.find(f"{atom}link") is not None:
                enlace = e.find(f"{atom}link").get("href", "")
            resumen = _sin_html(e.findtext("description") or e.findtext(f"{atom}summary") or "")[:400]
            fecha = _fecha(e.findtext("pubDate") or e.findtext(f"{atom}published") or e.findtext(f"{atom}updated"))
            if not titulo or not enlace or (fecha and fecha < limite):
                continue
            if not GTA.search(titulo + " " + resumen) or PROHIBIDO.search(titulo):
                continue
            items.append({"titulo": titulo, "url": enlace, "medio": _medio(enlace),
                          "fecha": fecha.date().isoformat() if fecha else "", "resumen": resumen})
    vistos, unicos = set(), []
    for it in items:
        if it["url"] not in vistos:
            vistos.add(it["url"])
            unicos.append(it)
    print(f"[investigacion] {len(unicos)} artículos recientes sobre GTA 6 en {len(FEEDS)} feeds")
    return unicos


class _Parrafos(HTMLParser):
    def __init__(self):
        super().__init__()
        self.dentro, self.saltar, self.actual, self.parrafos = 0, 0, [], []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "aside", "nav", "footer", "figure"):
            self.saltar += 1
        elif tag in ("p", "h2", "li") and not self.saltar:
            self.dentro += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "aside", "nav", "footer", "figure"):
            self.saltar = max(0, self.saltar - 1)
        elif tag in ("p", "h2", "li") and self.dentro:
            self.dentro -= 1
            texto = re.sub(r"\s+", " ", "".join(self.actual)).strip()
            if len(texto) > 70:
                self.parrafos.append(texto)
            self.actual = []

    def handle_data(self, data):
        if self.dentro and not self.saltar:
            self.actual.append(data)


def texto_articulo(url, maximo=7000):
    r = _get(url)
    if not r or "html" not in r.headers.get("content-type", ""):
        return ""
    p = _Parrafos()
    try:
        p.feed(r.text)
    except Exception:  # noqa: BLE001
        return ""
    basura = re.compile(r"cookie|subscribe|newsletter|sign up|affiliate|commission|all rights reserved", re.I)
    return "\n".join(x for x in p.parrafos if not basura.search(x))[:maximo]


# ---------- Wikipedia (temas atemporales) ----------
def _wiki(titulo, maximo):
    r = None
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=H, timeout=30, params={
            "action": "query", "prop": "extracts|info", "explaintext": 1, "redirects": 1, "titles": titulo,
            "inprop": "url", "format": "json", "formatversion": 2})
        page = r.json()["query"]["pages"][0]
    except Exception as e:  # noqa: BLE001
        print(f"[investigacion] Wikipedia falló con {titulo}: {e}")
        return None
    if page.get("missing"):
        return None
    texto = re.split(r"\n==+ ?(See also|References|External links|Further reading|Notes)\b", page.get("extract", ""))[0]
    return {"titulo": page["title"], "url": page.get("fullurl"), "texto": texto[:maximo]}


def tema_atemporal(formato, forzar=None):
    largo = formato == "largo"
    usados = db.temas_usados()
    semillas = json.loads(SEMILLAS.read_text(encoding="utf-8"))
    if forzar:
        elegido = next((t for t in semillas if t["tema"].lower() == forzar.lower()),
                       {"tema": forzar, "wiki": [forzar], "categoria": "pedido"})
    else:
        libres = [t for t in semillas if t["tema"].lower() not in usados and formato in t.get("formatos", ["short", "largo"])]
        if not libres:
            raise RuntimeError("Se acabaron los temas atemporales: agrega más en data/temas.json")
        elegido = random.choice(libres)
    partes, fuentes = [], []
    for w in elegido["wiki"]:
        art = _wiki(w, 26000 if largo else 9000)
        if art:
            partes.append(f"SOURCE: Wikipedia, \"{art['titulo']}\" ({art['url']})\n{art['texto']}")
            fuentes.append(art["url"])
    if not partes:
        raise RuntimeError(f"No encontré fuentes para el tema atemporal '{elegido['tema']}'")
    print(f"[investigacion] tema atemporal → {elegido['tema']}")
    return {"titulo": elegido["tema"], "clave": elegido["tema"], "categoria": elegido.get("categoria", "atemporal"),
            "estado": "confirmed", "texto_en": "\n\n".join(partes), "texto_es": "", "fuentes": fuentes,
            "enfoque": elegido.get("enfoque", ""), "interes": None}


# ---------- noticia del día ----------
ELEGIR = """You are the news editor of "Leonida Report", an English-language YouTube channel about GTA 6
(Grand Theft Auto VI). Today is {hoy}. Below are recent headlines from gaming outlets.

Group the headlines that are about the SAME story, then pick the ONE story that is best for a {formato} today.
Prefer, in this order: official Rockstar / Take-Two news; stories covered by 2+ different outlets; stories with
lasting interest for players (features, launch, sales, performance, controversies with context, industry).
AVOID: anything already covered (list below), piracy, leaked story spoilers, stories that are only about a
streamer's personal life, tragedies, pure clickbait, and stories where the only source is an anonymous post.

Classify the story status honestly:
- "confirmed": Rockstar/Take-Two said it officially, or outlets cite an official source/statement.
- "reported": a reputable outlet reports it, without official confirmation.
- "rumor": leaks, dataminers, insiders, social media claims.

ALREADY COVERED (do not repeat the same angle): {usados}

HEADLINES:
{lista}

Reply ONLY with JSON:
{{"historia": "neutral one-line description of the story", "clave": "short-unique-key-for-this-story",
  "items": [0, 3], "estado": "confirmed|reported|rumor", "por_que": "why this story, one sentence"}}
If no headline is usable, reply {{"historia": "", "items": []}}.
"""


def tema_noticia(formato, urls=None):
    usados = db.temas_usados()
    if urls:
        items = [{"titulo": "", "url": u, "medio": _medio(u), "fecha": "", "resumen": ""} for u in urls]
        indices = list(range(len(items)))
        historia, clave, estado = "", "", "reported"
    else:
        items = leer_feeds()
        if not items:
            return None
        random.shuffle(items)
        items = items[:60]
        lista = "\n".join(f"[{i}] ({it['medio']}, {it['fecha']}) {it['titulo']} — {it['resumen'][:160]}"
                          for i, it in enumerate(items))
        recientes = [v.get("tema") for v in db.videos()[-40:] if v.get("tema")]
        resp = ia.generar_json(ELEGIR.format(hoy=dt.date.today().isoformat(), lista=lista, formato=formato,
                                             usados="; ".join(recientes) or "(nothing yet)"), intentos=2)
        indices = [int(i) for i in resp.get("items") or [] if str(i).isdigit() and int(i) < len(items)]
        historia, clave = (resp.get("historia") or "").strip(), (resp.get("clave") or "").strip()
        estado = resp.get("estado") if resp.get("estado") in ("confirmed", "reported", "rumor") else "rumor"
        if not historia or not indices or clave.lower() in usados or historia.lower() in usados:
            print("[investigacion] la IA no encontró una historia nueva utilizable")
            return None
        print(f"[investigacion] historia: {historia} [{estado}] — {resp.get('por_que', '')}")

    partes, fuentes, medios = [], [], set()
    for i in indices[:5]:
        it = items[i]
        texto = texto_articulo(it["url"])
        if len(texto) < 400:  # sin texto completo usamos el resumen del feed, si lo hay
            texto = it["resumen"] if len(it["resumen"]) > 120 else ""
        if not texto:
            print(f"[investigacion] no pude leer {it['url']}")
            continue
        partes.append(f"SOURCE: {it['medio']} ({it['fecha'] or 'date n/a'}) {it['url']}\n"
                      f"HEADLINE: {it['titulo']}\n{texto}")
        fuentes.append(it["url"])
        medios.add(it["medio"])
    texto_total = "\n\n".join(partes)
    if len(texto_total) < (2500 if formato == "largo" else 900):
        print("[investigacion] muy poco texto de fuente para esta historia")
        return None
    if urls and not historia:
        r = ia.generar_json("In one neutral line, what news story about GTA 6 do these sources describe, and is it "
                            "confirmed (official), reported, or rumor? Reply ONLY JSON {\"historia\": \"\", "
                            "\"estado\": \"confirmed|reported|rumor\"}\n\n" + texto_total[:12000], intentos=1)
        historia = r.get("historia") or urls[0]
        estado = r.get("estado") if r.get("estado") in ("confirmed", "reported", "rumor") else "reported"
    # Candado: una sola fuente que no sea oficial nunca puede ser "confirmed"
    oficial = any(m.endswith("rockstargames.com") or m.endswith("take2games.com") for m in medios)
    if estado == "confirmed" and len(medios) < 2 and not oficial:
        estado = "reported"
    return {"titulo": historia, "clave": clave or historia, "categoria": "noticia", "estado": estado,
            "texto_en": texto_total[:40000], "texto_es": "", "fuentes": fuentes, "interes": len(medios),
            "medios": sorted(medios)}


def elegir_tema(formato="short", forzar=None):
    if forzar:
        urls = [u.strip() for u in forzar.split(",") if u.strip().startswith("http")]
        if urls:
            art = tema_noticia(formato, urls)
            if not art:
                raise SystemExit("No pude leer suficiente texto de esas URLs.")
            return art
        return tema_atemporal(formato, forzar)
    if random.random() >= PROB_ATEMPORAL:
        for _ in range(2):
            art = tema_noticia(formato)
            if art:
                return art
        print("[investigacion] sin noticia nueva utilizable: uso un tema atemporal")
    return tema_atemporal(formato)
