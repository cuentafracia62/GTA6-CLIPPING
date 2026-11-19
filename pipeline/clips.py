"""Clips de streams de GTA 6, SOLO de streamers que dieron permiso (programa de clipping, campaña o permiso escrito).

La lista de permisos está en data/permisos_clips.json. Un streamer se usa solo si:
  - "activo" es true,
  - tiene "enlace_prueba_permiso" (la página del programa/campaña o el mensaje donde te dio permiso),
  - "uso_comercial" es true (los videos del canal pueden monetizarse),
  - "vence" está vacío o es una fecha futura.
Cualquier otro streamer se ignora, aunque su clip sea viral.

Plataformas:
  - Twitch: API oficial (Helix). Necesita TWITCH_CLIENT_ID y TWITCH_CLIENT_SECRET (gratis en dev.twitch.tv).
  - Kick: API pública de la web (sin clave). Si Kick la bloquea, se puede poner la URL del clip a mano en
    "clips_manuales" del permiso.
La descarga se hace con yt-dlp.
"""
import datetime as dt
import json
import subprocess
import time

import requests

from . import db
from .config import CLIPS_HORAS, DATA, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, USER_AGENT

PERMISOS = DATA / "permisos_clips.json"
USADOS = DATA / "clips_usados.json"
JUEGO_TWITCH = "Grand Theft Auto VI"


def autorizados():
    """Streamers con permiso vigente (ver reglas arriba)."""
    hoy = dt.date.today().isoformat()
    ok = []
    for p in db.leer(PERMISOS, []):
        if not isinstance(p, dict) or not p.get("activo"):
            continue
        if not str(p.get("enlace_prueba_permiso", "")).startswith("http"):
            print(f"[clips] {p.get('creador')}: sin enlace de prueba del permiso; no lo uso")
            continue
        if p.get("uso_comercial") is not True:
            print(f"[clips] {p.get('creador')}: el permiso no incluye uso comercial; no lo uso")
            continue
        if p.get("vence") and str(p["vence"]) < hoy:
            print(f"[clips] {p.get('creador')}: el permiso venció el {p['vence']}; no lo uso")
            continue
        ok.append(p)
    return ok


def _usados():
    return set(db.leer(USADOS, []))


def marcar_usado(clip_id):
    lista = db.leer(USADOS, [])
    if clip_id not in lista:
        lista.append(clip_id)
        db.escribir(USADOS, lista[-2000:])


# ---------- Twitch ----------
_TOKEN = {}


def _twitch(ruta, **params):
    if not _TOKEN:
        r = requests.post("https://id.twitch.tv/oauth2/token", timeout=30, data={
            "client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials"})
        r.raise_for_status()
        _TOKEN["t"] = r.json()["access_token"]
    r = requests.get(f"https://api.twitch.tv/helix/{ruta}", params=params, timeout=30, headers={
        "Client-Id": TWITCH_CLIENT_ID, "Authorization": f"Bearer {_TOKEN['t']}"})
    r.raise_for_status()
    return r.json().get("data", [])


def _clips_twitch(p, desde):
    if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
        print(f"[clips] {p['creador']}: faltan TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET")
        return []
    usuario = _twitch("users", login=p["canal"])
    if not usuario:
        print(f"[clips] Twitch: no existe el canal {p['canal']}")
        return []
    juego = _twitch("games", name=JUEGO_TWITCH)
    juego_id = juego[0]["id"] if juego else None
    datos = _twitch("clips", broadcaster_id=usuario[0]["id"], first=50,
                    started_at=desde.isoformat().replace("+00:00", "Z"))
    salida = []
    for c in datos:
        if juego_id and c.get("game_id") != juego_id:
            continue  # solo clips jugando GTA 6
        salida.append({"id": f"twitch:{c['id']}", "url": c["url"], "titulo": c.get("title", ""),
                       "vistas": c.get("view_count", 0), "duracion": c.get("duration", 0),
                       "fecha": c.get("created_at", ""), "plataforma": "Twitch"})
    return salida


