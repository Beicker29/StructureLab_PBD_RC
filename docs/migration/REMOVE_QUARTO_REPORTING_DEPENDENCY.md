# Issue V2-003R — Remove Quarto reporting dependency

**Estado:** implementada antes de V2-004, por decisión arquitectónica del 25 de septiembre de 2026. **Alcance:** retirar solo el renderizado Quarto/Typst de Stage 01. V2-004 a V2-009 no se ejecutaron.

La generación de espectros de Stage 01 llamaba a Quarto para renderizar un PDF después de escribir CSV, XLSX, TXT ETABS, figuras y el YAML del caso. En el entorno de línea base, cuatro tests de integración terminaban con `FileNotFoundError` por ausencia de Quarto aunque no detectaban diferencias numéricas. El cálculo y la entrega de datos ya no requieren un generador de PDF.

## Inventario y decisión

| Ubicación | Dependencia encontrada | Decisión |
|---|---|---|
| `src/structurelab_pbd_rc/reports/export_quarto.py` | Descubrimiento y ejecución del binario `quarto`, destino Typst y limpieza de intermedios | Eliminar el módulo exclusivo del renderer |
| `src/structurelab_pbd_rc/reports/stage_01_hazard_report.py` | Construcción de QMD, copia de figuras al documento y llamada a render PDF | Eliminar el módulo exclusivo de esa memoria; las figuras originales y el YAML permanecen |
| `src/structurelab_pbd_rc/design/stages/stage_01_hazard.py` | Llamada obligatoria al PDF en los dos casos y escritura anticipada de YAML para alimentarla | Quitar la llamada; escribir el YAML estructurado una vez, tras producir los datos |
| `tests/test_stages/test_stage_01.py` | Dos expectativas QMD y dos PDF dentro de tests de integración numérica | Conservar los cuatro tests y sus aserciones numéricas/de artefactos; reemplazar solo esas expectativas por la ausencia de salidas QMD/PDF nuevas |
| Scripts, CLI y dependencias Python | No había llamada directa desde scripts ni paquete Quarto/Typst en `pyproject.toml`; dependían indirectamente del `run()` de Stage 01 | No cambiar interfaces ni dependencias Python |
| `docs/MIGRATION_PLAN_V2.md`, `docs/BASELINE_TASKS_V2.md`, `docs/migration/BASELINE_STATUS_V2.md`, `AGENTS.md` | Descripciones del renderer anterior y del bloqueo de línea base | Actualizar estado y conservar la evidencia histórica |

Los PDF de materiales se generan con Matplotlib y no dependen de Quarto. Los PDF y QMD ya presentes en `outputs/stage_01/` son históricos: no se borran ni reescriben. En **corridas nuevas** de Stage 01 desaparecen las claves `*_report_qmd` y `*_report_pdf` de `generated_files`, los QMD/PDF y las copias de figuras en `reports/<case_id>/assets`; es una diferencia intencional limitada a presentación. Permanecen `*_report_yaml`, CSV/XLSX, TXT ETABS, figuras originales, `stage_01_results.json`, rutas de casos y convenciones de unidades/signos. No se crea un renderer sustituto. El motor y formato final de reporting se decidirán durante el módulo 12.

## Validación

- [Suite completa](pytest_remove_quarto.log): **120 passed**, 0 failed, 0 setup errors, 0 skipped, usando la raíz temporal corta y el ajuste de permisos limitado al proceso documentados en [el estado de línea base](BASELINE_STATUS_V2.md).
- Se compararon los 20 CSV/TXT de los tests Stage 01 que existían tanto en la corrida anterior como en la nueva: **contenido binario idéntico**. Los cinco CSV/TXT adicionales pertenecen a la segunda ejecución del test de escalamiento, que antes se detenía al intentar renderizar el primer PDF.
- Se compararon los campos `stage_id`, `case_id`, `title`, `datos_de_entrada` y `datos_de_salida` de los cuatro YAML de Stage 01 disponibles en ambas corridas: **sin diferencias semánticas**. `generated_files` cambia solo por la retirada de salidas del renderer y por las raíces temporales.
- El manifiesto V2-002 conserva la identidad y hashes de los resultados históricos; no se ejecutaron los YAML canónicos para crear fixtures ni se modificaron `outputs/stage_01`, `outputs/stage_02` o `outputs/stage_03`.

Esta Issue no valida todavía el contenido de los dos casos canónicos ni el formato ETABS como fixtures. Ese trabajo sigue reservado a V2-004.
