# V2-005 — Línea base de materiales V1

**Estado:** cuatro configuraciones habilitadas ejecutadas juntas en una raíz aislada y comparadas con `outputs/stage_02/`; sin cambios de modelos. La ejecución está en [el log canónico](canonical_run_v1.log). El [manifiesto de fixtures](../../tests/fixtures/v1/materials/manifest.json) conserva parámetros, métricas, puntos notables, procedencia y estados; los CSV/YAML científicos completos están junto a él.

## Inputs y alcance

| Modelo | JSON canónico | SHA-256 |
|---|---|---|
| `Mon_Mander1988` | `configs/stage_02/confined_concrete/monotonic/Mon_Mander1988.json` | `f15e494be1c496e2a30e8c02432292fe3d28f911dcda4d6b0428ab7b9e91b032` |
| `Mon_RDM2019` | `configs/stage_02/ductile_reinforcing_steel/monotonic/Mon_RDM2019.json` | `dba8a6e78c58974838bca7601201e14690faafd6270625231bff16bc995f5d3b` |
| `Cyc_MP` | `configs/stage_02/nonductile_reinforcing_steel/cyclic/Cyc_MP.json` | `ca97e22b5c4a14fe5dfe7f2ef5c4a55dc2c566f10bca4ac67` |
| `Mon_MRO` | `configs/stage_02/nonductile_reinforcing_steel/monotonic/Mon_MRO.json` | `bb5974e305c9f91870b4f986967ce1df2c8f05890a229d341a953a268b0aa9c9` |

Los cuatro se resolvieron bajo `project_id=Modelos_constitutivos`, `case_id=COL75X75FC28MPa`. El catálogo científico usado como inventario de procedencia fue `references/catalog.yaml`, SHA-256 `c67c37873cb2efc9707bfdebd4b79789d20ff84a7a1f3c82fba71c5e964929f6`. Cada reporte conserva su fuente, cita, ubicación declarada y estado de calibración; el catálogo aún requiere curaduría bibliográfica, por lo que no se infiere validación experimental a partir de la existencia de un PDF.

Las unidades nativas son **mm**, **MPa** y deformación **mm/mm**; la tangente es MPa por deformación adimensional. Mander declara `compression_positive_tension_negative`, de modo que su rama de tracción tiene deformación y esfuerzo negativos. Las curvas de acero usan tracción positiva y compresión negativa cuando esa rama existe. `Mon_MRO` genera solo tracción y declara compresión `unsupported`; no se inventó una rama comprimida.

| Modelo | Estado / warnings | Filas de `curve.csv` | σ mínima / máxima [MPa] | Reversiones | Calibración declarada |
|---|---|---:|---:|---:|---|
| `Mon_Mander1988` | `completed` / ninguna | 801 | −3,28 / 41,83544034212139 | 0 | `source_equation_validation_case` |
| `Mon_RDM2019` | `completed` / ninguna | 1203 | −469,44635705937594 / 659,74 | 0 | `source_equation_application_case` |
| `Cyc_MP` | `completed` / ninguna | 241 | −510,40018403534896 / 540,0557866277463 | 4 | `synthetic_algorithm_verification_only` |
| `Mon_MRO` | `completed` / ninguna | 201 | 0 / 573 | 0 | `source_reported_monotonic_profile` |

No hubo puntos fuera de dominio, estados de falla ni warnings por fila en estos cuatro ejemplos. El CSV conserva, en orden, `step`, `strain`, `stress_mpa`, `tangent_mpa`, rama, sentido de carga, estado de tensión/compresión, restricción de pandeo, inversiones, dominio, falla, política de compresión, estado histórico y procedencia. Mander contiene 400 puntos de tracción, origen y 400 de compresión. RDM contiene 401 puntos en flexión, 401 en compresión pura y 401 de tracción de referencia. Cyc_MP mantiene el orden temporal y los puntos repetidos de su historia; no debe ordenarse por deformación al comparar.

## Controles numéricos característicos

- **Mander:** `f_l=2,3859465162001263 MPa`, `f_cc=41,83545529270206 MPa`, `epsilon_cc=0,006941234033107877` y `epsilon_cu=0,025669879898120283`. La configuración conserva `Ec` y `f_t` explícitos y el criterio último simplificado declarado; la tensión negativa no se cambia de signo.
- **RDM:** en flexión, `n=2`, `L/D=8,998875140607424`, `epsilon_i=0,02427542406760927`, `epsilon_ii=0,04981277612485804` y esfuerzo último de compresión de magnitud `174,2792443611055 MPa`. En compresión pura, `n=3`, `L/D=13,498312710911135`, `epsilon_i=0,0168`, `epsilon_ii=0,03550384973178559` y magnitud última `94,06 MPa`. Los dos conjuntos completos de restricción están en el manifiesto.
- **Mon_MRO:** la idealización ASCE/FEMA está `converged`; `f_y_effective=518,4452190438088 MPa`, `epsilon_y_effective=0,002592282449716289`, área real `4,441599976301571` y bilineal `4,441675868614375`, error relativo absoluto `1,7086705963806695e-05`. Ese `f_y_effective` es salida de idealización, no parámetro de entrada de la ecuación.
- **Cyc_MP:** deformaciones de −0,004 a 0,008 con cuatro reversiones. La etiqueta `synthetic_algorithm_verification_only` se preserva literalmente: verifica el algoritmo, no calibra un acero de edificación.

## Artefactos, comparación y límites

Se copiaron **cinco CSV** (`curve.csv` por modelo y la bilineal de Mon_MRO) y **ocho YAML** de parámetros/métricas a `tests/fixtures/v1/materials/stage_02/`, con hashes normalizados, columnas y número de filas en el manifiesto. Los cinco XLSX generados tienen una hoja cada uno y sus celdas coinciden con los CSV y los XLSX históricos; se registró el esquema sin copiar el binario. Los cuatro `resolved_inputs.json` y cuatro `model_report.yaml` constan como esquema; los campos científicos de los reportes se normalizaron al manifiesto, sustituyendo la ruta absoluta de `source_json` por la ruta relativa al repositorio.

Los **13 archivos científicos textuales** nuevos son iguales a los históricos; también coinciden estado, inputs resueltos, parámetros, métricas, puntos notables, base técnica y warnings de los cuatro reportes. Los **13 artefactos de presentación** (nueve PNG y cuatro PDF de Matplotlib) se inventariaron sin copiarlos ni usar identidad binaria como oráculo. Los 39 archivos históricos Stage 02 conservaron sus hashes de V2-002.

Esta captura fija las respuestas actuales, incluidas sus convenciones y limitaciones. No prueba que los cuatro materiales pertenezcan a la sección del libro M–φ ni valida experimentalmente el perfil sintético. La [suite completa posterior](pytest_v2_004_006.log) terminó con **120 passed**. No se corrigieron formulaciones o defectos y no se ejecutaron V2-007 a V2-009.
