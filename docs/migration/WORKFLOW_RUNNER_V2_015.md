# V2-015 — runner secuencial y validación del DAG

**Estado:** ejecutada el 26 de septiembre de 2026.  
**Alcance:** planificación y ejecución secuencial sobre el catálogo semántico V2 00–12.  
**Fuera de alcance:** invalidación/reutilización por hashes V2-016, migración de Stage 01–03 V1 y handlers científicos nuevos.

## Diseño implementado

`workflow/runner.py` construye un `WorkflowDAG` desde `ModuleCatalog`. Al crear el DAG valida referencias, detecta ciclos y obtiene un orden topológico determinista por número visible e ID semántico. Una selección de uno o varios `module_id` se expande únicamente por sus dependencias requeridas transitivas; las dependencias condicionales no se activan sin una decisión/configuración posterior que las haga requeridas.

La operación `WorkflowRunner.plan()` es un dry-run: no crea temporales ni rutas de salida. Devuelve el orden de ejecución y, por módulo:

- `ready`: existe handler V2 y sus dependencias requeridas están listas;
- `not_implemented`: el módulo pertenece al catálogo pero no tiene handler registrado;
- `blocked`: existe handler, pero al menos una dependencia requerida no está lista;
- motivo y dependencias directas requeridas.

`workflow/registry.py` mantiene el registro de handlers separado del catálogo arquitectónico. El catálogo conserva los trece módulos, pero el registro por defecto contiene solamente `project_objectives`, la implementación mínima aprobada en V2-011. En particular, no se registraron implementaciones ficticias para Hazard, Materials, Sections ni otros módulos 01–12.

## Ejecución y publicación

`WorkflowRunner.run()` consume `RunContext`, entrega a cada handler sus `StageResult` upstream y conserva estados separados para ejecución, calidad numérica, aplicabilidad y aceptación. Los doubles de prueba devuelven `HandlerOutput`, que combina un `StageResult` con bytes en memoria para los `ArtifactManifest` declarados; antes de publicar se validan identidad de módulo, URI declarada y SHA-256.

La semántica del runner es:

- un módulo sin handler produce `execution_status=not_implemented`, nunca `completed`;
- una excepción o salida inválida de un handler produce `failed`;
- un resultado upstream distinto de `completed` produce `blocked` en sus dependientes;
- los resultados completados antes de un fallo permanecen en el resultado de la ejecución sin ser reclasificados;
- `completed` no modifica `performance_acceptance`; puede permanecer `not_evaluated`;
- solo una ejecución cuyos módulos terminaron todos en `completed` se entrega a `TransactionalPublisher`;
- la promoción usa exclusivamente la ruta V2 `project_id/design_revision/case_id/run_id` y conserva la inmutabilidad de una corrida publicada.

El runner no busca archivos mediante glob en `outputs/`. Sus artefactos provienen exclusivamente de la salida explícita del handler y se escriben dentro de la transacción V2-014. Una planificación, una corrida fallida o una corrida con módulos no implementados no publica resultados parciales ni toca `outputs/stage_01`, `stage_02` o `stage_03`.

## Cobertura añadida

Se añadieron 14 tests de infraestructura en `tests/contracts/test_v2_workflow_runner.py` para:

- DAG válido, ciclo y dependencia inexistente;
- orden topológico determinista;
- selección parcial, selección múltiple y dependencia transitiva;
- separación catálogo/registro y módulo conocido no implementado;
- estados `ready`, `not_implemented` y `blocked` con motivos;
- fallo upstream, bloqueo downstream y preservación del resultado previo;
- `completed` sin aceptación implícita;
- dry-run sin efectos de filesystem;
- integración con publicación transaccional, dos `run_id` aislados e inmutabilidad por colisión;
- conservación de un centinela de outputs V1.

Los handlers usados para probar la infraestructura son doubles. No representan migración de capacidades científicas.

## Evidencia de tests

La suite específica terminó con **14 passed, 0 failed, 0 errors, 0 skipped**. La suite completa V1+V2 recolectó 220 casos y terminó así:

| Resultado | Cantidad |
|---|---:|
| Passed | 214 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

Comandos y resultados:

```text
python -m pytest tests/contracts/test_v2_workflow_runner.py -q -ra
14 passed in 0.32s

python -m pytest -q -ra
214 passed, 6 skipped in 35.89s
```

Cada omisión de la suite completa fue reportada individualmente:

| Test omitido | Razón |
|---|---|
| `test_installed_entrypoint_discards_cli_arguments[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |
| `test_exe_defaults[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_exe_defaults[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_exe_defaults[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |

Las seis omisiones pertenecen a la caracterización V1 de entrypoints instalados. No hubo skips V2, fallos ni errores de colección o preparación.
