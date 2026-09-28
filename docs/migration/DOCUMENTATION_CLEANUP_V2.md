# Limpieza documental del Frente 1 V1→V2

**Fecha:** 28 de septiembre de 2026. **Alcance:** documentos y artefactos de diagnóstico de la migración cerrada. No se inició el Frente 2.

## Archivos retirados

Se eliminaron **15 logs** de `docs/migration/` después de comprobar que ningún test, script, configuración o código los usa como entrada y que sus resultados esenciales ya constan en las memorias enlazadas:

| Evidencia resumida en | Logs eliminados |
|---|---|
| [Línea base científica](BASELINE_HAZARD_V2.md), [materiales](BASELINE_MATERIALS_V2.md), [secciones](BASELINE_SECTIONS_V2.md) | `canonical_run_v1.log` |
| [Estado de línea base](BASELINE_STATUS_V2.md) | `pytest_v2_003.log`, `pytest_v2_003_resolved.log`, `pytest_v2_003_short_path.log`, `pytest_v2_007_009.log` |
| [Retirada de Quarto](REMOVE_QUARTO_REPORTING_DEPENDENCY.md) | `pytest_remove_quarto.log` |
| [Compatibilidad y CLI](COMPATIBILITY_CLI_V2_023_025.md) | `pytest_v2_compat_cli.log`, `pytest_v2_compat_cli_final.log`, `pytest_v2_compat_cli_verified.log` |
| [Cierre V1→V2](V2_MIGRATION_CLOSURE.md) | `installed_cli_v1.log`, `installed_cli_v2.log`, `installed_wheel_cli.log`, `scientific_regression_installed.log`, `pytest_v2_migration_closure.log`, `references_links_verification.log` |

Los recuentos de pytest, causas de fallos ambientales, resultado de instalación/CLI, comparación de 150 CSV y verificación bibliográfica siguen descritos en esos Markdown. El comando para reproducir el ajuste temporal de pytest permanece en [el estado de línea base](BASELINE_STATUS_V2.md).

## Movimiento y enlaces

El manifiesto `docs/migration/BASELINE_MANIFEST_V2.json` se trasladó sin alterar bytes a [metadata/BASELINE_MANIFEST_V2.json](../../tests/fixtures/v1/metadata/BASELINE_MANIFEST_V2.json). Su SHA-256 antes y después es `b0bb8ead61b0a18967b25def23882c0107a5ac8a669aa95a424a1f6cdfd90c29`; los **436** hashes almacenados no cambiaron. Se actualizaron sus enlaces en [el estado de línea base](BASELINE_STATUS_V2.md), [la guía de compatibilidad](COMPATIBILITY_CLI_V2_023_025.md), [el cierre](V2_MIGRATION_CLOSURE.md) y [el índice](README.md).

Los enlaces a logs retirados se sustituyeron por sus resultados documentados en las tres memorias científicas, el estado de línea base, la ficha de Quarto, la guía de compatibilidad y el cierre. [El plan](../MIGRATION_PLAN_V2.md) y [las tareas preparadas](../BASELINE_TASKS_V2.md) recibieron únicamente una nota inicial que los identifica como históricos y remite al [estado arquitectónico vigente](../ARCHITECTURE_V2.md). Se creó [este índice de migración](README.md). `AGENTS.md` ahora remite al cierre, en vez de al log retirado.

## Preservado deliberadamente

Se mantiene `pytest_v2_004_006.log` (325 bytes): [el README inmutable de las fixtures V1](../../tests/fixtures/v1/README.md) lo enlaza, y el alcance autorizado solo permite mover allí el manifiesto. El log conserva el resultado histórico **120 passed** de la captura científica. Todos los datos científicos V1, código productivo, configuraciones, `references/catalog.yaml` y fuentes bibliográficas permanecieron sin modificaciones.

## Verificación

- Manifiesto trasladado: SHA-256 idéntico; **268/268** outputs históricos coinciden con sus hashes, sin diferencias.
- Fixtures originales: **137 archivos** con el mismo digest de rutas y SHA-256 anterior a la limpieza: `a3fce3f3b560abbec146dde4b584ea0d4d7df8c27f16957e630a440e92db5a1c`. Solo se agregó el manifiesto trasladado bajo `metadata/`.
- Biblioteca: **28/28** fuentes coinciden con `references/catalog.yaml`; **3/3** alias `identical_content_to` tienen el mismo hash que su referencia.
- Enlaces Markdown locales: **154/154** destinos existentes, **0 rotos**, incluidos los enlaces al manifiesto y al único log conservado.
- Suite V1+V2 completa: **286 passed, 0 failed, 0 errors, 0 skipped** (pytest 9.1.1, Python 3.12.10; 267.11 s). Se usó el ajuste de ACL `0700` y nombres `tmp_path` cortos únicamente dentro del proceso de pytest, como documenta la línea base. La comprobación de hashes y enlaces anterior se repitió después de la suite con el mismo resultado.

No hubo cambios de formulaciones ni de resultados científicos. La presencia de una fixture compatible o una suite verde no implica validación física adicional.
