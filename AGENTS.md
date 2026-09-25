# Instrucciones del repositorio para agentes

## Propósito y estado

`StructureLab_PBD_RC` está en transición hacia un orquestador PBSD/PBEE para edificaciones de concreto reforzado. Leer `docs/MIGRATION_PLAN_V2.md` y `docs/BASELINE_TASKS_V2.md` antes de planificar cambios de migración. La arquitectura aprobada tiene módulos visibles 00–12 con IDs semánticos. Las capacidades actuales son amenaza espectral, caracterización de cuatro modelos de materiales e idealización de curvas M–φ importadas.

V2-001 a V2-009 y la Issue independiente V2-003R de retirada de Quarto/Typst ya se ejecutaron y documentaron. V2-010 y posteriores permanecen sin ejecutar; no anticipar movimientos de fuentes ni refactorizaciones.

## Límites de la arquitectura

- Mantener cálculos y modelos reutilizables en `mechanics/`; la orquestación coordina lectura, validación, ejecución y publicación.
- Conservar la semántica V1 de `stage_01` (amenaza), `stage_02` (materiales) y `stage_03` (secciones importadas). La numeración V2 02 y 03 significa otra cosa: usar versión de esquema e ID semántico para evitar ambigüedad.
- Stage 01 distingue espectros normativos de resultados probabilísticos de OpenQuake/SGC. Los casos actuales no proporcionan por sí solos curvas de tasas de excedencia.
- Stage 04 debe incluir un motor nativo de análisis seccional por fibras. Conservar la importación Excel existente para compatibilidad y comparación documentada; no considerarla un motor de fibras.
- Stage 05 consta de Target Spectrum, External Record Acquisition, Amplitude Scaling, optional External Spectral Matching y Suite QA. Preservar originales, factores, transformaciones, unidades y procedencia.
- Stage 06 define y valida un modelo no lineal neutral respecto al solver antes de aplicar adaptadores de ETABS, Perform-3D u OpenSees. Una capacidad no soportada debe fallar explícitamente.
- Distinguir envolventes monotónicas, historias cíclicas, validez/calibración de materiales y criterios de falla. `Cyc_MP` canónico tiene parámetros sintéticos para verificar el algoritmo.
- Declarar unidades, signos, ejes y fuentes en las fronteras. No alterar resultados científicos sin pruebas y una decisión explícita sobre su versión.

## Fuentes y línea base

- `references/` es la biblioteca científica. `references/catalog.yaml` inventaría las rutas y hashes actuales. Completar su procedencia y verificar enlaces antes de cualquier reorganización física; conservar rutas originales hasta que existan alias comprobados.
- Tratar `outputs/stage_01`, `stage_02` y `stage_03` como resultados V1; no renumerarlos ni sobreescribirlos. Las fixtures V2-004 a V2-006 están bajo `tests/fixtures/v1/` y sus memorias en `docs/migration/`; proceden de salidas temporales aisladas.
- El ajuste ambiental limitado a pytest resolvió los errores de permisos de `tmp_path`. Tras V2-007 a V2-009, la suite completa pasó 169 tests; la corrida anterior de 120 tests y los resultados históricos de 104/16 y 116/4 permanecen en `docs/migration/BASELINE_STATUS_V2.md`.
- Stage 01 conserva YAML, CSV/XLSX, TXT ETABS y figuras; su cálculo no depende de PDF. No reinstalar Quarto ni introducir otro renderer como arreglo implícito. El motor final de reporting se decidirá en el módulo 12. Separar pruebas de ecuaciones, contratos e integración; comparar valores, signos, estados, warnings y procedencia sin confundir coincidencia de archivos con validación física.

## Alcance de tareas preparadas

V2-001 a V2-009 están especificadas en `docs/BASELINE_TASKS_V2.md`; V2-003R tiene ficha independiente en `docs/migration/REMOVE_QUARTO_REPORTING_DEPENDENCY.md`. El resto de Issues del plan es backlog propuesto; las V2-031 a V2-039 describen el motor de fibras y su validación futura.
