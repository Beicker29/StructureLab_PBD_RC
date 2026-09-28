# Conversión V1→V2 y CLI del workflow

**Estado:** bloque A/B ejecutado el 28 de septiembre de 2026, después de V2-021. Esta entrega cubre la conversión y la CLI solicitadas; no declara cerradas V2-022, V2-024 ni las capacidades científicas posteriores.

## Conversión explícita

`structurelab workflow convert` acepta un YAML de decisiones de proyecto y uno o varios orígenes V1: un YAML Stage 01, el directorio Stage 02, o un YAML Stage 03. El modo predeterminado es **preview** y no escribe archivos. `--write --destination <directorio nuevo>` genera `project.yaml` (`ProjectSpec` V2) y un JSON canónico por módulo bajo `modules/`. Rechaza un destino existente o situado dentro de los directorios de inputs V1; nunca reescribe configuraciones ni importa `outputs/stage_0x`.

El YAML de decisiones es necesario porque los inputs V1 no contienen identidad completa de sitio, objetivos de desempeño, revisión de diseño ni una asociación demostrada entre el libro M–φ y los materiales. Esos datos se declaran expresamente, sin inferirlos del nombre de una carpeta. Estructura requerida:

```yaml
schema_version: '2'
project_id: Modelos_constitutivos
design_revision: rev_01
case_id: COL75X75FC28MPa
site:
  site_id: sitio_confirmado
  name: Sitio identificado por el responsable del proyecto
base_units: {length: m, force: kN, time: s}
hazard_levels:
  - {hazard_level_id: service, name: Servicio, return_period_years: 31}
  - {hazard_level_id: design, name: Diseño, return_period_years: 475}
  - {hazard_level_id: maximum_considered, name: Máximo considerado, return_period_years: 2500}
performance_objectives:
  - objective_id: characterization_only
    name: Caracterización de inputs existentes
    hazard_level_ids: [service, design, maximum_considered]
material_set_id: canonical_v1_materials
v1_bindings:
  site_hazard: {case_id: case_01_nsr10}
  material_characterization:
    project_id: Modelos_constitutivos
    case_id: COL75X75FC28MPa
  section_component_characterization:
    workbook_sha256: ce38cc1aca600805cc852e46d7c564ba5646ed5fdcb4ba1bafdbcdddbd27f427
    confirmed_for_project_case: true
```

Se incluyen en `v1_bindings` exactamente los módulos cuyos orígenes se pasan al comando. `confirmed_for_project_case: true` es una **afirmación explícita del responsable de la conversión**; los ejemplos V1 no prueban por sí mismos que los materiales y el Excel pertenezcan a una misma edificación. Para Stage 03, `--source-root` resuelve el libro relativo al repositorio original. El hash declarado debe coincidir con el libro leído.

```powershell
structurelab workflow convert --project-template decision.yaml `
  --stage-01 configs/stage_01/case_01_nsr10_spectra.yaml `
  --stage-02 configs/stage_02 `
  --stage-03 configs/stage_03/section_characterization.yaml `
  --source-root . --destination converted/project_01

structurelab workflow convert --project-template decision.yaml `
  --stage-01 configs/stage_01/case_01_nsr10_spectra.yaml `
  --stage-02 configs/stage_02 `
  --stage-03 configs/stage_03/section_characterization.yaml `
  --source-root . --destination converted/project_01 --write
```

El preview informa rutas, SHA-256 y tamaños previstos. `project.yaml` conserva referencias con hash a las configuraciones V2 y `metadata.v1_conversion.source_records` identifica cada archivo de origen, su ID V1, rol, ruta y SHA-256. Stage 01 conserva su YAML original como contenido de la configuración V2, con `schema_version` e ID semántico añadidos. Stage 02 conserva cada `resolved_inputs`, parámetros, unidades, signos y procedencia de los cuatro modelos; los IDs nuevos de conjunto/parámetros/instancia son deterministas y no activan múltiples conjuntos. Stage 03 conserva la configuración y cada fila de las hojas seleccionadas como entrada estructurada, con hashes del YAML y el XLSX. El handler V2 consume esas filas sin abrir el libro durante el cálculo.

Se rechazan asociaciones, períodos de retorno, rutas, hashes o nombres de hojas incompatibles; también JSON Stage 02 deshabilitados o no traducidos, campos V1 desconocidos y colisiones de carpetas de hojas. No se eligen defaults para datos científicos faltantes. Las rutas V1 absolutas se guardan como procedencia; el proyecto V2 puede ejecutarse después desde otro CWD con sus JSON incluidos. Los archivos fuente no se copian ni eliminan.

## CLI oficial V2

El entrypoint de paquete `structurelab` se declara en `pyproject.toml`; el equivalente inmediato desde el checkout editable es `python -m structurelab_pbd_rc`. Su sintaxis es:

