# Preguntas frecuentes

**Me sale `zsh: no matches found: ...` y el proceso termina con `exit 1` sin que
yt-cli imprima nada.**

Esto pasa **antes** de que yt-cli se ejecute: es tu shell (zsh, y a veces bash)
interpretando la URL en vez de pasártela al programa. Las URLs de YouTube casi siempre
tienen `&`, `?` o `=`, y sin comillas:

- `?algo` se interpreta como un patrón glob (de ahí "no matches found").
- `&` corta el comando ahí y lo manda a segundo plano (de ahí el `[1] <pid>` antes del
  error, y que veas el mismo comando reportado sin el resto de la URL).

**Solución: pon la URL completa entre comillas dobles.**

```bash
# Falla:
yt-cli playlist https://music.youtube.com/playlist?list=XYZ&si=abc

# Funciona:
yt-cli playlist "https://music.youtube.com/playlist?list=XYZ&si=abc"
```

Si quieres evitar el problema de raíz en zsh, también puedes desactivar el glob de
signos de interrogación en tu `.zshrc` con `setopt no_nomatch`, aunque seguir
entrecomillando URLs es la práctica recomendada en cualquier shell.

**¿yt-cli funciona en distros distintas a Arch?**
Sí, el núcleo es Python puro + ffmpeg. El PKGBUILD es específico de Arch/AUR, pero
`pip install -e .` funciona en cualquier distro con Python 3.13+ y ffmpeg instalados.

**¿Por qué falla `yt-cli download` con "Host no soportado"?**
yt-cli valida las URLs contra una lista blanca (`youtube.com`, `youtu.be`,
`music.youtube.com`) por seguridad. Otros sitios no están soportados en esta versión
(ver ROADMAP.md).

**¿Puedo usar un proxy?**
Sí: `yt-cli config set network.proxy "http://usuario:pass@host:puerto"`.

**¿Puedo limitar la velocidad de descarga?**
Sí: `yt-cli config set network.rate_limit_kbps 500` (límite en KB/s).

**¿Cómo actualizo yt-cli a la última versión?**
`yt-cli update` solo comprueba si hay una versión nueva; `yt-cli self-update` la instala
vía `pip install --upgrade yt-cli`. Ambos consultan la API pública de PyPI.

**¿Puedo desactivar los colores?**
Sí, yt-cli respeta el estándar [`NO_COLOR`](https://no-color.org/): ejecuta con
`NO_COLOR=1 yt-cli ...` y toda la salida (incluidos los errores) se imprime sin códigos
ANSI de color.

**¿Puedo usar la salida de yt-cli en un script?**
`search`, `history` y `version` aceptan `--json` para salida machine-readable, pensada
para pipear a `jq` u otras herramientas.

**¿Qué hace `overwrite_policy = "rename"`?**
Si el archivo destino ya existe, en vez de omitir la descarga (`skip`) o sobrescribir
(`overwrite`), yt-cli agrega un sufijo numérico: `Video.mp4`, `Video (1).mp4`,
`Video (2).mp4`, etc. Nota: esto solo aplica a descargas individuales (`download`/`audio`),
no a playlists/canales completos (ver ROADMAP.md).

**¿Cómo uso distintos ajustes según el tipo de descarga (p. ej. FLAC para archivar,
480p para ver rápido en el celular)?**
Define perfiles con nombre en `config.toml`:

```toml
[profiles.archivo]
audio_format = "flac"
audio_quality = "best"
```

Y actívalos con `yt-cli --profile archivo audio URL`.

**¿Dónde se guardan mis descargas por defecto?**
En `~/Downloads/yt-cli/`, configurable con
`yt-cli config set general.download_directory "/ruta/que/quieras"`.

**¿Cómo borro el historial?**
`yt-cli history clear` (pide confirmación; usa `--yes` para omitirla). También puedes
exportarlo antes de borrarlo: `yt-cli history export backup.json`.

**`yt-cli doctor` dice que ffmpeg no está instalado, pero sí lo tengo.**
Verifica que esté en tu `PATH`: `which ffmpeg`. Si usas un entorno virtual o un gestor de
versiones, asegúrate de que el shell donde ejecutas `yt-cli` tenga el mismo `PATH` que
usaste para instalar ffmpeg.

**¿Esto elude las protecciones de YouTube (DRM, geobloqueo, etc.)?**
No. yt-cli usa yt-dlp para descargar contenido públicamente accesible, sujeto a los
Términos de Servicio de YouTube. El usuario es responsable de su uso.
