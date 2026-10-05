# Contribuir a yt-cli

## Entorno de desarrollo

```bash
git clone https://github.com/h3n-x/yt-cli.git
cd yt-cli
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip           # pip ≥ 25.1 para --group
pip install -e . --group dev
# o, con uv:  uv sync
```

Para ejecutar una descarga real necesitas `ffmpeg` y un runtime JavaScript (`deno`).
Los tests no usan la red.

## Antes de abrir un PR

Lo mismo que ejecuta la CI (`.github/workflows/ci.yml`):

```bash
ruff check .
ruff format --check .
mypy src/                # strict
pytest                   # incluye cobertura de ramas; la CI exige ≥ 88 %
```

Si cambias la CLI (comandos u opciones), regenera el autocompletado:

```bash
python packaging/generate_completions.py packaging/completions
```

Todo cambio debe:

- Tener tipado completo (`mypy --strict` sin `# type: ignore` salvo casos comentados).
- Incluir tests. Para lógica que toca yt-dlp, usar el doble `FakeYoutubeDL` de
  `tests/test_downloader_component.py`; para la CLI, `CliRunner` con un downloader falso
  como en `tests/test_cli_downloads.py`.
- Escapar cualquier texto externo que se muestre con Rich (`rich.markup.escape`).
- No construir comandos de shell por concatenación (ver SECURITY.md).
- Respetar las capas de ARCHITECTURE.md (`models/` y `utils/` no importan de capas
  superiores ni de yt-dlp).
- Si añade una opción de configuración, usarla de verdad: un test de contrato falla si un
  campo de configuración no se referencia fuera de `config/`.

Las pruebas contra YouTube real llevan `@pytest.mark.integration` y no se ejecutan por
defecto (`pytest -m integration` para lanzarlas).

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`,
`refactor:`, `test:`, `chore:`.

## Releases

1. Actualiza `__version__` en `src/yt_cli/__init__.py`, `pkgver` en `packaging/PKGBUILD`
   y `CHANGELOG.md`.
2. Crea y empuja el tag `vX.Y.Z`. `.github/workflows/release.yml` comprueba que coincide
   con la versión, construye, publica en PyPI (Trusted Publishing) y crea la release.

## Reportar bugs

Abre un issue con `yt-cli version`, la salida de `yt-cli doctor`, los pasos para
reproducir y la salida completa con `--debug`.

## Dependencias nuevas

Justifica en el PR qué resuelve que la stdlib o las dependencias actuales no resuelvan
(ver la tabla de ARCHITECTURE.md).