```powershell
structurelab workflow plan --project converted/project_01/project.yaml `
  --module site_hazard --module material_characterization `
  --module section_component_characterization

structurelab workflow run --project converted/project_01/project.yaml `
  --module site_hazard --module material_characterization `
  --module section_component_characterization `
  --project-id Modelos_constitutivos --design-revision rev_01 `
  --case-id COL75X75FC28MPa --output-root isolated_outputs
```

Sin `--module`, se seleccionan las configuraciones declaradas en `ProjectSpec.references`. Los flags de identidad verifican los valores del proyecto: no crean una identidad nueva ni reinterpretan `stage_01/02/03`. `--config MODULE_ID=PATH` permite una ruta explícita **solo si sus bytes y SHA-256 coinciden con la referencia del proyecto**. Las rutas relativas de configuración se resuelven respecto a `project.yaml`. `plan` es de solo lectura, incluso si no existe `--output-root`; `run` usa `WorkflowRunner` y `TransactionalPublisher` V2, sin ecuaciones en la CLI. Una corrida anterior puede ofrecerse mediante `--reuse-manifest <ruta>`; no se descubren resultados por glob. El manifiesto debe estar en la raíz V2 seleccionada y el runner verifica procedencia e integridad antes de presentar `reusable`.

La salida JSON muestra orden de ejecución y estado por `module_id`: `ready`, `reusable`, `invalidated`, `not_implemented` o `blocked`, con `reason`, `reason_code` y detalles. Una ejecución informa estados de cálculo, calidad y aceptación por módulo. Códigos de salida: **0** para preview/escritura/plan ejecutable/corrida publicada; **2** para CLI, contrato o configuración inválidos; **3** para plan bloqueado o módulo no implementado; **1** para fallo de ejecución o publicación. Un plan `invalidated` es ejecutable y devuelve 0. El `run_id` se genera si no se indica; un ID ya publicado no se reemplaza.

Los comandos `structurelab-stage-01/02/03` mantienen significado y entrypoints V1. Su defecto previo de no propagar argumentos desde el ejecutable no se corrigió en este bloque: invocar `--help` ejecuta el caso predeterminado. Para pasar argumentos V1 utilice `scripts/run_stage_0x.py` o `python -m structurelab_pbd_rc.cli.run stage_0x ...`. Tras modificar `pyproject.toml` se debe reinstalar el paquete para exponer el nuevo ejecutable `structurelab`; `python -m structurelab_pbd_rc` también funciona desde el checkout. La [instalación limpia de cierre](V2_MIGRATION_CLOSURE.md) comprobó los cuatro ejecutables con build isolation y sin `setuptools` preinstalado en el entorno nuevo.

## Verificación y límites

El test de integración recorre preview → escritura → plan → run con los tres dominios. Compara el CSV de espectros, las curvas y métricas de los cuatro materiales, y las tablas monotónicas/cíclicas de las diez hojas con `tests/fixtures/v1/`; también comprueba hashes de inputs V1, preservación de `outputs/stage_0x`, planificación desde otro CWD, rechazo de ambigüedad, `reusable` e `invalidated`. Las pruebas del runner y servicios existentes mantienen sus comparaciones científicas adicionales. No se ha demostrado equivalencia física entre los ejemplos V1 ni se ha añadido aceptación de desempeño.

La corrida final V1+V2 terminó con **286 passed, 0 failed, 0 errors, 0 skipped**. No hubo diferencias numéricas o funcionales ajenas al contrato de la CLI. En dos intentos previos, nueve y luego uno fallaron al abrir rutas de publicación de Windows de 260 caracteres o más; no fueron fallos de aserción ni errores de preparación. La corrida final conservó el ajuste local de permisos temporales V2-003 y acortó los nombres `tmp_path` solo dentro del proceso de pytest. No se alteraron tests previos ni código productivo para evitar ese límite de ruta.

El conversor requiere un directorio Stage 02 completo y habilitado conforme al contrato V1; una selección parcial o múltiples `material_set_id` quedan fuera de alcance. La conversión Stage 03 materializa filas del XLSX en JSON, por lo que el archivo V2 puede ser grande; el hash del libro original preserva la trazabilidad. Los archivos de presentación (PDF/PNG) no son oráculos numéricos. El motor de fibras, OpenQuake, nuevos backends, movimientos sísmicos y reporting PDF/HTML no forman parte de esta entrega.

La escritura de la conversión crea un directorio nuevo y deja `project.yaml` para el final; si falla el disco durante esa escritura, puede quedar un destino V2 incompleto que deberá inspeccionarse y retirarse antes de repetir `--write`. Los inputs V1 permanecen protegidos en ese caso.

**Incidente de verificación corregido:** al invocar `--help` en los tres entrypoints V1 se activaron, por su comportamiento legado, los runners predeterminados sobre `outputs/stage_0x`. Antes de continuar se restauraron exclusivamente esos árboles con los 268 archivos rastreados de `HEAD`; Git quedó limpio en `outputs/stage_01`–`03`, y los 268 hashes coincidieron con el [manifiesto V1](../../tests/fixtures/v1/metadata/BASELINE_MANIFEST_V2.json). No se utilizarán esos ejecutables para nuevas verificaciones en este bloque.
