# StructureLab_PBD_RC

`StructureLab_PBD_RC` es un orquestador Python en desarrollo para un flujo PBSD/PBEE de edificaciones de concreto reforzado. La arquitectura V2 define módulos visibles **00–12** con IDs semánticos. Actualmente solo son ejecutables `project_objectives` (00), `site_hazard` (01), `material_characterization` (03) y `section_component_characterization` (04). Este último caracteriza curvas M–φ **importadas**; todavía no calcula secciones por fibras. Los módulos 02 y 05–12 siguen pendientes. Consulte la [arquitectura y matriz de estado](docs/ARCHITECTURE_V2.md) antes de usar resultados para un proyecto.

Las tres etapas V1 permanecen disponibles: `stage_01` genera espectros NSR-10 o con forma CCP-14 y valores SGC configurados; `stage_02` caracteriza cuatro formulaciones constitutivas; `stage_03` importa e idealiza curvas M–φ de Excel. V2 conserva esos cálculos y publica corridas independientes con manifiesto. La numeración V2 **no cambia el significado** de los comandos V1: `stage_02` V1 sigue siendo materiales, mientras 02 V2 es el modelo estructural base todavía no implementado.

## Instalación

Requiere Python 3.10 o posterior. En PowerShell, desde la raíz del repositorio:

```powershell
python -m venv .venv_structurelab_pbd_rc
.\.venv_structurelab_pbd_rc\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv_structurelab_pbd_rc\Scripts\Activate.ps1
structurelab workflow --help
```

El build aislado de `pip` instala `setuptools>=68` según `pyproject.toml`; no hace falta instalarlo manualmente en el entorno de ejecución. Una instalación sin acceso al índice requiere un repositorio local de wheels para los requisitos de build y runtime. En Linux/macOS se usan los ejecutables equivalentes bajo `bin/`. Los ejemplos siguientes suponen el entorno activado; también puede invocar directamente `Scripts/structurelab.exe`. El paquete instala `structurelab` y conserva `structurelab-stage-01`, `structurelab-stage-02` y `structurelab-stage-03`.

## Workflow V2

Prepare un YAML de decisiones del proyecto como explica la [guía V1→V2](docs/migration/COMPATIBILITY_CLI_V2_023_025.md). La conversión de un caso existente se revisa primero sin escribir archivos:

```powershell
structurelab workflow convert --project-template decision.yaml `
  --stage-01 configs/stage_01/case_01_nsr10_spectra.yaml `
  --stage-02 configs/stage_02 `
  --stage-03 configs/stage_03/section_characterization.yaml `
  --source-root . --destination converted/project_01
```

Después de verificar el preview, repita el comando con `--write`. El destino debe ser nuevo; el conversor no modifica configs ni outputs V1. Planifique y ejecute con IDs semánticos:

```powershell
structurelab workflow plan --project converted/project_01/project.yaml `
  --module site_hazard --module material_characterization `
  --module section_component_characterization
structurelab workflow run --project converted/project_01/project.yaml `
  --module site_hazard --module material_characterization `
  --module section_component_characterization --output-root isolated_outputs
```

`plan` informa `ready`, `reusable`, `invalidated`, `not_implemented` o `blocked` con razones. `run` solo publica los módulos ejecutables. La CLI también admite `--project-id`, `--design-revision`, `--case-id`, `--config MODULE_ID=PATH` y `--reuse-manifest`; los valores deben concordar con `ProjectSpec` y sus hashes. Si el entorno aún no se ha reinstalado, `python -m structurelab_pbd_rc workflow ...` ofrece la misma CLI desde el checkout. El [cierre de migración](docs/migration/V2_MIGRATION_CLOSURE.md) registra la regresión y las limitaciones.

## Compatibilidad V1

`design/stages/` conserva los runners históricos; `mechanics/` contiene los cálculos reutilizables, `services/` los prepara para V2, `workflow/` coordina contratos y DAG, `presentation/` crea tablas/figuras e `io/` publica artefactos. Las salidas V1 siguen bajo `outputs/stage_01`, `stage_02` y `stage_03`; las V2 se aíslan bajo `outputs/v2` de la raíz elegida. [La biblioteca científica](references/catalog.yaml) conserva rutas y hashes de sus fuentes.

La información siguiente documenta las entradas y el comportamiento V1 que se mantienen durante la compatibilidad. La Etapa 2 está organizada por material, protocolo de carga y modelo constitutivo.

## Etapa 2: materiales

Los cuatro materiales previstos son:

- `confined_concrete`: concreto confinado.
- `unconfined_concrete`: concreto no confinado.
- `ductile_reinforcing_steel`: acero de refuerzo ductil.
- `nonductile_reinforcing_steel`: acero de refuerzo no ductil.

`unconfined_concrete` conserva su carpeta como reserva; no tiene una formulación ejecutable. Los cuatro modelos implementados se distribuyen entre las otras tres familias. Los parámetros canónicos de `Cyc_MP` son sintéticos para verificar el algoritmo, no una calibración experimental.

`configs/stage_02/` contiene únicamente las cuatro carpetas de material. Cada material contiene `monotonic/` y `cyclic/`, y cada modelo constitutivo dispone de un único JSON:

