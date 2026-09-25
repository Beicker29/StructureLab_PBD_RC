# V2-008 — Publicación y fallos controlados de V1

**Estado:** caracterización ejecutada el 25 de septiembre de 2026. Pruebas: [test_v1_publication.py](../../tests/test_characterization/test_v1_publication.py). Se usaron árboles temporales exclusivos, con un centinela previo de la etapa activa y otro de una etapa distinta. No se modificaron `outputs/stage_0x/` ni las fixtures científicas V2-004 a V2-006.

## Inventario y huellas de los centinelas

| Contenido | Uso | SHA-256 |
|---|---|---|
| `previous-scientific-result` | Archivo previo en etapa/caso activo | `f7265c947bcbc8a753d476a17e6d6b37af4b9cd9ffa15716ac5074538a0a43d1` |
| `other-stage-result` | Archivo de otra etapa | `12ff335a81632e7ee947e1c0f3cf4a35b1d514908d909fff07b2b8ff8b05e862` |
| `other-case` | Archivo del caso inactivo Stage 01 | `2c572c9ea06c7a73d0ff720e9b9b8de53ee1c3f54eb82c4350c778e9bfe9da38` |
| `partial` | Escritura parcial inyectada | `9834a14ab9bcaa0f6a8da71073617eac8f004e596a3fa11d807b84631b825d9d` |
| `new` | Árbol promovido Stage 02 | `11507a0e2f5e69d5dfa40a62a1bd7b6ee57e6bcd85c67c9b8431b36fff21c437` |

Cada test calcula SHA-256 del contenido **antes** y **después** para los archivos que deben sobrevivir. El inventario posterior se comprueba por existencia/ausencia de los archivos del caso, etapa, temporal y respaldo. Los archivos de salida normales, cuando se llega a generarlos, se identifican por ruta y no se confunden con una fixture numérica congelada.

## Matriz de fallos observados

| Etapa y punto | Resultado previo en la misma etapa/caso | Otra etapa / otro caso | Estado parcial y rollback |
|---|---|---|---|
| 01, validación antes de reset | Sobrevive con hash idéntico | Sobrevive | `prepare_stage_from_config` puede haber creado directorios; no hay reemplazo del caso. |
| 01, al comenzar cálculo después del reset | Se pierde | Otra etapa y caso inactivo conservan hash | Quedan carpetas vacías del caso activo; no hay rollback. |
| 01, durante escritura CSV inyectada | Se pierde | Ambas sobreviven con hash idéntico | Queda `data/partial.csv`; no existe manifiesto final de corrida. |
| 01, fallo al escribir JSON final | Se pierde | Ambas sobreviven con hash idéntico | Ya existen CSV/XLSX/TXT/figuras/reportes del caso, pero falta `stage_01_results.json`; no hay rollback. |
| 02, preparación del modelo antes de staging | Sobrevive con hash idéntico | Sobrevive | La evaluación se hace antes de crear el temporal. |
| 02, escritura parcial en `.stage_02-*` | Sobrevive con hash idéntico | Sobrevive | El `except` elimina el temporal; la etapa publicada no cambia. |
| 02, fallo de promoción tras mover la etapa antigua a `.bak-stage_02-*` | Se restaura con hash idéntico | Sobrevive | El respaldo vuelve a `stage_02`, y el temporal se elimina. Probado con `shutil.move` inyectado para fallar. |
| 02, fallo limpiando respaldo **después** de promoción | El árbol anterior ya no es el publicado | Sobrevive | El árbol nuevo es visible, el anterior permanece en `.bak-stage_02-*`, y `run` reportaría error. No hay rollback posterior a promoción. |
| 03, validación antes de reset | Sobrevive con hash idéntico | Sobrevive | La preparación puede crear `data/`; no reemplaza el árbol anterior. |
| 03, cálculo después de reset | Se pierde todo `stage_03` anterior | Otra etapa sobrevive con hash idéntico | El nuevo árbol solo tiene estructura parcial; no hay rollback. |
| 03, escritura CSV inyectada | Se pierde todo el árbol anterior | Sobrevive | Queda `partial.csv` en la hoja activa; no hay rollback. |
| 03, fallo de JSON agregado tras procesar la hoja | Se pierde todo el árbol anterior | Sobrevive | La hoja conserva CSV/YAML/figuras/resultados por hoja, pero falta `stage_03/data/stage_03_results.json`. |

Stage 01 elimina la carpeta del caso activo y carpetas heredadas a nivel de etapa, conservando el otro caso actual. Stage 02 reemplaza el **árbol completo** de `stage_02`, no solo el caso habilitado: un caso ajeno preexistente dentro de esa etapa se perdería tras una promoción exitosa. Stage 03 elimina el árbol completo antes de procesar hojas. La suite de integración V1 ya comprueba reemplazos correctos; estos tests añaden cortes controlados de la secuencia.

En Windows, los movimientos/reemplazos pueden fallar por archivos bloqueados o permisos. Se probó el rollback ante una excepción Python de promoción, no una interrupción del proceso, caída del sistema ni dos escritores concurrentes. La limpieza fallida del respaldo demuestra que una excepción después de promover no equivale a transacción completa. Son **políticas y defectos legados registrados**, no garantías de publicación V2. El aislamiento por caso, la recuperación y la concurrencia pertenecen a V2-014 y posteriores.
