# V2-010 a V2-012 — catálogo y contratos iniciales

**Estado:** ejecutadas.
**Alcance:** catálogo V2, núcleo mínimo de Stage 00 y contratos de contexto, artefactos y resultados.
**Fuera de alcance:** V2-013 y posteriores; política dimensional, publicación, runner/DAG, invalidación, conversión V1→V2 y cambios científicos.

## V2-010 — catálogo de módulos

Se incorporó `workflow/catalog.py` como catálogo operativo único de los trece módulos. Cada entrada separa `module_id` semántico estable de `stage_number` visible entre `00` y `12`. El catálogo valida unicidad case-insensitive, versiones, dependencias conocidas y coherencia del namespace.

Los aliases `stage_01`, `stage_02` y `stage_03` no se resuelven como V2. En particular, se rechazan explícitamente porque `stage_02` y `stage_03` conservan sus significados V1. La selección V2 admite el ID semántico o el número visible de dos dígitos.

## V2-011 — ProjectSpec y Stage 00

Se incorporó `contracts/project.py` con `ProjectSpec` y contratos anidados para:

- sitio;
- unidades base declaradas, sin conversiones ni política dimensional;
- niveles de amenaza;
- objetivos de desempeño;
- referencias a configuraciones, inputs, criterios y fuentes.

El contrato exige `schema_version`, `project_id`, `design_revision` y `case_id`, valida IDs duplicados y referencias internas y soporta round-trip dict/JSON. `workflow/stages/project_objectives.py` implementa la frontera mínima de Stage 00: confirma un contrato válido, pero no introduce ni evalúa criterios normativos.

## V2-012 — contexto, artefactos y resultados

Se incorporaron:

- `RunContext`, con identidad de corrida, proyecto/caso/revisión, raíz absoluta, versión de código, entorno, configuración resuelta y política de publicación declarada;
- `ArtifactManifest`, con identidad, tipo, módulo/número, productor, URI relativa segura, SHA-256, unidades, signos, ejes y dependencias por ID/hash;
- `StageResult`, con estados independientes de ejecución, calidad/convergencia numérica, aplicabilidad y aceptación de desempeño.

`StageResult.completed` deriva solo del estado de ejecución y `StageResult.accepted` solo del estado de aceptación. Una ejecución completada puede —y en Stage 00 debe— permanecer `not_evaluated`; nunca se promueve automáticamente a aceptada.

La validación de dependencias detecta IDs de artefacto duplicados, dependencias ausentes y hashes incompatibles. La validación del DAG y el runner pertenecen a V2-015 y no se anticipan aquí.

## Compatibilidad y regresión

No se modificó código bajo `mechanics/`, configuraciones V1, outputs históricos ni interfaces `design.stages.stage_01/02/03`. Los tests nuevos leen los manifiestos congelados bajo `tests/fixtures/v1/` y confirman que sus `stage_id` permanecen `stage_01`, `stage_02` y `stage_03`, separados del namespace V2.

La evidencia automatizada se encuentra en `tests/contracts/` y cubre round-trip, validación, IDs duplicados, versiones incompatibles, dependencias, separación de estados y regresión de IDs V1.

## Resultado de pruebas

El 26 de septiembre de 2026 se ejecutó la suite completa con el entorno virtual del repositorio:

```text
179 passed, 6 skipped in 63.01s
```

Las seis omisiones corresponden a la caracterización ya documentada de los tres entrypoints instalados V1: sus ejecutables no están presentes en este entorno virtual. No se omitieron tests de contratos V2 ni regresiones numéricas.
