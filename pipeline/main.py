"""Punto de entrada del sistema.

  python -m pipeline.main short                  # investiga, crea y publica un short
  python -m pipeline.main largo                  # lo mismo con un video largo (16:9)
  python -m pipeline.main short --no-subir       # solo crea el video (queda en out/)
  python -m pipeline.main short --tema "Mary Celeste"
  python -m pipeline.main largo --prueba         # video largo corto, para probar el sistema
  python -m pipeline.main estadisticas           # actualiza métricas y aprendizajes
  python -m pipeline.main panel                  # regenera el panel
"""
import argparse
import datetime as dt
import json
import re
import shutil
import sys
import unicodedata

from . import db, guion, ia, investigacion, miniatura, montaje, panel, visuales, voz, youtube
from .config import (CANAL, LIMITE_SHORTS_DIA, MODO_REVISION, NOTICIA_SIN_VERIFICAR_PRIVADA, OUT,
                     PUBLICAR_CON_RESPALDO, VOZ_RATE, VOZ_RATE_LARGO)


def slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:50]


def _mmss(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def metadatos(g, art, formato, capitulos, creditos):
    titulo = g["titulo"]
    if formato == "short":
        # En el reproductor de Shorts casi nadie abre la descripción: los hashtags que se VEN son los del
        # título. Ponemos los 2 más específicos del caso + #Shorts (si caben en los 100 caracteres).
        en_titulo = []
        for h in [*[x.lstrip("#").strip() for x in g.get("hashtags", [])][:2], "Shorts"]:
            if h and len(titulo) + len(" #" + h) <= 100 and h.lower() not in [x.lower() for x in en_titulo]:
                titulo += " #" + h
                en_titulo.append(h)
    partes = [g["descripcion"].strip(), ""]
    if formato == "largo" and len(capitulos) >= 3:
        partes += ["⏱️ Chapters"] + [f"{_mmss(t)} {n}" for t, n in capitulos] + [""]
    estado = {"confirmed": "✅ Status: confirmed (official or multiple sources).",
              "reported": "🟡 Status: reported by media, not officially confirmed.",
              "rumor": "🔴 Status: RUMOR / unconfirmed. Treat it as such."}.get(g.get("sello") or art.get("estado"))
    if estado:
        partes.append(estado)
    partes.append("What do you think? Tell me in the comments 👇")
    partes.append(f"🔔 Subscribe to {CANAL}: GTA 6 news, checked and labelled.\n")
    fuentes = art.get("fuentes", []) + g.get("fuentes_extra", [])
    partes.append(f"📚 Sources (checked {dt.date.today().isoformat()}):\n"
                  + "\n".join(f"• {u}" for u in dict.fromkeys(fuentes)))
    if creditos:
        for fuente in dict.fromkeys(c.get("fuente", "Pexels") for c in creditos):
            autores = ", ".join(dict.fromkeys(c["autor"] for c in creditos
                                              if c.get("autor") and c.get("fuente", "Pexels") == fuente))
            partes.append(f"🎞️ Footage: {fuente} ({autores}).")
    partes.append("🎨 Illustrations are AI-generated and are NOT game screenshots. Narration uses a synthetic voice. "
                  "Rumors and opinions are labelled on screen.")
    partes.append("Leonida Report is an unofficial fan channel, not affiliated with Rockstar Games or "
                  "Take-Two Interactive. Grand Theft Auto is a trademark of Take-Two Interactive.")
    # YouTube ignora TODOS los hashtags si hay más de 15 (contando los del título): usamos 15 en total
    del_titulo = [h.lower() for h in re.findall(r"#(\w+)", titulo)]
    maximo = 15 - len(del_titulo)
    extra = ["GTA6", "Shorts" if formato == "short" else "GTAVI"]
    lista = []
    for h in [*g.get("hashtags", []), *extra]:
        h = h.lstrip("#").strip()
        if h and h.lower() not in [x.lower() for x in lista] + del_titulo and len(lista) < maximo:
            lista.append(h)
    if "gta6" not in [x.lower() for x in lista] + del_titulo and lista:
        lista[-1] = "GTA6"  # la etiqueta del canal siempre va
    partes.append("\n" + " ".join("#" + h for h in lista))
    desc = "\n".join(partes)
    # Etiquetas: YouTube acepta hasta 500 caracteres en total
    tags, largo = [], 0
    for t in [*g.get("tags", []), *[h for h in re.findall(r"#(\w+)", titulo) + lista if h.lower() != "shorts"]]:
        t = t.strip()
        if t and t.lower() not in [x.lower() for x in tags] and largo + len(t) + 3 <= 480:
            tags.append(t)
            largo += len(t) + 3
    return {"titulo": titulo[:100], "descripcion": desc[:4900], "tags": tags}


# Palabras muy comunes del español y del portugués que casi nunca aparecen en un texto en inglés
_NO_INGLES = set("el la los las que de del por para con una uno pero como muy esta este esto también "
                 "porque cuando donde está son fue ser hay más já não uma com isso".split())
_INGLES = set("the and of to is in that it for on with this was are be you not but they have".split())


def parece_ingles(texto):
    """El canal es SOLO en inglés: comprueba que el guion no se haya escrito en otro idioma."""
    palabras = re.findall(r"[a-záéíóúñãõç']+", texto.lower())
    if len(palabras) < 20:
        return True
    en = sum(p in _INGLES for p in palabras)
    otro = sum(p in _NO_INGLES for p in palabras)
    return en >= 3 * max(otro, 1) or (otro == 0 and en > 0)


def hace_falta_short():
    """Para las ejecuciones automáticas: ¿toca crear un short ahora?

    - No pasa del límite diario de subidas de YouTube (el día de la cuota va de medianoche a medianoche
      hora del Pacífico): LIMITE_SHORTS_DIA shorts (4), que dejan lugar al video largo diario y a 1 de reserva.
    - Si los 2 próximos horarios ya tienen video programado, no hace nada. Así las ejecuciones de respaldo
      solo crean video cuando GitHub se saltó una ejecución principal.
    """
    from zoneinfo import ZoneInfo
    pacifico = ZoneInfo("America/Los_Angeles")
    hoy = dt.datetime.now(pacifico).date()
    subidos = 0
    for v in db.videos():
        if v.get("formato") != "short" or not v.get("youtube_id") or not v.get("fecha"):
            continue
        try:
            f = dt.datetime.fromisoformat(v["fecha"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if f.tzinfo and f.astimezone(pacifico).date() == hoy:
            subidos += 1
    limite = LIMITE_SHORTS_DIA
    # Si ya se creó un short en los últimos 100 minutos, esta ejecución es un respaldo innecesario
    # (las ejecuciones principales van separadas 3 h o más; cada respaldo va 1 h después de la suya)
    hace3h = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=100)
    for v in db.videos():
        try:
            f = dt.datetime.fromisoformat((v.get("fecha") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if v.get("formato") == "short" and f.tzinfo and f > hace3h and v.get("estado") != "retenido_calidad":
            print("[main] ya se creó un short hace menos de 100 minutos; esta ejecución de respaldo no hace falta")
            return False
    if subidos >= limite:
        print(f"[main] ya se subieron {subidos} shorts en el día de cuota de YouTube (límite {limite}); no creo otro")
        return False
    proximos = youtube.proximos_horarios(2)
    if proximos and all(ocupado for _, ocupado in proximos):
        print(f"[main] los próximos horarios ya tienen video ({', '.join(h for h, _ in proximos)}); no hace falta otro")
        return False
    return True


def crear_video(formato, tema=None, subir=True, prueba=False):
    vertical = formato == "short"
    with db.Ejecucion(formato) as ej:
        ia.reiniciar_costos()
        art = investigacion.elegir_tema(formato, tema)
        ej.nota(tema=art["titulo"])

        g = guion.guion_short(art) if vertical else guion.guion_largo(art, prueba=prueba)
        print(f"[main] título: {g['titulo']}")
        for e in g["escenas"][:12]:
            print(f"   · [{e['tipo']}] {e['narracion']}")
        print(f"[main] sello del video: {g.get('sello')} · verificación: {g.get('verificacion')}")
        texto_guion = " ".join([g["titulo"], *(e["narracion"] for e in g["escenas"])])
        if not parece_ingles(texto_guion):
            raise RuntimeError("El guion no está en inglés: el canal es solo para público de habla inglesa. "
                               "No se crea el video.")

        vid_id = f"{dt.date.today().isoformat()}-{formato}-{slug(art['titulo'])}"
        carpeta = OUT / vid_id
        trabajo = carpeta / "trabajo"
        if trabajo.exists():
            shutil.rmtree(trabajo)
        trabajo.mkdir(parents=True)

        escenas = g["escenas"]
        if not vertical:  # pausa un poco más larga al cambiar de capítulo
            for a, b in zip(escenas, escenas[1:]):
                a["pausa_extra"] = a.get("capitulo") != b.get("capitulo")
        escenas, total_voz = voz.narrar(escenas, trabajo, rate=VOZ_RATE if vertical else VOZ_RATE_LARGO)
        print(f"[main] narración: {total_voz:.1f}s")

        capitulos = []
        if not vertical:
            vistos = set()
            for e in escenas:
                if e["capitulo"] not in vistos:
                    vistos.add(e["capitulo"])
                    capitulos.append((0.0 if not capitulos else e["inicio"], g["capitulos"][e["capitulo"]]))

        estilo = visuales.elegir_estilo()
        print(f"[main] estilo visual: {estilo['nombre']}")
        creditos = visuales.preparar(escenas, trabajo, vertical, estilo, 0.3 if vertical else 0.6)

        video = carpeta / ("short.mp4" if vertical else "video.mp4")
        info = montaje.montar(escenas, total_voz, trabajo, video, vertical, estilo,
                              gancho=g.get("gancho_pantalla", ""), capitulos=capitulos)

        mini = None
        if not vertical:
            primera_img = next(e["archivo"] for e in escenas if e["visual"] == "imagen")
            texto = g.get("texto_miniatura") or guion.corto(g["titulo"], 4)
            mini = miniatura.crear(primera_img, texto, carpeta / "miniatura.jpg", sello=g.get("sello"))

        meta = metadatos(g, art, formato, capitulos, creditos)
        registro = {
            "id": vid_id, "fecha": db.ahora(), "formato": formato, "estado": "creado",
            "tema": art["titulo"], "tema_clave": art.get("clave", art["titulo"]), "categoria": art.get("categoria"),
            "interes_fuentes": art.get("interes"), "estado_historia": g.get("sello") or art.get("estado"), "titulo_yt": meta["titulo"], "estructura": g.get("estructura"),
            "estilo": estilo["nombre"], "duracion": info["duracion"], "escenas": len(escenas),
            "clips_reales": len(creditos), "musica": info["musica"], "verificacion": g.get("verificacion"),
            "fuentes": list(dict.fromkeys(art.get("fuentes", []) + g.get("fuentes_extra", []))),
            "costo_usd": round(ia.COSTOS["usd"], 4), "ia": ia.COSTOS["llamadas"],
            "prueba": prueba,
        }
        (carpeta / "meta.json").write_text(json.dumps({**meta, "registro": registro, "guion": [
            {k: e.get(k) for k in ("capitulo", "tipo", "narracion", "pantalla", "imagen", "stock", "visual")}
            for e in escenas]},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if not prueba:
            db.guardar_video(registro)
        print(f"[main] video listo: {video} ({info['duracion']}s) · costo IA ${registro['costo_usd']:.3f}")

        # Filtro de calidad: Pollinations (respaldo sin clave) inventa datos con frecuencia; no publicamos eso
        solo_respaldo = all(c["proveedor"] == "pollinations" for c in ia.COSTOS["llamadas"])
        if subir and not prueba and solo_respaldo and not PUBLICAR_CON_RESPALDO:
            registro["estado"] = "retenido_calidad"
            db.guardar_video(registro)
            raise RuntimeError("Guion escrito solo por el respaldo gratuito (Pollinations): no se publica. "
                               "Configura ANTHROPIC_API_KEY o GEMINI_API_KEY (ver GUIA.md).")
        if subir and not prueba:
            if not youtube.credenciales_listas():
                print("[main] faltan credenciales de YouTube: el video no se sube (ver GUIA.md)")
            elif db.ya_subido(registro["tema_clave"], formato):
                print("[main] este tema ya se subió antes: no lo subo otra vez")
            else:
                # Candado del modo automático: una noticia sin verificación web no se publica sola
                revision = bool(not MODO_REVISION and NOTICIA_SIN_VERIFICAR_PRIVADA
                                and art.get("categoria") == "noticia" and not g.get("verificado_web"))
                if revision:
                    print("[main] noticia sin verificación web: se sube PRIVADA para que la revises")
                ultimo = None
                for intento in range(3):
                    try:
                        res = youtube.subir(video, meta, mini, revision=revision)
                        registro.update(res)
                        db.guardar_video(registro)
                        (OUT / "SUBIDO").write_text(registro.get("youtube_id", ""), encoding="utf-8")
                        break
                    except Exception as e:  # noqa: BLE001
                        ultimo = e
                        print(f"[main] subida falló (intento {intento + 1}): {e}")
                else:
                    registro["estado"] = "error_subida"
                    db.guardar_video(registro)
                    raise RuntimeError(f"No se pudo subir a YouTube: {ultimo}")
        ej.nota(video=vid_id, estado_video=registro["estado"], costo_usd=registro["costo_usd"])
    return registro


def main():
    ap = argparse.ArgumentParser(description="Sistema de YouTube — Leonida Report (GTA 6)")
    ap.add_argument("accion", choices=["short", "largo", "estadisticas", "panel"])
    ap.add_argument("--tema", help="URLs de noticias separadas por coma, o un tema atemporal / artículo de Wikipedia")
    ap.add_argument("--no-subir", action="store_true")
    ap.add_argument("--prueba", action="store_true", help="Video corto de prueba (no se registra ni se sube)")
    ap.add_argument("--programado", action="store_true",
                    help="Ejecución automática: solo crea el short si hace falta (ver hace_falta_short)")
    args = ap.parse_args()

    if args.programado and args.accion == "short" and not hace_falta_short():
        return 0
    try:
        if args.accion in ("short", "largo"):
            crear_video(args.accion, args.tema, subir=not args.no_subir, prueba=args.prueba)
        elif args.accion == "estadisticas":
            with db.Ejecucion("estadisticas"):
                from . import estadisticas
                if youtube.credenciales_listas():
                    estadisticas.actualizar()
                else:
                    print("[main] sin credenciales de YouTube: solo analizo lo guardado")
                    estadisticas.analizar()
    finally:
        panel.generar()  # el panel se actualiza siempre, también cuando algo falla
    return 0


if __name__ == "__main__":
    sys.exit(main())
