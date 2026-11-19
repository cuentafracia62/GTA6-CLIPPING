"""Narración con edge-tts (voces neuronales de Microsoft, gratis) y tiempos por palabra."""
import asyncio
import subprocess
import time

import edge_tts

from .config import PAUSA_ESCENA, VOZ, VOZ_PITCH, VOZ_RATE, VOZ_RESPALDO


_TIPOGRAFIA = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": ", ", "—": ", ",
                             "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
                             " ": " ", "…": "...", "&": " and ", "<": " ", ">": " "})


def texto_para_voz(texto):
    """edge-tts a veces no devuelve audio con caracteres tipográficos raros: los normalizamos."""
    t = texto.translate(_TIPOGRAFIA)
    t = t.replace("%", " percent").replace("+", " plus ")
    return " ".join(t.split())


async def _sintetizar(texto, mp3, rate, voz=VOZ):
    com = edge_tts.Communicate(texto_para_voz(texto), voz, rate=rate, pitch=VOZ_PITCH, boundary="WordBoundary")
    palabras = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                palabras.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "w": ch["text"]})
    return palabras


def duracion(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


class SinAudio(RuntimeError):
    pass


def narrar(escenas, carpeta, rate=VOZ_RATE, pausa=PAUSA_ESCENA):
    """Un wav por escena. Si la voz principal falla, rehace TODA la narración con la de respaldo
    (así un video nunca mezcla dos voces)."""
    voces = [VOZ] + [v for v in VOZ_RESPALDO if v != VOZ]
    for n, voz in enumerate(voces):
        try:
            if n:
                print(f"[voz] la voz {voces[n - 1]} falla; rehago la narración con {voz}")
            return _narrar(escenas, carpeta, rate, pausa, voz)
        except SinAudio as e:
            ultimo = e
    raise RuntimeError(f"ninguna voz respondió: {ultimo}")


def _narrar(escenas, carpeta, rate, pausa, voz):
    t0 = 0.0
    for i, esc in enumerate(escenas):
        mp3, wav = carpeta / f"voz_{i:03d}.mp3", carpeta / f"voz_{i:03d}.wav"
        for intento in range(4):
            try:
                palabras = asyncio.run(_sintetizar(esc["narracion"], mp3, rate, voz))
                if not palabras or mp3.stat().st_size < 1000:
                    raise RuntimeError("audio vacío")
                break
            except Exception as e:  # noqa: BLE001
                print(f"[voz] escena {i} intento {intento + 1}: {e}")
                if intento == 3:
                    raise SinAudio(f"escena {i}: {e}") from e
                time.sleep(3 * (intento + 1))
        p = pausa + (0.25 if esc.get("pausa_extra") else 0)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-af", f"apad=pad_dur={p}",
                        "-ar", "44100", "-ac", "1", str(wav)], check=True)
        dur = duracion(wav)
        esc.update(wav=wav, inicio=t0, dur=dur,
                   palabras=[{"t": q["t"] + t0, "d": q["d"], "w": q["w"]} for q in palabras])
        t0 += dur
    return escenas, t0
