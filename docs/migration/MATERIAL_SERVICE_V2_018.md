# V2-018 — servicio de evaluación de materiales preservando Stage 02 V1

**Estado:** ejecutada el 26 de septiembre de 2026.  
**Alcance:** extracción de la evaluación científica de los cuatro modelos V1 hacia una capa de servicio completamente en memoria.  
**Fuera de alcance:** V2-019 y posteriores, handler V2 `material_characterization`, publicación o presentación V2, cambios en reporting, rutas de outputs y modificaciones de formulaciones científicas.

## Servicio científico en memoria

`services/material_evaluation.py` expone `evaluate_material()` sobre los factories y kernels existentes en `mechanics/materials/`. No lee configuraciones, no escribe archivos y no importa CLI, gráficos, PDF, XLSX, reporting ni mecanismos de publicación.

Los contratos separan explícitamente:

- `MaterialFormulation`: identidad estable de la formulación (`Mon_Mander1988`, `Mon_RDM2019`, `Mon_MRO` o `Cyc_MP`), material y tipo de análisis;
- `MaterialParameterSet`: identidad y valores de un conjunto de parámetros;
- `MaterialInstance`: instancia material que enlaza formulación, parámetros y procedencia;
- `MaterialEvaluationInput`: caso, unidades nativas y protocolo de evaluación;
- `MonotonicMaterialEvaluation`: curva y resultados sin API de historia;
- `CyclicMaterialEvaluation`: historia evaluada y estado final confirmado;
- `CyclicMaterialSession`: estado privado por instancia con `set_trial_strain`, `commit_state`, `revert_to_last_commit` y `reset`.

La historia de deformaciones y su interpolación pertenecen al protocolo de evaluación, no al conjunto de parámetros constitutivos. Cada sesión cíclica construye una instancia independiente del kernel y no comparte estado mutable con otra evaluación.

Stage 02 V1 adapta sus inputs ya resueltos a `MaterialEvaluationInput` y consume el resultado en memoria. Su carga de configuración, narrativa técnica, gráficos, PDF, XLSX, escritura y reemplazo transaccional V1 permanecen en la etapa existente. La estructura de outputs no fue modificada.

## Compatibilidad científica

El servicio selecciona las formulaciones mediante los factories existentes:

| Modelo | Factory existente | Resultado |
|---|---|---|
| `Mon_Mander1988` | `build_confined_concrete_model` | 801 puntos, tracción negativa y compresión positiva |
| `Mon_RDM2019` | `build_ductile_steel_model` | 1203 puntos, casos de restricción y ramas de tracción/compresión |
| `Mon_MRO` | `build_nonductile_steel_model` | 201 puntos y posterior idealización bilineal energética |
| `Cyc_MP` | `build_nonductile_steel_model` | 241 puntos históricos, puntos repetidos y cuatro reversiones |

Se preservan las unidades nativas `mm`, `MPa` y `mm/mm`. El servicio rechaza otras unidades: toda conversión V2 debe realizarse fuera del cálculo mediante las fronteras de V2-013. No se normalizan signos ni outputs V1.

Para `Mon_MRO`, `f_y_effective` permanece exclusivamente dentro del resultado de la idealización FEMA/ASCE. No existe `fy_MPa` entre los inputs de la formulación. El caso congelado converge a `f_y_effective = 518.4452190438088 MPa`.

Para `Cyc_MP`, tanto la procedencia de la instancia como las métricas y filas conservan literalmente `synthetic_algorithm_verification_only`. No se atribuye calibración experimental a sus parámetros.

## Regresión V2-005 y preservación V1

`tests/contracts/test_v2_material_service.py` compara directamente el resultado en memoria con `tests/fixtures/v1/materials/`:

- todas las deformaciones, esfuerzos, tangentes, ramas, direcciones, signos y puntos repetidos de los cuatro CSV;
- todos los parámetros calculados y métricas congelados;
- estados, warnings y puntos notables;
- idealización bilineal y `fy` efectivo de `Mon_MRO`;
- metadata sintética y estado final de `Cyc_MP`;
- operaciones trial/commit/revert/reset y aislamiento entre dos sesiones;
- dos evaluaciones monotónicas independientes;
- ausencia de archivos creados por el servicio;
- hashes intactos de fixtures y `outputs/stage_02` históricos;
- publicación V1 en un temporal, cuyos CSV/YAML científicos coinciden byte a byte con V2-005;
- ausencia de `material_characterization` en el registro V2 por defecto.

No se registró handler, no se agregó publicación/presentación V2 y no se ejecutó V2-019.

## Verificación

Las pruebas específicas terminaron con **13 passed, 0 failed, 0 errors, 0 skipped**:

```text
python -m pytest tests/contracts/test_v2_material_service.py -q
13 passed in 7.16s
```

La suite completa V1+V2 recolectó 259 casos:

| Resultado | Cantidad |
|---|---:|
| Passed | 253 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

```text
python -m pytest -q -ra
253 passed, 6 skipped in 109.91s
```

Cada omisión fue reportada individualmente:

| Test omitido | Razón |
|---|---|
| `test_installed_entrypoint_discards_cli_arguments[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |
| `test_exe_defaults[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_exe_defaults[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_exe_defaults[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |

Las seis omisiones pertenecen a pruebas V1 de entrypoints instalados. No hubo skips V2, fallos, errores de colección ni errores de preparación.
