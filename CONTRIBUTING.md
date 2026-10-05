# Contribuir a yt-cli

## Entorno de desarrollo

```bash
git clone https://github.com/yt-cli/yt-cli.git
cd yt-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Antes de abrir un PR

```bash
ruff check .          # estilo y errores comunes
mypy src/              # tipado estricto
pytest --cov=yt_cli    # tests + cobertura
```

Todo el código nuevo debe:

- Tener tipado completo (`mypy --strict` debe pasar sin `# type: ignore` salvo casos
  documentados con un comentario explicando por qué).
- Incluir tests. No se aceptan PRs que reduzcan la cobertura existente.
- Para funciones puras con un dominio de entrada amplio (sanitización, parsing), preferir
  un test de propiedades con Hypothesis además de los casos concretos, siguiendo el
  patrón de `tests/test_naming_properties.py`.
- No introducir invocaciones de shell construidas por concatenación de strings (ver
  SECURITY.md). Cualquier `subprocess.run` nuevo debe usar una lista de argumentos.
- Seguir la separación de capas descrita en ARCHITECTURE.md: `cli/` no contiene lógica de
  negocio, `models/` y `utils/` no importan de capas superiores.

## Estructura de commits

Se sigue [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

## Reportar bugs

Abre un issue con:
- Versión de yt-cli (`yt-cli version`)
- Salida de `yt-cli doctor`
- Pasos para reproducir
- Salida completa con `--debug`

## Añadir una nueva dependencia

Toda dependencia nueva debe justificarse en el PR: qué problema resuelve que la stdlib o
las dependencias existentes no resuelven ya. Ver la tabla de justificación en
ARCHITECTURE.md como referencia del estándar esperado.
