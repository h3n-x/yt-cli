# Política de seguridad

## Reportar una vulnerabilidad

Repórtala de forma privada mediante **GitHub → pestaña Security → "Report a
vulnerability"** en https://github.com/h3n-x/yt-cli (no abras un issue público).
Incluye la versión (`yt-cli version`), los pasos para reproducir y el impacto estimado.

## Garantías de diseño

1. **Sin comandos de shell construidos por concatenación.** yt-dlp se usa como librería;
   el único subproceso propio (`pip` en `self-update`) usa una lista de argumentos fija y
   `shell=False`.
2. **URLs en lista blanca** (`http`/`https`; `youtube.com`, `youtu.be`,
   `youtube-nocookie.com` y sus subdominios, comparando el *hostname* real, no el texto
   antes de `@` ni el puerto).
3. **Texto remoto nunca interpretado como markup.** Títulos, nombres de canal y mensajes
   de error se escapan antes de pasar por Rich, y el logging no interpreta markup: un
   título no puede cambiar estilos ni provocar errores de render.
4. **Nombres de archivo:** yt-dlp sanea cada campo de metadatos (un `/` en un título se
   convierte en `⧸`), por lo que los metadatos no pueden escapar del directorio de
   descarga. Las plantillas solo admiten placeholders simples.
5. **Configuración privada:** `config.toml` se escribe con permisos `0600` (puede contener
   credenciales de proxy) y `config show` oculta `usuario:contraseña`.
6. **Escrituras atómicas y con lock entre procesos** para configuración, historial y cache.
7. **Opciones de yt-dlp vía `[ytdlp]`:** las claves de las que depende yt-cli (rutas,
   formato, postprocesadores, hooks, logger) no se pueden sobrescribir.

## `update` / `self-update`

- Solo se considera legítimo un paquete `yt-cli` de PyPI que declare
  `https://github.com/h3n-x/yt-cli` en sus URLs de proyecto; si el nombre lo registrara
  otra persona, yt-cli se niega a recomendarlo o instalarlo.
- `self-update` solo actúa si yt-cli se instaló con pip y **fuera** de un Python gestionado
  por la distribución (PEP 668); en otro caso indica cómo actualizar con el gestor
  correspondiente (pacman/AUR, pipx, uv).
- Instala exactamente la versión comprobada (`yt-cli==X.Y.Z`).
- La publicación en PyPI está preparada con Trusted Publishing y attestations (PEP 740)
  en `.github/workflows/release.yml`. **Limitación conocida:** `self-update` aún no
  verifica esas attestations antes de instalar; confía en la cadena HTTPS + hashes de pip.

## Alcance

yt-cli descarga contenido accesible públicamente para uso personal y no elude DRM. El
usuario es responsable de cumplir los Términos de Servicio de YouTube y las leyes de
derechos de autor aplicables.
