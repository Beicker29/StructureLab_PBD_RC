# StructureLab_PBD_RC

`StructureLab_PBD_RC` es un proyecto Python enfocado en etapas tecnicas para el analisis de estructuras de concreto reforzado.

La Etapa 1 caracteriza materiales. La Etapa 2 caracteriza la seccion a partir de diagramas momento-curvatura mediante una bilinealizacion ASCE/FEMA adaptada a M-phi. Las etapas siguientes se agregaran cuando su alcance este claro.

## Filosofia del proyecto

- El flujo no contiene la teoria central.
- Las ecuaciones mecanicas y modelos constitutivos viven en `mechanics/`.
- La orquestacion de cada etapa vive en `design/stages/`.
- La lectura y escritura de datos vive en `io/`.
- Las tablas, graficas y reportes viven en `reports/`.
- Cada flujo de etapa solo lee configuraciones, coordina modulos y guarda resultados.
- Los notebooks son para exploracion y visualizacion, no para logica principal.

## Alcance Actual

El repositorio contiene implementacion de:

- Etapa 1: caracterizacion mecanica de materiales.
- Etapa 2: caracterizacion de seccion por bilinealizacion de diagramas momento-curvatura.

## Roadmap por etapas

1. Etapa 1: caracterizacion mecanica de materiales.
2. Etapa 2: caracterizacion de la seccion mediante idealizacion bilineal M-phi.
3. Etapas posteriores: se definiran despues de consolidar la seccion.

## Entorno virtual

El entorno virtual del proyecto se llama:

```powershell
.venv_structurelab_pbd_rc
```

Activacion manual:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\Activate.ps1
```

En VS Code, una terminal nueva abierta dentro del proyecto usara el perfil `StructureLab PowerShell` y activara automaticamente `.venv_structurelab_pbd_rc`.

Tambien queda preparado:

- `.vscode/settings.json` para que VS Code use ese interprete y abra una terminal local `StructureLab PowerShell` con el entorno activado.
- `.envrc` para usuarios de `direnv`.
- `scripts/Enter-StructureLab.cmd` para abrir una terminal en el proyecto con el entorno activado sin cambiar politicas globales de PowerShell.
- `scripts/Register-StructureLabAutoActivate.ps1` para instalar, si se aprueba despues, un hook de PowerShell que active el entorno al entrar al proyecto.

## Instalacion local

Desde la raiz del proyecto:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe -m pip install setuptools
.\.venv_structurelab_pbd_rc\Scripts\python.exe -m pip install -e ".[dev]" --no-build-isolation
```

## Ejecucion de la Etapa 1

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_01.py
```

Tambien puede indicarse una configuracion especifica:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_01.py --config configs\stages\stage_01_material_characterization.yaml
```

El script lee `configs/stages/stage_01_material_characterization.yaml`, valida los datos principales, calcula geometria y confinamiento, genera curvas de materiales, calcula metricas comparativas y exporta resultados en `outputs/stage_01/`.

Archivos principales generados:

- `outputs/stage_01/data/concrete_curves.csv`
- `outputs/stage_01/data/steel_curves.csv`
- `outputs/stage_01/data/mesh_curves.csv`
- `outputs/stage_01/data/curve_metrics.csv`
- `outputs/stage_01/data/stage_01_results.json`
- `outputs/stage_01/data/models/<modelo>/<modelo>.csv`
- `outputs/stage_01/data/models/<modelo>/<modelo>.xlsx`
- `outputs/stage_01/figures/*.png`
- `outputs/stage_01/figures/models/*.png`
- `outputs/stage_01/reports/<modelo>/<modelo>.yaml`
- `outputs/stage_01/reports/mander_classic_unconfined_concrete/mander_classic_unconfined_concrete_memoria.pdf`

## Ejecucion de la Etapa 2

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_02.py
```

Tambien puede indicarse una configuracion especifica:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_02.py --config configs\stages\stage_02_section_characterization.yaml
```

El script lee `configs/stages/stage_02_section_characterization.yaml`, importa el Excel definido en `source.workbook`, procesa las hojas indicadas en `source.sheets` y genera una subcarpeta por hoja dentro de `outputs/stage_02/`. En cada ejecucion se borra la salida previa de la Etapa 2 y se reconstruye desde el Excel vigente.

Para cada hoja, se detectan automaticamente los pares de columnas `Curvature` / `Moment`, se extraen las curvas M-phi y se genera una idealizacion bilineal:

```text
(0, 0) -> (phi_y, My) -> (phi_u, Mu)
```

Archivos principales generados:

- `outputs/stage_02/data/stage_02_results.json`
- `outputs/stage_02/<hoja>/data/moment_curvature_curves.csv`
- `outputs/stage_02/<hoja>/data/bilinear_curves.csv`
- `outputs/stage_02/<hoja>/data/bilinearization_parameters.csv`
- `outputs/stage_02/<hoja>/data/stage_02_sheet_results.json`
- `outputs/stage_02/<hoja>/figures/moment_curvature_real.png`
- `outputs/stage_02/<hoja>/figures/moment_curvature_bilinearization.png`
- `outputs/stage_02/<hoja>/figures/moment_curvature_real_vs_bilinear.png`
- `outputs/stage_02/<hoja>/reports/<curva>/<curva>_bilinearization.yaml`

## Estado actual

La Etapa 1 ya implementa un flujo funcional para:

- `mander_classic_unconfined_concrete`.
- `mander_classic_confined_concrete`.
- `mander_adjusted_confined_concrete`.
- `attard_setunge_unconfined_concrete`.
- `attard_setunge_confined_concrete`.
- `steel_tension_mander`.
- `steel_compression_no_buckling`.
- `steel_compression_with_buckling`.
- `welded_wire_mesh` para diametros 4, 5 y 6 mm.

Convencion de signos de la Etapa 1: se define en `configs/stages/stage_01_material_characterization.yaml`, dentro de `curve_generation.sign_convention`. Para el concreto no confinado, la compresion se grafica positiva y la rama de traccion se grafica con esfuerzo y deformacion negativos.

La Etapa 2 ya implementa la bilinealizacion ASCE/FEMA adaptada a diagramas momento-curvatura. `My` se reporta como fluencia efectiva equivalente de la seccion, no como primera fluencia fisica de una barra.
