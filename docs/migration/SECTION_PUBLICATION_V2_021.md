# V2-021 — presentación y publicación V2 de caracterización de secciones

**Estado:** ejecutada el 26 de septiembre de 2026.  
**Alcance:** handler V2 de `section_component_characterization`, presentación desacoplada y publicación transaccional de curvas M–φ externas caracterizadas por V2-020.  
**Fuera de alcance:** V2-022 y posteriores, motor nativo de fibras, equilibrio axial, generación nativa M–φ, interacción P–M, rotaciones plásticas, rótulas y modelos histeréticos de componentes.

## Capacidad del workflow

El registro por defecto incorpora `section_component_characterization` con identidad visible 04. Su DAG mínimo es:

```text
project_objectives → section_component_characterization
```

`baseline_model` y `material_characterization` permanecen como dependencias condicionales del catálogo. No se ejecutan ni se simulan para caracterizar una curva externa. El handler exige:

- `ProjectSpec` y `RunContext` consistentes;
- configuración estructurada de esquema 2;
- hojas y filas ya importadas en memoria;
- hash `section_configuration` coincidente con la configuración resuelta;
- referencia del proyecto con el mismo hash;
- procedencia V2-016 completa.

El importador queda fuera del cálculo científico. En la regresión, el lector XLSX V1 se usa antes de construir el `RunContext`; el handler nunca busca ni abre el libro. La ruta externa M–φ permanece válida, explícita y trazable aun cuando exista un futuro motor de fibras.

## Cálculo y artefactos científicos

El handler invoca exclusivamente `SectionCharacterizationService`. No contiene ecuaciones, selección de puntos últimos, reglas de corte ni bilinealización.

La publicación canónica contiene **221 artefactos** bajo:

```text
04_section_component_characterization/imported_m_phi/
```

El inventario es:

- un `resolved_input.json` con configuración y curvas estructuradas;
- diez `scientific_result.json`, uno por hoja;
- diez `warnings.json`;
- 140 tablas CSV/XLSX;
- 60 figuras PNG.

Cada resultado científico existe antes e independientemente de la presentación e incluye:

- curva fuente y ramas detectadas;
- resultados `monotonica` y `ciclica` completos;
- puntos últimos y cortes;
- `phi_u`, `Mu`, `phi_y`, `My`, `Ke`, áreas y error;
- estados `converged`/`best_effort` y warnings;
- configuración, unidades, signos, ejes y procedencia.

Los manifiestos declaran curvatura `1/m`, momento `kN-m`, rigidez `kN-m²` y área `kN`. Curvatura y momento conservan orientación y signo en el sistema local de la sección; no hay conversión ni normalización silenciosa.

## Presentación desacoplada

`presentation/section_characterization.py` recibe únicamente `SectionSheetResult` ya calculados. Produce, por hoja y modo:

- tablas de curva real, curva bilineal y parámetros en CSV/XLSX;
- tabla de puntos de corte para `ciclica`;
- figuras de curva real, bilineal y comparación.

La capa no importa ni invoca kernels científicos, no selecciona puntos y no modifica el resultado. No genera PDF ni HTML.

Un fallo de tablas o figuras se registra como `presentation_failed`. Los JSON científicos previamente construidos siguen publicándose, pero `presentation_status=incomplete` y `metadata.incomplete=true` impiden reutilizar conservadoramente esa corrida.

## Semántica histórica y estados

La salida denominada `ciclica` conserva el nombre V1, acompañada por:

```text
response_semantics = truncated_or_reused_monotonic_backbone
is_hysteretic = false
```

No se añadieron descarga, recarga, disipación ni memoria cíclica.

La hoja `V1 (2-3)T` conserva el `best_effort` del ramal negativo. Por ello, el resultado Stage 04 es:

- `execution_status=completed`;
- `numerical_quality=best_effort`;
- `applicability=applicable`;
- `performance_acceptance=not_evaluated`.

La política V2-016 sigue rechazando `best_effort` por defecto. El registro de este handler autoriza explícitamente su reutilización cuando hashes, procedencia, dependencias, integridad y presentación también son válidos. Esa autorización QA no cambia el estado a `converged` y nunca implica `accepted`.

## Equivalencia, invalidación y aislamiento

El runner V2 procesó las diez hojas y comparó las 70 tablas CSV científicas contra V2-006. Se preservaron curvas, ramas, cortes configurados/automáticos/ausentes, parámetros, áreas, errores, warnings y estados. Los casos `enabled: false` y reutilización monotónica continúan cubiertos por la regresión V2-020.

Una segunda corrida idéntica reutiliza Stage 00 y Stage 04 mediante el índice explícito de manifiestos, sin invocar el servicio. Cambiar cualquiera de los siguientes elementos invalida el candidato:

- un valor de la curva estructurada;
- configuración de bilinealización;
- parámetro de corte.

También se prueba el rechazo de un hash declarado incorrecto antes de publicar. No se usa `glob` sobre `outputs/` para seleccionar candidatos.

La publicación se realiza exclusivamente mediante `TransactionalPublisher`, bajo `project_id/design_revision/case_id/run_id`. Stage 03 V1, `outputs/stage_03`, las fixtures, configuraciones y kernels científicos permanecieron intactos. No se escribió fuera de la raíz V2 aislada de prueba.

## Verificación

Las pruebas de servicio y publicación de secciones terminaron con **16 passed, 0 failed, 0 errors, 0 skipped**:

```text
python -m pytest tests/contracts/test_v2_section_service.py tests/contracts/test_v2_section_publication.py -q -ra
16 passed in 87.98s
```

La suite completa V1+V2 recolectó 283 casos:

| Resultado | Cantidad |
|---|---:|
| Passed | 277 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

```text
python -m pytest -q -ra
277 passed, 6 skipped in 132.37s
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
