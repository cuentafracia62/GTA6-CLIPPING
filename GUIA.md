# Leonida Report: cómo poner en marcha el sistema

Es un sistema **100 % independiente** del canal de misterios: otra cuenta de Google, otro canal, otro repositorio de GitHub, otro proyecto de Google Cloud, sus propias claves y su propio entorno de Python (`.venv` en esta carpeta). Se basa en el mismo código, pero no comparte nada con *Misterios Sin Resolver*. Corre en GitHub Actions, así que tu PC puede estar apagada.

**Cuenta del canal:** cuentafacio62@gmail.com

Diferencias con el sistema de misterios:

| Antes (Misterios) | Ahora (GTA 6) |
|---|---|
| Temas de Wikipedia | **Noticias del día**, leídas de 9 medios de videojuegos (IGN, GamesRadar, PC Gamer, Eurogamer, VGC, Kotaku, Polygon, GameSpot, Dexerto) por RSS público. Más **temas atemporales** sobre la historia de la saga (`data/temas.json`) |
| Guion en español | Guion en **inglés**. Cada escena lleva su sello: **CONFIRMED / REPORTED / RUMOR / OUR TAKE** |
| Voz es-MX | Voz **en-US-ChristopherNeural** (respaldo: Guy y Eric) |
| Imágenes de terror | Ilustraciones de estilo neón y synthwave, **marcadas como ilustración, nunca como capturas del juego**, además de clips de archivo de Florida y Miami |
| Público hispanohablante | **Solo público de habla inglesa:** guion, voz, título, descripción e idioma del video en inglés. Si un guion sale en otro idioma, no se crea el video |
| 5 shorts + 1 largo al día | **100 % automático (desde 2026-11-19): 4 shorts y 1 video largo TODOS los días.** Se suben programados y se publican solos: shorts a las 10:00, 13:00, 17:00 y 20:00 ET; largo a las 14:00 ET |
| — | **Candado de noticias (gratis):** una noticia se publica sola si sus fuentes vienen de **2 o más medios distintos** (variable `MIN_MEDIOS_AUTO`). Si solo la publicó 1 medio, el video se sube PRIVADO para que lo revises. Los temas atemporales se publican solos. (Con `ANTHROPIC_API_KEY`, que es de pago, además se verifica con búsqueda web) |

**Lo que el sistema NO hace (a propósito):**
- No descarga tráileres ni clips de streamers.
- No usa material filtrado.
- Si en `assets/footage/` pones gameplay grabado por ti, lo usa (ver `assets/footage/LEEME.md`).

---

## Paso 1. Crear el canal (tú, unos 10 minutos)
1. Entra a youtube.com con **cuentafacio62@gmail.com**. Es mejor hacerlo en otro perfil del navegador, para no mezclarla con la cuenta del canal de misterios.
2. Crea un **canal de marca** con el nombre que elegiste (propuesta: *Leonida Report*).
3. Verifica el canal en **youtube.com/verify** con tu teléfono. Sin esto no se pueden subir miniaturas ni videos de más de 15 minutos.

## Paso 2. Crear el repositorio en GitHub
1. En github.com crea un repositorio **nuevo y aparte**, por ejemplo `leonida-report`. No uses el repositorio de misterios. Hazlo **público**: así los minutos de Actions son ilimitados. Tus claves no se ven aunque el repositorio sea público.
2. Sube a ese repositorio **el contenido de esta carpeta `sistema/`**. Abre una terminal en esta carpeta y ejecuta:
   ```powershell
   git init
   ```
   ```powershell
   git add .
   ```
   ```powershell
   git commit -m "Leonida Report v1"
   ```
   ```powershell
   git remote add origin https://github.com/TU_USUARIO/leonida-report.git
   ```
   ```powershell
   git push -u origin main
   ```
   Si quieres, este paso lo hago yo cuando me digas el nombre del repositorio.

## Paso 3. Autorizar YouTube (OAuth: no compartes ninguna contraseña)
1. Entra a **console.cloud.google.com con cuentafacio62@gmail.com** y crea un **proyecto nuevo**, por ejemplo `leonida-report`. Es un proyecto propio, así que tiene su propia cuota diaria y no le quita subidas al canal de misterios.
2. En ese proyecto:
   - **APIs y servicios → Biblioteca:** activa **YouTube Data API v3** y **YouTube Analytics API**.
   - **Pantalla de consentimiento OAuth:** elige tipo *Externo*, agrega cuentafacio62@gmail.com como **usuario de prueba** y después **publica la app**. Si la dejas en modo de prueba, el token vence a los 7 días.
   - **Credenciales → Crear credenciales → ID de cliente de OAuth → App de escritorio.** Descarga el JSON y guárdalo en **esta carpeta** con el nombre `client_secret.json`.