# ---------- Kick ----------
def _clips_kick(p, desde):
    try:
        r = requests.get(f"https://kick.com/api/v2/channels/{p['canal']}/clips", timeout=30,
                         params={"sort": "view", "time": "week"},
                         headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        r.raise_for_status()
        datos = r.json().get("clips", [])
    except Exception as e:  # noqa: BLE001
        print(f"[clips] Kick no respondió para {p['canal']} ({str(e)[:120]}); uso solo los clips manuales")
        return []
    salida = []
    for c in datos:
        cat = (c.get("category") or {}).get("name", "")
        if cat and "grand theft auto vi" not in cat.lower() and "gta 6" not in cat.lower():
            continue
        fecha = c.get("created_at", "")
        try:
            if fecha and dt.datetime.fromisoformat(fecha.replace("Z", "+00:00")) < desde:
                continue
        except ValueError:
            pass
        salida.append({"id": f"kick:{c.get('id')}", "url": c.get("clip_url") or f"https://kick.com/{p['canal']}?clip={c.get('id')}",
                       "titulo": c.get("title", ""), "vistas": c.get("views") or c.get("view_count") or 0,
                       "duracion": c.get("duration", 0), "fecha": fecha, "plataforma": "Kick"})
    return salida


def buscar(horas=None):
    """Clips recientes de GTA 6 de todos los streamers autorizados, del más visto al menos visto."""
    desde = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=horas or CLIPS_HORAS)
    usados = _usados()
    todos = []
    for p in autorizados():
        try:
            plataforma = (p.get("plataforma") or "").lower()
            lista = _clips_twitch(p, desde) if plataforma == "twitch" else _clips_kick(p, desde) \
                if plataforma == "kick" else []
        except Exception as e:  # noqa: BLE001
            print(f"[clips] error buscando clips de {p.get('creador')}: {str(e)[:150]}")
            lista = []
        for url in p.get("clips_manuales") or []:
            lista.append({"id": f"manual:{url}", "url": url, "titulo": "", "vistas": 0, "duracion": 0,
                          "fecha": "", "plataforma": p.get("plataforma", "").title()})
        for c in lista:
            if c["id"] in usados:
                continue
            c.update(creador=p["creador"], canal=p["canal"], permiso=p["enlace_prueba_permiso"],
                     programa=p.get("programa", ""), atribucion=p.get("atribucion") or
                     f"Clip: {p['creador']} ({p.get('plataforma', '').title()}) — used with permission",
                     max_segundos=int(p.get("max_segundos") or 60))
            todos.append(c)
    todos.sort(key=lambda c: c.get("vistas") or 0, reverse=True)
    print(f"[clips] {len(todos)} clips nuevos de {len(autorizados())} streamers con permiso")
    return todos


def descargar(clip, destino):
    """Descarga el clip a mp4 con yt-dlp. Devuelve la ruta o None."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    for intento in range(2):
        try:
            subprocess.run(["yt-dlp", "--no-playlist", "--quiet", "--no-warnings",
                            "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                            "-o", str(destino), clip["url"]], check=True, timeout=600)
            if destino.exists() and destino.stat().st_size > 50_000:
                return destino
        except Exception as e:  # noqa: BLE001
            print(f"[clips] no pude descargar {clip['url']} ({str(e)[:150]})")
            time.sleep(5)
    return None


def duracion(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(ruta)],
                         capture_output=True, text=True, timeout=60).stdout
    try:
        return float(json.loads(out)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


def tramos(ruta, carpeta, n, largo=6.0):
    """Corta n tramos de 'largo' segundos repartidos a lo largo del clip (para usarlos como b-roll)."""
    total = duracion(ruta)
    if total < 2:
        return []
    salida = []
    paso = max(0.0, (total - largo) / max(1, n - 1)) if n > 1 else 0
    for i in range(n):
        ini = min(i * paso, max(0, total - largo))
        t = carpeta / f"{ruta.stem}_t{i}.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{ini:.2f}", "-i", str(ruta),
                        "-t", f"{min(largo, total):.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", str(t)], check=True, timeout=300)
        salida.append(t)
    return salida
