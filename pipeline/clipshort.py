"""Short hecho con un CLIP REAL de stream (solo de streamers con permiso, ver clips.py).

Formato (9:16): el clip original al centro sobre su propio fondo desenfocado, título arriba, crédito abajo,
y una frase corta de voz al inicio (en inglés) que da contexto. Después se escucha el audio original del stream.
La voz y el título aportan contexto propio (no es un re-subido tal cual) y el crédito va en pantalla y en la
descripción, con el enlace al clip original y a la prueba del permiso.
"""
import datetime as dt
import json
import subprocess
import textwrap

from . import clips, db, ia, montaje, voz
from .config import ASSETS, CANAL, OUT

PROMPT = """You write YouTube Shorts packaging for "{canal}", an English-language GTA 6 channel.
We have permission to use this livestream clip of the streamer {creador} playing GTA 6 on {plataforma}.
We have NOT watched the clip: you only know its title and numbers below. Do NOT invent what happens beyond
what the title says; keep it intriguing but honest ("watch what happens when…", "{creador}'s reaction to…").

CLIP TITLE: {titulo}
VIEWS: {vistas}
WHAT IS TRENDING ABOUT GTA 6 RIGHT NOW (use it only if it clearly matches the clip):
{tendencias}

Reply ONLY with JSON, all in natural American English:
{{"titulo": "YouTube title, max 70 characters, include {creador} and GTA 6, no ALL CAPS, no fake urgency",
  "gancho_voz": "spoken hook for the first 3 seconds, max 14 words",
  "texto_pantalla": "big on-screen headline, max 32 characters",
  "descripcion": "2 short sentences of context for the description",
  "hashtags": ["3 specific hashtags without #"], "tags": ["8 search tags"]}}
"""


def _envolver(texto, ancho):
    return "\n".join(textwrap.wrap(texto, ancho)[:3])


def _tiene_audio(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(ruta)], capture_output=True, text=True, timeout=60).stdout
    return bool(out.strip())


def montar(clip_mp4, voz_wav, dur_voz, titulo, credito, salida, carpeta, max_seg):
    montaje.asegurar_fuentes(carpeta / "fonts")
    fuente = (ASSETS / "fonts" / "Anton-Regular.ttf").as_posix().replace(":", r"\:")
    fuente2 = (ASSETS / "fonts" / "BebasNeue-Regular.ttf").as_posix().replace(":", r"\:")
    (carpeta / "titulo.txt").write_bytes(_envolver(titulo.upper(), 20).encode("utf-8"))  # bytes: sin saltos de línea de Windows
    (carpeta / "credito.txt").write_bytes(credito.encode("utf-8"))
    total = min(clips.duracion(clip_mp4), max_seg, 58.0)
    if total < 5:
        raise RuntimeError("el clip es demasiado corto")
    tit = (carpeta / "titulo.txt").as_posix().replace(":", r"\:")
    cre = (carpeta / "credito.txt").as_posix().replace(":", r"\:")
    vf = ("[0:v]split[a][b];"
          "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,"
          "eq=brightness=-0.18[bg];"
          "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
          f"drawtext=fontfile='{fuente}':textfile='{tit}':fontsize=76:fontcolor=white:line_spacing=12:"
          "box=1:boxcolor=0xFF3E9A@0.92:boxborderw=22:x=(w-text_w)/2:y=170,"
          f"drawtext=fontfile='{fuente2}':textfile='{cre}':fontsize=46:fontcolor=white:"
          "box=1:boxcolor=0x0B1026@0.8:boxborderw=14:x=(w-text_w)/2:y=h-360,"
          "fps=30,format=yuv420p[v]")
    if _tiene_audio(clip_mp4):
        # Audio del stream más bajo mientras habla la voz; después, a volumen normal
        fa = (f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,"
              f"volume='if(lt(t,{dur_voz + 0.3:.2f}),0.25,1)':eval=frame[ca];"
              "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[vz];"
              f"[ca][vz]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,"
              f"atrim=end={total:.2f}[a]")
    else:
        fa = (f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={total:.2f},"
              f"atrim=end={total:.2f}[a]")
    montaje._ff(["-i", str(clip_mp4), "-i", str(voz_wav), "-filter_complex", f"{vf};{fa}",
                 "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium",
                 "-crf", "21", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(salida)],
                limite=1200)
    montaje.verificar_audio(salida, total)
    return round(total, 1)