```text
configs/stage_02/
|-- ductile_reinforcing_steel/
|   |-- monotonic/
|   `-- cyclic/
|-- nonductile_reinforcing_steel/
|   |-- monotonic/
|   `-- cyclic/
|-- confined_concrete/
|   |-- monotonic/
|   `-- cyclic/
`-- unconfined_concrete/
    |-- monotonic/
    `-- cyclic/
```

Cada JSON de modelo declara `stage_id`, `enabled`, `title`, `units` e `inputs`; el bloque `inputs` exige `project_id`, `case_id`, `model_id`, `parameters` y únicamente los datos físicos que consume ese modelo. Todos usan `Modelos_constitutivos/COL75X75FC28MPa`. Las unidades son `mm`, `MPa` y `mm/mm`; la fuerza global del proyecto se expresa en `kN`.

```text
outputs/stage_02/<project_id>/<case_id>/<material>/<behavior>/<model_id>/
|-- data/
|   |-- resolved_inputs.json
|   |-- calculated_parameters.yaml
|   |-- metrics.yaml
|   |-- curve.csv
|   `-- curve.xlsx
|-- figures/
|   |-- response.png
|   `-- response_notable_points.png
`-- reports/
    |-- model_report.yaml
    `-- model_report.pdf
```

Una ejecución procesa conjuntamente todos los JSON habilitados bajo el proyecto `Modelos_constitutivos` y el caso `COL75X75FC28MPa`. Stage 02 se construye primero en una carpeta temporal y reemplaza su árbol anterior solo cuando todos los modelos terminan correctamente. La carga rechaza más de un JSON para el mismo modelo, proyectos o casos inconsistentes y colisiones de ruta.

Modelo implementado para `confined_concrete`:

- `monotonic/Mon_Mander1988.json`: envolvente monotónica de Mander-Popovics. Su propio bloque `parameters.geometry` describe la sección rectangular 750 x 750 mm con 16 barras #7 y flejes #4 cada 100 mm. En rectangulares usa `f_l=0.5*k_e*(rho_x+rho_y)*fyh`; no implementa William-Warnke. La compresión se exporta positiva y el segmento lineal de tracción, definido por `f_t`, `E_c` y `ε_t=f_t/E_c`, se exporta negativo.

Modelos implementados para `nonductile_reinforcing_steel`:

- `monotonic/Mon_MRO.json`: envolvente Ramberg-Osgood modificada de Carrillo et al. (2019).
- `cyclic/Cyc_MP.json`: algoritmo Menegotto-Pinto con historia compatible con Steel02. La configuracion incluida es sintetica y sirve solamente para verificar el software; no es una calibracion NTC 5806.

Instructivos estaticos:

- [Mon_MRO](docs/stage_02/nonductile_reinforcing_steel/monotonic/Mon_MRO/guia_aplicacion_mon_mro.pdf)
- [Cyc_MP](docs/stage_02/nonductile_reinforcing_steel/cyclic/Cyc_MP/guia_aplicacion_cyc_mp.pdf)

Modelo implementado para `ductile_reinforcing_steel`:

- `monotonic/Mon_RDM2019.json`: envolvente de traccion de referencia y dos envolventes RDM 2019 de compresion para `COL75X75FC28MPa`: barras de borde en flexion y barras interiores en compresion axial. `epsilon_y` y `parameter_p` son inputs; para este caso se adopta `P=3.087`. `Es=fy/epsilon_y`, las rigideces `k` y `kt`, `keq=kt/k`, el modo `n`, `L=n*s`, `L/D` y `rb` son resultados calculados. No se ingresan `Es`, `n` ni `L/D`.

El nombre base de cada JSON debe coincidir exactamente con `inputs.model_id`.

## Etapa 1

Ejecucion con las configuraciones disponibles:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_01.py
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_01.py --config configs\stage_01\case_01_nsr10_spectra.yaml
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_01.py --config configs\stage_01\case_02_sgc_ccp14_spectra.yaml
```

Los resultados se guardan bajo `outputs/stage_01/`.

## Etapa 2

Ejecucion conjunta de todos los modelos habilitados:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_02.py
```

Ejecucion desde otra raiz Stage 2 con la misma estructura:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_02.py --config ruta\a\stage_02
```

No se admite ejecutar un JSON aislado: la raiz completa permite validar la unicidad de los modelos y reconstruir cada caso sin omitir configuraciones asociadas. El reporte YAML de cada modelo incluye inputs resueltos, parametros calculados, metadatos, advertencias y archivos producidos.

La formulacion, procedencia y limitaciones se documentan en `docs/material_characterization.md`.

## Etapa 3

Ejecucion:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_03.py
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_03.py --config configs\stage_03\section_characterization.yaml
```

El flujo importa el Excel definido en `source.workbook`, procesa las hojas seleccionadas y genera salidas `monotonica` y `ciclica` por hoja. La segunda etiqueta representa una envolvente recortada o reutilizada; no incluye descarga/recarga histerética. Los resultados se guardan bajo `outputs/stage_03/`.

La bilinealizacion produce:

```text
(0, 0) -> (phi_y, My) -> (phi_u, Mu)
```

`My` representa la fluencia efectiva equivalente de la seccion, no la primera fluencia fisica de una barra.
