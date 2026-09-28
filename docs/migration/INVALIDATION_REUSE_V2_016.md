# V2-016 — invalidación de dependencias y reutilización verificada

**Estado:** ejecutada el 26 de septiembre de 2026.  
**Alcance:** identidad de contenido, procedencia estable, invalidación transitiva y reanudación verificable sobre publicaciones V2.  
**Fuera de alcance:** migración de capacidades científicas V1, V2-017 y posteriores, y eliminación de resultados históricos.

## Identidad de contenido y procedencia

`ArtifactManifest.sha256` conserva la identidad de los bytes publicados y expone el alias explícito `content_hash`. Es independiente de `ProcessProvenance.signature`, que identifica el proceso productor mediante JSON canónico y SHA-256.

`ProcessProvenance` registra:

- `module_id` y `schema_version`;
- versión explícita de implementación/formulación;
- configuración resuelta estable;
- hashes declarados de inputs;
- hashes agregados de módulos requeridos;
- unidades y convenciones de signo relevantes;
- versión de backend externo, cuando existe.

La firma no incorpora `run_id`, timestamps, roots de ejecución ni rutas absolutas. Una ruta de input científicamente relevante debe representarse mediante su hash requerido; si falta un hash declarado como obligatorio, no existe evidencia suficiente para reutilizar.

## Índice explícito de candidatos

`PublishedRunReference` identifica exactamente:

```text
project_id / design_revision / case_id / run_id / manifest_sha256
```

`PublishedRunIndex` recibe esas referencias del llamador y las ordena determinísticamente por prioridad y `run_id`. No enumera directorios, no busca candidatos con `glob` y nunca cruza proyecto, revisión o caso. `TransactionalPublisher.published_reference()` genera una referencia únicamente desde el `manifest.json` de una identidad conocida.

Antes de considerar un módulo reutilizable se comprueba de forma explícita:

1. existencia y hash del manifiesto referenciado;
2. `publication_status=complete`, esquema compatible e identidad completa de corrida;
3. `StageResult` completados y declaraciones de artefactos coherentes;
4. existencia y `content_hash` de cada archivo declarado;
5. integridad de dependencias por ID/hash;
6. ausencia de marcas `corrupt` o `incomplete`;
7. firma de procedencia esperada;
8. política QA conservadora: calidad `converged` o `not_applicable` y aplicabilidad evaluada.

La falta de versión de implementación, firma, artefactos, hashes obligatorios o evidencia QA produce `invalidated`; nunca una reutilización optimista.

## Planificación, invalidación y reanudación

`workflow plan` conserva `ready`, `not_implemented` y `blocked`, y añade:

- `reusable`: contenido, procedencia, dependencias, esquema y QA verificados;
- `invalidated`: existía un candidato explícito, pero debe recalcularse.

Cada entrada incluye `reason_code`, mensaje legible y detalles estructurados. Si un upstream deja de ser reutilizable, sus dependientes requeridos quedan `invalidated` transitivamente. Un módulo invalidado se ejecuta normalmente durante la nueva corrida; un módulo reutilizable omite su handler y copia bytes verificados a la nueva transacción V2-014. La nueva publicación registra `reused_from` con la identidad y hash del manifiesto fuente.

Los resultados históricos no se modifican, renombran ni eliminan. La reanudación lee los archivos fuente y publica una corrida nueva e inmutable bajo su propio `run_id`. `completed` continúa separado de aceptación de desempeño.

## Cobertura añadida

Los 18 tests de `tests/contracts/test_v2_invalidation_reuse.py` usan exclusivamente handlers y artefactos sintéticos. Cubren:

- inputs idénticos y cadena completamente reutilizable sin invocar handlers;
- cambios de configuración, input hash y versión de implementación;
- invalidación transitiva por cambio o corrupción upstream;
- exclusión de `timestamp`, `run_id` y rutas absolutas operativas;
- ausencia de un hash de input obligatorio;
- `content_hash` incorrecto, manifiesto incompleto, esquema incompatible y artefacto ausente;
- rechazo por política QA;
- aislamiento entre proyectos, revisiones y casos;
- plan read-only sin descubrimiento por glob;
- conservación física de la corrida histórica y de outputs V1.

No se registraron handlers científicos para módulos 01–12 ni se migraron Stage 01, 02 o 03 V1.

## Evidencia de tests

La suite específica terminó con **18 passed, 0 failed, 0 errors, 0 skipped**. La suite completa V1+V2 recolectó 238 casos:

| Resultado | Cantidad |
|---|---:|
| Passed | 232 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

Resultado de la suite completa:

```text
python -m pytest -q -ra
232 passed, 6 skipped in 37.27s
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

Las seis omisiones pertenecen a la caracterización V1 de entrypoints instalados. No hubo skips V2, fallos ni errores de colección o preparación.
