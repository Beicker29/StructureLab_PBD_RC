# Cierre de migración V1→V2 — Frente 1

**Fecha:** 28 de septiembre de 2026. **Alcance:** packaging, CLI instalada, documentación, biblioteca de referencias, auditoría de limpieza y verificación de las capacidades ya migradas. Este cierre no inicia el Frente 2 ni cambia formulaciones, kernels, fixtures científicas o salidas históricas V1.

## Resultado y capacidades

La arquitectura de trece módulos 00–12 y sus IDs semánticos permanece vigente. La [matriz de arquitectura](../ARCHITECTURE_V2.md) es la referencia del estado ejecutable. Actualmente tienen handler V2 `project_objectives`, `site_hazard`, `material_characterization` y `section_component_characterization`. El último caracteriza curvas M–φ externas; no es un motor de fibras. `baseline_model`, `ground_motion`, `nonlinear_model`, `nonlinear_analysis`, `demand_performance`, `collapse_fragility`, `damage_loss`, `seismic_risk` y `reporting_iteration` carecen de handler operativo. El catálogo/DAG los identifica y la CLI los muestra como `not_implemented` o `blocked`; no publica resultados ficticios.

La conversión V1→V2 conserva los inputs de Stage 01, los cuatro modelos de Stage 02 y las diez hojas importadas por Stage 03. Requiere un YAML de decisiones para sitio, objetivos, revisión e identidad y confirmación explícita de asociaciones que V1 no demuestra. Preview no escribe; `--write` crea `ProjectSpec`, configuraciones V2 y procedencia con SHA-256 en un destino nuevo. `workflow plan` verifica referencias sin publicar; `workflow run` invoca solo `WorkflowRunner` y `TransactionalPublisher`. El significado de `stage_01/02/03` V1 no cambia y los `outputs/stage_0x` no se migran. La [guía V1→V2](COMPATIBILITY_CLI_V2_023_025.md) contiene formato, comandos y códigos de salida.

## Packaging y CLI instalada

`pyproject.toml` declara `setuptools>=68` en `[build-system]` y `setuptools.build_meta` como backend; `pip` instala esa dependencia **en un entorno de build aislado**. `setuptools` no necesita estar preinstalado en el virtualenv de ejecución. Los entrypoints son `structurelab` y los tres `structurelab-stage-0x` heredados. No se cambió el backend: una instalación editable limpia lo validó efectivamente.

Se creó un virtualenv Python 3.12.10 nuevo, se habilitó `pip` y se ejecutó `pip install -e .` con aislamiento de build y dependencias, seguido de `pip install -e ".[dev]"`. La instalación terminó con `structurelab-pbd-rc 0.1.0`, Matplotlib 3.11.2, NumPy 2.5.3, PyYAML 6.0.3 y pytest 9.1.1. `pip show setuptools` confirmó que **no está instalado como distribución runtime** en ese entorno. Se probaron los ejecutables instalados:

- `structurelab workflow convert` en preview y escritura: siete archivos fuente V1, tres configuraciones V2 con hashes y un `project.yaml` nuevo;
- `structurelab workflow plan`: 00, 01, 03 y 04 en `ready`, sin crear la raíz de outputs;
- `structurelab workflow run`: 00, 01, 03 y 04 en `completed`, con manifiesto y publicación V2 aislada;
- `structurelab-stage-01`, `structurelab-stage-02` y `structurelab-stage-03`: los tres ejecutaron sus defaults con salida 0 en un directorio temporal que contenía copias de los inputs canónicos. Stage 03 procesó diez hojas y conservó el warning conocido de `best_effort`.

La comprobación anterior con `--no-build-isolation` fallaba porque ese virtualenv carecía de `setuptools`; usar esa opción anulaba precisamente el aislamiento que provee el requisito declarado. El primer intento offline en el entorno limpio tampoco pudo obtener `setuptools>=68` porque `PIP_NO_INDEX=1` y no había un wheel local; al habilitar acceso al índice para la instalación aislada, el build funcionó. Un despliegue offline necesitará un wheelhouse de requisitos de build y runtime, no una dependencia implícita del entorno previo.

Se verificó también `pip install .` **sin modo editable** en el mismo entorno limpio. El wheel normal instaló el paquete bajo `site-packages`, registró los cuatro `console_scripts`, y el ejecutable `structurelab` pudo planificar y publicar `site_hazard` desde un CWD distinto al checkout, con CSV idéntico a la fixture V1. `setuptools` siguió ausente del runtime.

## Regresión científica y resultados V1

En el entorno limpio se ejecutó el flujo instalado `convert → plan → run` para las tres capacidades migradas, en una raíz nueva. La verificación científica contrastó **150 CSV** con las fixtures congeladas: dos comparaciones de espectro, ocho curvas de materiales y 140 tablas de secciones (V1 y V2 frente a sus oráculos). También coincidieron métricas y warnings de los cuatro materiales, el warning de secciones y las diez hojas. La prueba de integración de la suite cubre además preview no destructivo, hashes, ambigüedades, estados reutilizable/invalido y ejecución desde otro CWD. Coincidencia numérica de estos ejemplos no certifica validez física para una edificación distinta.

