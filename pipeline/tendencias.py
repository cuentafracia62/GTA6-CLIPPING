"""Qué está en tendencia sobre GTA 6 AHORA (para elegir temas que la gente está buscando).

Fuentes gratis:
  - YouTube: los videos de GTA 6 más vistos de las últimas 48 h (search.list con tu propia cuota: 100 unidades).
  - Reddit: lo más votado del día en r/GTA6 y r/GTA (JSON público).
Si una fuente falla, se sigue con las demás. El resultado es una lista corta de títulos con su "peso".
"""
import datetime as dt

import requests

from .config import USER_AGENT

_CACHE = {}


def youtube_48h(n=20):
    try:
        from . import youtube
        if not youtube.credenciales_listas():
            return []
        yt = youtube.servicio()
        desde = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)).isoformat().replace("+00:00", "Z")
        r = yt.search().list(part="snippet", q="GTA 6", type="video", order="viewCount", publishedAfter=desde,
                             relevanceLanguage="en", regionCode="US", maxResults=n).execute()
        ids = [i["id"]["videoId"] for i in r.get("items", [])]
        vistas = {}
        if ids:
            s = yt.videos().list(part="statistics", id=",".join(ids)).execute()
            vistas = {i["id"]: int(i["statistics"].get("viewCount", 0)) for i in s.get("items", [])}
        return [{"fuente": "YouTube", "titulo": i["snippet"]["title"], "canal": i["snippet"]["channelTitle"],
                 "peso": vistas.get(i["id"]["videoId"], 0)} for i in r.get("items", [])]
    except Exception as e:  # noqa: BLE001
        print(f"[tendencias] YouTube no disponible ({str(e)[:120]})")
        return []


def reddit_dia(n=15):
    salida = []
    for sub in ("GTA6", "GTA"):
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/top.json", params={"t": "day", "limit": n},
                             headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            for c in r.json()["data"]["children"]:
                d = c["data"]
                if d.get("stickied") or d.get("over_18"):
                    continue
                salida.append({"fuente": f"r/{sub}", "titulo": d.get("title", ""), "canal": "",
                               "peso": int(d.get("score", 0))})
        except Exception as e:  # noqa: BLE001
            print(f"[tendencias] Reddit r/{sub} no disponible ({str(e)[:100]})")
    return salida


def actuales():
    """Lista combinada (se calcula una vez por ejecución)."""
    if "lista" not in _CACHE:
        lista = youtube_48h() + reddit_dia()
        print(f"[tendencias] {len(lista)} temas en tendencia (YouTube 48 h + Reddit hoy)")
        _CACHE["lista"] = lista
    return _CACHE["lista"]


def para_prompt(maximo=25):
    """Texto para la IA: lo más fuerte de cada fuente."""
    lista = actuales()
    if not lista:
        return "(no trend data available today)"
    yt = sorted([t for t in lista if t["fuente"] == "YouTube"], key=lambda t: -t["peso"])[:15]
    rd = sorted([t for t in lista if t["fuente"] != "YouTube"], key=lambda t: -t["peso"])[:10]
    lineas = [f"- [YouTube, {t['peso']:,} views in 48h] {t['titulo']}" for t in yt]
    lineas += [f"- [{t['fuente']}, {t['peso']:,} upvotes today] {t['titulo']}" for t in rd]
    return "\n".join(lineas[:maximo])
