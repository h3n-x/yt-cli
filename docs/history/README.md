# Informes históricos (v0.1.0 – v0.3.x)

Estos informes se escribieron en sesiones **sin acceso para ejecutar el código**: sus
propios textos lo declaran (p. ej. `TEST_REPORT.md`: "ningún archivo de `tests/*.py` se
ejecutó"). Se conservan como registro histórico, pero varias de sus afirmaciones resultaron
falsas al ejecutar el proyecto (la suite tenía 10 tests fallando, `config set` no podía
guardar, las completions no funcionaban, la CI no podía pasar).

La auditoría vigente, basada en ejecución real, es
[`docs/AUDIT_2026-10.md`](../AUDIT_2026-10.md); los cambios que la resuelven están en la
sección 0.4.0 del [CHANGELOG](../../CHANGELOG.md).