def crear(subir=True, prueba=False, metadatos_fn=None):
    """Hace un short con el clip con permiso más visto que no se haya usado. Devuelve el registro o None."""
    from . import tendencias, youtube
    from .main import parece_ingles, slug

    candidatos = clips.buscar()
    if not candidatos:
        return None
    for clip in candidatos[:4]:
        vid_id = f"{dt.date.today().isoformat()}-short-clip-{slug(clip['creador'] + '-' + clip['id'])[:40]}"
        carpeta = OUT / vid_id
        trabajo = carpeta / "trabajo"
        trabajo.mkdir(parents=True, exist_ok=True)
        archivo = clips.descargar(clip, trabajo / "clip.mp4")
        if not archivo:
            continue
        print(f"[clipshort] clip de {clip['creador']} ({clip['plataforma']}, {clip['vistas']} vistas): {clip['titulo']}")
        g = ia.generar_json(PROMPT.format(canal=CANAL, creador=clip["creador"], plataforma=clip["plataforma"],
                                          titulo=clip["titulo"] or "(no title)", vistas=clip["vistas"],
                                          tendencias=tendencias.para_prompt(12)), intentos=2)
        texto = " ".join([g.get("titulo", ""), g.get("gancho_voz", ""), g.get("descripcion", "")])
        if not g.get("titulo") or not parece_ingles(texto):
            print("[clipshort] el texto no salió en inglés o vino vacío; pruebo otro clip")
            continue
        escena = [{"narracion": g["gancho_voz"], "tipo": "opinion"}]
        escena, dur_voz = voz.narrar(escena, trabajo)
        video = carpeta / "short.mp4"
        dur = montar(archivo, escena[0]["wav"], dur_voz, g.get("texto_pantalla") or g["titulo"],
                     f"{clip['creador']} · {clip['plataforma']} · used with permission", video, trabajo,
                     clip["max_segundos"])

        titulo = g["titulo"][:85]
        for h in [*(x.lstrip("#") for x in g.get("hashtags", [])[:1]), "GTA6", "Shorts"]:
            if len(titulo) + len(h) + 2 <= 100:
                titulo += " #" + h
        desc = "\n".join([
            g.get("descripcion", "").strip(), "",
            f"🎮 Clip: {clip['creador']} on {clip['plataforma']} — {clip['url']}",
            f"✅ {clip['atribucion']}" + (f" ({clip['programa']})" if clip.get("programa") else ""),
            f"🔔 Subscribe to {CANAL} for GTA 6 news, checked and labelled.", "",
            "Leonida Report is an unofficial fan channel, not affiliated with Rockstar Games or Take-Two "
            "Interactive. Grand Theft Auto is a trademark of Take-Two Interactive.", "",
            " ".join("#" + h.lstrip("#") for h in [*g.get("hashtags", [])[:3], "GTA6", "Shorts"]),
        ])
        meta = {"titulo": titulo[:100], "descripcion": desc[:4900], "tags": [t for t in g.get("tags", [])][:15]}
        registro = {
            "id": vid_id, "fecha": db.ahora(), "formato": "short", "estado": "creado", "tipo_short": "clip",
            "tema": f"Clip {clip['creador']}: {clip['titulo']}", "tema_clave": clip["id"], "categoria": "clip",
            "titulo_yt": meta["titulo"], "duracion": dur, "clip_url": clip["url"], "clip_permiso": clip["permiso"],
            "creador": clip["creador"], "costo_usd": round(ia.COSTOS["usd"], 4), "ia": ia.COSTOS["llamadas"],
            "prueba": prueba,
        }
        (carpeta / "meta.json").write_text(json.dumps({**meta, "registro": registro}, ensure_ascii=False,
                                                      indent=2, default=str), encoding="utf-8")
        if prueba:
            return registro
        db.guardar_video(registro)
        clips.marcar_usado(clip["id"])
        if subir and youtube.credenciales_listas():
            res = youtube.subir(video, meta, None)
            registro.update(res)
            db.guardar_video(registro)
            (OUT / "SUBIDO").write_text(registro.get("youtube_id", ""), encoding="utf-8")
        return registro
    return None
