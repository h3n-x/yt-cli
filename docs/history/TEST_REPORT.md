# TEST_REPORT.md — yt-cli v0.3.0

## Restricción del entorno (se repite aquí porque es central para interpretar este informe)

Este sandbox no tiene acceso de red (`pip install` falla:
`No matching distribution found for hatchling`), en ninguna de las tres sesiones de
trabajo sobre este proyecto (v0.1.0, v0.2.0, v0.3.0). Como resultado:

- `pytest`, `pydantic`, `rich`, `typer`, `yt-dlp`, `orjson`, `tomli_w`, `hypothesis`,
  `httpx` **no están instalados** y no se pudieron instalar en esta sesión.
- Los archivos de test usan fixtures de pytest (`tmp_path`, `monkeypatch`,
  `pytest.mark.parametrize`, `typer.testing.CliRunner`) que **no se pueden ejecutar sin
  pytest/typer instalados**.

**Por lo tanto: ningún archivo de `tests/*.py` se ejecutó literalmente vía `pytest` en
esta sesión.** Se repite explícitamente para cumplir con el requisito de "no afirmar
que algo fue probado si no fue ejecutado".

Lo que sí se hizo, sin cambios de metodología respecto a v0.2.0:

1. **Verificación real por ejecución directa (`python3`, sin pytest)** de la lógica
   subyacente a los tests de los módulos puro-stdlib: `utils/naming.py`,
   `core/validators.py`, `models/enums.py`, `utils/locking.py`, y en esta iteración
   también la función `_parse_version` de `cli/main.py` (verificada como script
   standalone, ya que el módulo completo no se puede importar sin typer/rich/httpx
   instalados).
2. **Revisión estática por lectura de código** de todo lo demás, incluida la nueva
   suite `tests/test_cli.py`: cada test se razonó línea por línea contra la
   implementación real de `cli/main.py` (incluyendo el comportamiento documentado de
   Typer/Click con opciones eager, y el hecho de que `rich.Console` resuelve
   `sys.stdout`/`sys.stderr` de forma perezosa, compatible con la redirección de
   `CliRunner`), pero no se ejecutó.

## Cobertura por archivo de test (134 tests en total)

| Archivo | # tests | Dependencias | Estado en esta sesión |
|---|---|---|---|
| `test_naming.py` | 13 | stdlib | **Ejecutado y verificado** |
| `test_validators.py` | 14 | stdlib | **Ejecutado y verificado**, incluye symlink attack real |
| `test_enums.py` | 6 | stdlib (`StrEnum`) | **Ejecutado y verificado** |
| `test_locking.py` | 4 | stdlib (`fcntl`) | **Ejecutado y verificado**, incluye concurrencia real con 20 hilos |
| `test_naming_properties.py` | 5 | hypothesis | Escrito; propiedades verificadas manualmente con casos borde equivalentes |
| `test_version_parsing.py` | 4 | stdlib (lógica) + typer (import del módulo) | Lógica **verificada manualmente** vía script standalone; el archivo de test en sí no se ejecutó porque importar `cli.main` requiere typer/rich/httpx |
| `test_config.py` | 15 | pydantic, tomli_w | Escrito y revisado; no ejecutado |
| `test_download_request.py` | 6 | pydantic | Escrito y revisado; no ejecutado |
| `test_history.py` | 9 | pydantic, orjson | Escrito y revisado; no ejecutado |
| `test_cache.py` | 6 | orjson | Escrito y revisado; no ejecutado |
| `test_downloader.py` | 18 | yt-dlp | Escrito y revisado; no ejecutado |
| `test_cli.py` | 34 | typer, pydantic, rich, yt-dlp, httpx | Escrito y revisado línea por línea; no ejecutado |

**Total ejecutado y verificado de verdad en esta sesión: 37/134 (28%)** — la misma
cifra absoluta que en v0.2.0, porque los 38 tests nuevos de esta iteración
(`test_cli.py` + `test_version_parsing.py`) dependen todos, directa o indirectamente
(por la cadena de imports de `cli/main.py`), de librerías no instalables en este
sandbox. La lógica de `_parse_version` sí se verificó manualmente por separado.

**Total escrito, sintácticamente válido (`py_compile` pasa en los 12 archivos) y
revisado manualmente línea por línea, pendiente de ejecución en CI: 97/134 (72%).**

## Bug real encontrado durante la escritura de tests en esta sesión

Al escribir `test_search_handles_extraction_failure` (verificando que `search()` maneja
con gracia un fallo de extracción), se detectó por revisión de código que
`extract_metadata_only()` puede lanzar **dos** tipos de excepción distintos
(`yt_dlp.utils.DownloadError` propio de yt-dlp, y nuestro propio
`core.downloader.DownloadError` cuando yt-dlp devuelve `info=None` sin lanzar nada), y
que `search()` en `cli/main.py` solo capturaba el primero. Esto se corrigió en el mismo
código (no solo en el test) — ver CHANGELOG.md v0.3.0. Este es exactamente el tipo de
valor que se espera de escribir tests exhaustivos incluso sin poder ejecutarlos: forzar
la revisión completa de cada camino de excepción posible.

## Evidencia de ejecución real (transcripción resumida de esta sesión, v0.3.0)

```
0.2.0 -> (0, 2, 0) OK
1.0.0 -> (1, 0, 0) OK
0.0.0+dev -> (0, 0, 0) OK
2.1.3-beta -> (2, 1, 3) OK
10.20.30 -> (10, 20, 30) OK
Comparaciones de version OK
```

(Ver TEST_REPORT.md de v0.2.0, sección anterior de este mismo documento en el
historial de versiones, para la evidencia de naming/validators/locking, que no cambió
en esta iteración.)

## Por qué no se "simuló" pydantic/yt-dlp/typer para inflar el número ejecutado

Se mantiene la misma decisión que en v0.2.0: no se escribieron stubs falsos de estas
librerías para poder "ejecutar" más archivos de test. Un test que pasa contra un stub
casero no verifica nada sobre el comportamiento real de Typer/Click (p. ej. cómo
resuelve una opción `eager`, o cómo `CliRunner` redirige stdout/stderr), y reportarlo
como "test ejecutado y verde" sería la cobertura inventada que este informe tiene la
instrucción explícita de no producir.

## Qué se espera que ocurra en CI (no verificado, es una expectativa documentada)

Sin cambios respecto a v0.2.0: el workflow `.github/workflows/ci.yml` instala `.[dev]`
y corre `pytest --cov=yt_cli --cov-fail-under=90`. Con `test_cli.py` cubriendo ahora la
capa de orquestación de Typer que antes no tenía tests directos, la expectativa
razonada (no medida) es que la brecha de cobertura identificada en el TEST_REPORT.md de
v0.2.0 ("`cli/main.py` sin tests vía `CliRunner`") esté cerrada. La brecha restante,
documentada honestamente: el flujo end-to-end completo de `download_collection()` con
`yt_dlp.YoutubeDL` real (no mockeado) sigue sin un test propio, ya que requeriría red
real o mocks más profundos del objeto `YoutubeDL` — se deja pendiente en ROADMAP.md.

