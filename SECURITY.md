# Política de seguridad

## Reporte de vulnerabilidades

Si encuentras una vulnerabilidad de seguridad en yt-cli, repórtala de forma privada a
`security@yt-cli.example` (no abras un issue público). Incluye:

- Versión de yt-cli afectada
- Pasos para reproducir
- Impacto estimado

Se confirma la recepción en un plazo de 72 horas y se coordina la divulgación responsable
tras publicar un parche.

## Garantías de diseño

yt-cli sigue estas reglas de forma no negociable:

1. **Nunca se ejecutan comandos de shell construidos por concatenación de strings.**
   Toda invocación a `ffmpeg`/`ffprobe` usa `subprocess.run` con una lista explícita de
   argumentos y `shell=False`.
2. **yt-dlp se usa como librería Python**, no como subproceso con argumentos armados a
   partir de entrada del usuario.
3. **Toda URL se valida contra una lista blanca de esquemas (`http`/`https`) y hosts**
   (`youtube.com`, `youtu.be`, `music.youtube.com`) antes de pasarla a yt-dlp.
4. **Toda ruta derivada de metadatos remotos** (títulos de video, nombres de canal, etc.)
   se resuelve y se confina al directorio de descarga configurado, rechazando cualquier
   intento de `../` (path traversal).
5. **La configuración y el historial se escriben de forma atómica** (archivo temporal +
   `rename()`), para que una interrupción a mitad de escritura no corrompa el estado.
6. **Desde v0.2.0, la configuración, el historial y la cache usan un lock exclusivo
   entre procesos** (`utils/locking.py`, vía `fcntl.flock`) alrededor de todo el ciclo
   lectura-modificación-escritura, para que dos invocaciones concurrentes de `yt-cli` no
   se pisen los cambios mutuamente (ver `AUDIT_REPORT.md`, hallazgo B7, y
   `SECURITY_REPORT.md` para la prueba de concurrencia real que demuestra la corrección).

## Limitación conocida: `self-update`

`yt-cli self-update` (v0.3.0) consulta la API pública de PyPI y ejecuta
`pip install --upgrade yt-cli` mediante una lista de argumentos fija (nunca un comando de
shell construido por concatenación). La integridad del paquete depende enteramente de la
cadena de confianza de pip/PyPI (HTTPS + hashes) — **no hay una verificación de firma
adicional propia** (p. ej. Sigstore/cosign) antes de instalar. Esto se documenta aquí
explícitamente como limitación conocida, no como un problema resuelto; ver ROADMAP.md.

## Alcance

Este proyecto descarga contenido de YouTube para uso personal. El usuario es responsable
de cumplir los Términos de Servicio de YouTube y las leyes de derechos de autor aplicables
en su jurisdicción. yt-cli no provee ni facilita la elusión de DRM.