La suite completa V1+V2 del entorno limpio terminó con **286 passed, 0 failed, 0 errors, 0 skipped**. Se ejecutó con el ajuste **solo dentro del proceso de pytest** que resuelve el ACL temporal `0700` y acorta nombres `tmp_path` en Windows. Los intentos históricos sin ese ajuste confundían fallos de preparación o el límite de rutas con regresiones; no se modificó código productivo para evitarlo.

Los 268 archivos rastreados de `outputs/stage_01`, `stage_02` y `stage_03` se volvieron a verificar contra los SHA-256 del [manifiesto V1](../../tests/fixtures/v1/metadata/BASELINE_MANIFEST_V2.json); no hubo diferencias. Las fixtures `tests/fixtures/v1/` permanecen intactas.

## Biblioteca científica y enlaces

`references/catalog.yaml` contiene **28 entradas** y coincide con los 28 archivos de fuente (23 PDF, dos XLSX y tres textos; se excluyen los `.gitkeep`). Se verificó el SHA-256 de cada archivo y los tres enlaces `identical_content_to`, que forman dos grupos de igualdad binaria. Todos los enlaces locales de Markdown/HTML revisados resuelven; la verificación previa registró 136 enlaces locales válidos y dos enlaces directos a la biblioteca. Ninguna fuente ni ruta se movió o eliminó. Igualdad de hash no sustituye curaduría bibliográfica: autoría, título, uso y pertinencia científica siguen marcados como pendientes en el catálogo.

## Auditoría de limpieza controlada

No se retiró ni se marcó como obsoleto mediante código ningún símbolo durante este cierre. Buscar consumidores internos no permite descartar consumidores externos de una API pública V1, y falta el reemplazo probado del reporte integral. La clasificación es:

| Candidato | Clasificación | Evidencia y decisión |
|---|---|
| `design/stages/stage_01/02/03`, `cli.run` y `structurelab-stage-0x` | **Conservar** | Compatibilidad V1 y salidas históricas; el defecto de forwarding de flags sigue registrado para una corrección separada |
| `reports/plots.py`, `reports/export_excel.py`, `stage_02_material_report.py`, `io/paths.py::ensure_stage_output_dirs` | **Conservar** | Usos directos en V1 y/o tests; V2 no los reemplaza para consumidores V1 |
| `io/paths.py::ensure_material_model_output_dirs` | **Deprecar propuesto; no aplicado** | Sin llamadas internas detectadas y ruta incompleta para multiproyecto; puede ser API externa, por lo que no cumple aún la prueba de ausencia de consumidores |
| `reports/report_builder.py::build_stage_report` | **Revisar posteriormente** | Stub que solo lanza error; importado por test de API, sin motor Stage 12 probado que lo sustituya |
| `core/registry.py::ModelRegistry` | **Revisar posteriormente** | Registro genérico sin consumidores internos salvo su reexportación pública; `workflow.registry.HandlerRegistry` tiene otra responsabilidad y no prueba equivalencia de API |
| `mechanics/geometry/sections.py::RectangularSection` | **Conservar** | Reexportación pública; geometría en cm; no usar como motor seccional V2 sin contrato nuevo |
| `mander_1988/equations.py::elastic_modulus_mpa` | **Conservar** | Helper científico sin llamadas internas; el modelo exige `Ec` explícito y no existe decisión para retirar o activar esa fórmula |
| Presentación repetida entre runners V1 y servicios V2 | **Revisar posteriormente** | Similaridad no demuestra equivalencia de API/salidas; retirar una rama rompería compatibilidad |
| PDF con contenido duplicado y carpetas `.gitkeep` | **Conservar** | Alias hash verificados; rutas históricas y tests aún los usan |

**Código eliminado:** ninguno. **Deprecaciones activadas:** ninguna. La condición de eliminación exigida por esta tarea —sin consumidores, innecesario para V1, reemplazo probado y suite verde— no quedó demostrada para ningún candidato; retirar símbolos ahora sería prematuro.

## Deuda y límite del cierre

El entrypoint V1 instalado ignora los flags CLI: incluso `--help` lanza el default. Queda como defecto de compatibilidad conocido, no se cambió en este cierre. Para argumentos V1 se usan los scripts `scripts/run_stage_0x.py` o `python -m structurelab_pbd_rc.cli.run stage_0x ...`. El conversor exige el directorio completo Stage 02 y un solo `material_set_id`; no infiere vínculos físicos entre ejemplos. Si falla el disco durante `--write`, puede quedar un destino V2 nuevo e incompleto, mientras los originales V1 permanecen intactos. El reporte integral 12 y el motor PDF/HTML siguen pendientes.

El **Frente 2** deberá tratar, mediante Issues separadas, modelo base 02; motor nativo de fibras y componentes 04; adquisición/escalamiento/QA de registros 05; representación no lineal neutral y backends 06–07; EDP y aceptación 08; colapso/fragilidad 09; daño/pérdidas 10; riesgo 11 y reporting/iteración 12. También quedan para decisiones futuras importación probabilística OpenQuake/SGC, múltiples conjuntos materiales y curaduría bibliográfica. Ninguna de esas capacidades se implementó ni se presentó como operativa en este cierre.
