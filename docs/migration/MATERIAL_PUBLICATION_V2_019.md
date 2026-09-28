# V2-019 — presentación y publicación V2 de materiales

**Estado:** ejecutada el 26 de septiembre de 2026.  
**Alcance:** handler V2 real de `material_characterization`, presentación desacoplada y publicación transaccional de un único conjunto de materiales.  
**Fuera de alcance:** V2-020 y posteriores, múltiples `material_set_id`, reporting integral PDF/HTML y cambios científicos en los kernels.

## Capacidad de workflow

El registro por defecto contiene ahora `project_objectives`, `site_hazard` y `material_characterization`. Al solicitar materiales, el DAG ejecuta únicamente:

```text
project_objectives → material_characterization
```

`baseline_model` permanece como dependencia condicional del catálogo y no se ejecuta ni se simula. El handler requiere:

- `ProjectSpec` consistente con el `RunContext`;
- referencia de configuración de `material_characterization` cuyo SHA-256 coincida con el input resuelto;
- un único `material_set_id` por corrida;
- una lista de instancias estructuradas con formulación, `parameter_set_id`, `material_instance_id` e inputs resueltos;
- artefacto Stage 00 completado y procedencia V2-016 suficiente.

No se admiten múltiples `material_set_id`; esa capacidad permanece reservada para V2-024.

El handler usa `MaterialEvaluationService`, fachada inyectable añadida al servicio V2-018. No contiene ecuaciones ni vuelve a implementar métricas, curvas, idealización o reglas de historia. Las cuatro instancias se evalúan una vez y el resto de la ejecución consume esos resultados estructurados.

## Fronteras nativas

Cada resultado publica fronteras V2-013 validadas para `strain`, `stress` y `tangent`:

| Resultado | Unidad | Convención |
|---|---|---|
| strain Mander | `mm/mm` | compresión positiva, tracción negativa |
| stress Mander | `MPa` | compresión positiva, tracción negativa |
| strain acero | `mm/mm` | tracción positiva, compresión negativa |
| stress acero | `MPa` | tracción positiva, compresión negativa |
| tangent | `MPa` | no aplicable |

El sistema de referencia es material uniaxial. No se normalizan signos ni se convierten unidades; toda conversión futura debe producir el artefacto trazable definido en V2-013.

## Artefactos

La ejecución canónica publica 36 artefactos de `material_characterization` bajo:

```text
03_material_characterization/<material_set_id>/<material>/<analysis_type>/<model_id>/
```

Cada modelo produce independientemente:

- `data/resolved_input.json`;
- `data/scientific_result.json` con formulación, parámetros, instancia, curva, tangente, métricas, puntos notables, warnings, estado, calibración, fronteras y estado cíclico cuando aplica;
- `data/metrics.json`;
- `data/notable_points.json`;
- `data/warnings.json`;
- `tables/curve.csv` y `tables/curve.xlsx`;
- `figures/response.png`.

`Mon_MRO` añade `data/idealization.json`, tablas CSV/XLSX y figura de idealización. El `fy` efectivo continúa siendo resultado de esa idealización, nunca input constitutivo.

Todos los artefactos tienen `ArtifactManifest`, hashes de contenido, dependencias explícitas, unidades, signos, ejes y una firma común de procedencia. La firma incluye configuración resuelta, hashes de input y Stage 00, versión `material-kernels-v1+service-v2-018+publication-v2-019.1` y versión instalada de Matplotlib. `completed` conserva `performance_acceptance=not_evaluated`.

No se producen PDF ni HTML. El reporting integral permanece reservado para Stage 12.

## Presentación desacoplada

`presentation/material_characterization.py` recibe exclusivamente `MaterialEvaluationResult` ya calculados. Genera CSV/XLSX y PNG en memoria; no importa factories ni kernels y no modifica las estructuras científicas.

Los JSON científicos se construyen antes de invocar presentación. Si falla una tabla o figura:

- no se reinterpretan ni recalculan curvas;
- se conservan y publican los artefactos científicos disponibles;
- `numerical_quality` continúa describiendo sólo el cálculo;
- se registra `presentation_failed` y `presentation_status=incomplete`;
- el resultado sigue `completed` y no `accepted`;
- `metadata.incomplete=true` hace que V2-016 rechace su reutilización.

Así, una falla visual no corrompe la evidencia científica y tampoco se presenta conservadoramente como resultado reutilizable completo.

## Compatibilidad y reutilización

Los cuatro casos canónicos (`Mon_Mander1988`, `Mon_RDM2019`, `Mon_MRO` y `Cyc_MP`) se ejecutaron mediante el runner V2. Los JSON publicados se compararon con V2-005 para todas las filas de strain/stress/tangent, ramas, métricas, puntos notables, warnings, idealización y calibración. `Cyc_MP` conserva literalmente `synthetic_algorithm_verification_only`.

Una segunda corrida con la misma identidad científica reutiliza Stage 00 y Stage 03 mediante manifiestos y hashes explícitos, sin invocar `MaterialEvaluationService`. Cambiar un parámetro invalida la cadena. No se usan glob sobre `outputs/` para localizar candidatos; la selección continúa mediante `PublishedRunIndex`.

La publicación usa exclusivamente `TransactionalPublisher` bajo `project_id/design_revision/case_id/run_id`. Las fixtures, `outputs/stage_02` y la publicación/reporting V1 permanecieron intactos.

## Verificación

Las pruebas específicas de V2-019 terminaron con **8 passed, 0 failed, 0 errors, 0 skipped**:

```text
python -m pytest tests/contracts/test_v2_material_publication.py -q -ra
8 passed in 7.67s
```

La suite completa V1+V2 recolectó 267 casos:

| Resultado | Cantidad |
|---|---:|
| Passed | 261 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

```text
python -m pytest -q -ra
261 passed, 6 skipped in 47.34s
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