3. Ejecuta, en esta carpeta, con su propio Python:
   ```powershell
   .venv\Scripts\python obtener_token.py
   ```
4. Se abre el navegador. **Elige cuentafacio62@gmail.com y, cuando lo pregunte, el canal de marca *Leonida Report*.** Acepta los permisos.
5. Aparecen 3 valores en la pantalla. Cópialos en GitHub → **el repositorio de este canal** → **Settings → Secrets and variables → Actions → New repository secret**:
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`
6. Borra el archivo `token_youtube.txt` que se crea en la carpeta. Nunca lo subas a GitHub: `client_secret.json` y `token_youtube.txt` ya están en `.gitignore`.

**Importante para que se publique solo:** mientras Google no apruebe la auditoría del proyecto de Google Cloud, YouTube deja **privado** todo lo que se sube por la API (aunque el sistema lo programe). Pide la auditoría en el formulario *YouTube API Services – Audit and Quota Extension* de Google con el proyecto de este canal. Hasta que la aprueben, tendrás que publicar a mano los videos que queden privados.

## Paso 4. Claves propias de IA y de video (Secrets del repositorio nuevo)
Crea **claves nuevas solo para este canal**. Así cada canal tiene su propio límite de gasto y sus propias estadísticas de uso:
- `ANTHROPIC_API_KEY`: **opcional, de pago** (no se usa en este canal desde 2026-11-19). Sin ella, el guion lo escribe Gemini (gratis) y las noticias se verifican contando medios distintos. La búsqueda de Google dentro de Gemini tampoco es gratis (`GEMINI_BUSQUEDA=1` solo si pagas Gemini).
- `GEMINI_API_KEY`: respaldo. Créala en aistudio.google.com con cuentafacio62@gmail.com.
- `PIXABAY_API_KEY`: clips de archivo. Créate una cuenta gratis en pixabay.com con cuentafacio62@gmail.com y copia la clave desde pixabay.com/api/docs.

## Paso 5. Variables opcionales (Settings → Variables)
| Variable | Valor por defecto | Para qué sirve |
|---|---|---|
| `MODO_REVISION` | `0` | `0` = todo se publica solo. Ponlo en `1` si quieres volver a revisar todo antes de publicar |
| `YT_HORA_PUBLICACION_SHORTS` | `10:00,13:00,17:00,20:00` | Horas (ET) a las que se publican los shorts. Si cambias la cantidad, cambia también los horarios de `.github/workflows/shorts.yml` |
| `YT_HORA_PUBLICACION_LARGOS` | `14:00` | Hora (ET) a la que se publica el video largo de cada día |
| `LIMITE_SHORTS_DIA` | `4` | Máximo de shorts por día. YouTube permite unas 6 subidas al día por proyecto: 4 shorts + 1 largo deja 1 de reserva |
| `ZONA_HORARIA` | `America/New_York` | Zona horaria de los horarios |
| `PROB_ATEMPORAL` | `0.3` | Proporción de temas atemporales frente a noticias |
| `CLAUDE_MODELO` | `claude-opus-5-5` | Para gastar menos: `claude-sonnet-5-5` |
| `CANAL_NOMBRE` | `Leonida Report` | Si eliges otro nombre |

## Paso 6. Primera prueba
GitHub → **Actions → Shorts diarios (GTA 6) → Run workflow**, con *subir* desactivado. Descarga el video desde los *artifacts* de la ejecución y revísalo.
Si te gusta, ya no hace falta nada más: desde ese momento el sistema crea, programa y publica solo.

## Horario automático (hora de Nueva York, ET)
| Qué | Se crea | Se publica |
|---|---|---|
| Video largo | 3:20 ET (justo después de que YouTube reinicia la cuota) | 14:00 ET |
| Short 1 | ~7:30 ET | 10:00 ET |
| Short 2 | ~10:30 ET | 13:00 ET |
| Short 3 | ~14:30 ET | 17:00 ET |
| Short 4 | ~17:30 ET | 20:00 ET |

Cada short tiene una ejecución de respaldo 1 hora después, por si GitHub se salta la principal.

## Tu rutina (opcional, unos 5 minutos a la semana)
1. Mira el panel (`PANEL.md`) o la pestaña *Actions*: errores y videos que quedaron **privados** (noticias sin verificar).
2. Si hay alguno privado, revísalo con `../checklist-publicacion.md` y publícalo o bórralo en YouTube Studio.
3. Si ves un error en un video ya publicado, corrígelo o bórralo en YouTube Studio.

## Uso manual
- **Video sobre una noticia concreta:** en *Run workflow* → tema, pega 1 a 3 URLs de artículos separadas por coma.
- **Tema atemporal:** escribe uno de los temas de `data/temas.json`, o el título de un artículo de Wikipedia en inglés.
