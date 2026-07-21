# StructureLab_PBD_RC

`StructureLab_PBD_RC` es un proyecto Python enfocado en etapas tecnicas para el analisis de estructuras de concreto reforzado.

La Etapa 1 calcula amenaza, con implementacion inicial para espectros sismicos. La Etapa 2 caracteriza materiales. La Etapa 3 caracteriza la seccion a partir de diagramas momento-curvatura mediante una bilinealizacion ASCE/FEMA adaptada a M-phi.

## Filosofia del proyecto

- El flujo no contiene la teoria central.
- Las ecuaciones mecanicas y modelos constitutivos viven en `mechanics/`.
- La orquestacion de cada etapa vive en `design/stages/`.
- La lectura y escritura de datos vive en `io/`.
- Las tablas, graficas y reportes viven en `reports/`.
- Cada flujo de etapa solo lee configuraciones, coordina modulos y guarda resultados.
- Los notebooks son para exploracion y visualizacion, no para logica principal.
- Los YAML de cada etapa viven en `configs/<stage_id>/`; por ejemplo, lo sismico de Etapa 1 se organiza como `hazard.seismic`.

## Alcance Actual

El repositorio contiene implementacion de:

- Etapa 1: calculo de amenaza con espectros sismicos NSR-10 y SGC + CCP-14.
- Etapa 2: caracterizacion mecanica de materiales.
- Etapa 3: caracterizacion de seccion por bilinealizacion de diagramas momento-curvatura.

## Roadmap por etapas

1. Etapa 1: calculo de amenaza, con primer modulo sismico implementado.
2. Etapa 2: caracterizacion mecanica de materiales.
3. Etapa 3: caracterizacion de la seccion mediante idealizacion bilineal M-phi.
4. Etapas posteriores: se definiran despues de consolidar la seccion.

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
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_01.py --config configs\stage_01\case_01_nsr10_spectra.yaml
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_01.py --config configs\stage_01\case_02_sgc_ccp14_spectra.yaml
```

La configuracion de amenaza se guarda bajo `hazard.seismic`. El caso NSR-10 escala el espectro base para niveles de amenaza de 31, 475 y 2500 anos. El caso SGC + CCP-14 usa valores SGC independientes por periodo de retorno; `Fpga`, `Fa` y `Fv` se calculan con las tablas CCP-14 mediante interpolacion lineal.

Archivos principales generados:

- `outputs/stage_01/nsr10_spectra/data/case_01_nsr10_spectra.csv`
- `outputs/stage_01/nsr10_spectra/data/case_01_nsr10_parameters.csv`
- `outputs/stage_01/nsr10_spectra/data/etabs/case_01_nsr10_<nivel>_etabs_v22.txt`
- `outputs/stage_01/nsr10_spectra/figures/case_01_nsr10_spectra.png`
- `outputs/stage_01/nsr10_spectra/figures/case_01_nsr10_<nivel>_spectrum.png`
- `outputs/stage_01/nsr10_spectra/reports/case_01_nsr10_report.yaml`
- `outputs/stage_01/ccp14_spectra/data/case_02_sgc_ccp14_spectra.csv`
- `outputs/stage_01/ccp14_spectra/data/case_02_sgc_ccp14_parameters.csv`
- `outputs/stage_01/ccp14_spectra/data/etabs/case_02_sgc_ccp14_<nivel>_etabs_v22.txt`
- `outputs/stage_01/ccp14_spectra/figures/case_02_sgc_ccp14_spectra.png`
- `outputs/stage_01/ccp14_spectra/figures/case_02_sgc_ccp14_<nivel>_spectrum.png`
- `outputs/stage_01/ccp14_spectra/reports/case_02_sgc_ccp14_report.yaml`

Los TXT para ETABS v22 se importan como `From File`, con `Values are = Period vs Value` y `Header Lines to Skip = 0`.

## Ejecucion de la Etapa 2

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_02.py
```

Tambien puede indicarse una configuracion especifica:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_02.py --config configs\stage_02\material_characterization.yaml
```

El script lee `configs/stage_02/material_characterization.yaml`, valida los datos principales, calcula geometria y confinamiento, genera curvas de materiales, calcula metricas comparativas y exporta resultados en `outputs/stage_02/`.

Archivos principales generados:

- `outputs/stage_02/data/concrete_curves.csv`
- `outputs/stage_02/data/steel_curves.csv`
- `outputs/stage_02/data/mesh_curves.csv`
- `outputs/stage_02/data/curve_metrics.csv`
- `outputs/stage_02/data/stage_02_results.json`
- `outputs/stage_02/data/models/<modelo>/<modelo>.csv`
- `outputs/stage_02/data/models/<modelo>/<modelo>.xlsx`
- `outputs/stage_02/figures/*.png`
- `outputs/stage_02/figures/models/*.png`
- `outputs/stage_02/reports/<modelo>/<modelo>.yaml`
- `outputs/stage_02/reports/mander_classic_unconfined_concrete/mander_classic_unconfined_concrete_memoria.pdf`

## Ejecucion de la Etapa 3

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_03.py
```

Tambien puede indicarse una configuracion especifica:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_stage_03.py --config configs\stage_03\section_characterization.yaml
```

El script lee `configs/stage_03/section_characterization.yaml`, importa el Excel definido en `source.workbook`, procesa las hojas indicadas en `source.sheets` y genera una subcarpeta por hoja dentro de `outputs/stage_03/`. Cada hoja separa sus salidas en `monotonica/` y `ciclica/`, y cada una contiene `data/`, `figures/` y `reports/`. La salida `ciclica/` recorta la curva real en el punto configurado por viga y recalcula su propia bilinealizacion. En cada ejecucion se borra la salida previa de la Etapa 3 y se reconstruye desde el Excel vigente.

Para cada hoja, se detectan automaticamente los pares de columnas `Curvature` / `Moment`, se extraen las curvas M-phi y se genera una idealizacion bilineal:

```text
(0, 0) -> (phi_y, My) -> (phi_u, Mu)
```

Archivos principales generados:

- `outputs/stage_03/data/stage_03_results.json`
- `outputs/stage_03/<hoja>/monotonica/data/moment_curvature_curves.csv`
- `outputs/stage_03/<hoja>/monotonica/data/bilinear_curves.csv`
- `outputs/stage_03/<hoja>/monotonica/data/bilinearization_parameters.csv`
- `outputs/stage_03/<hoja>/monotonica/figures/moment_curvature_real.png`
- `outputs/stage_03/<hoja>/monotonica/reports/<curva>/<curva>_bilinearization.yaml`
- `outputs/stage_03/<hoja>/ciclica/data/moment_curvature_curves.csv`
- `outputs/stage_03/<hoja>/ciclica/data/bilinear_curves.csv`
- `outputs/stage_03/<hoja>/ciclica/data/cyclic_cut_points.csv`
- `outputs/stage_03/<hoja>/ciclica/figures/moment_curvature_real_vs_bilinear.png`
- `outputs/stage_03/<hoja>/ciclica/reports/<curva>/<curva>_bilinearization.yaml`

## Estado actual

La Etapa 1 ya implementa dos casos independientes:

- `case_01_nsr10`: forma espectral NSR-10 con niveles escalados.
- `case_02_sgc_ccp14`: valores SGC independientes y forma espectral CCP-14. Este caso requiere completar manualmente `PGA`, `Sa_0_2` y `Sa_1_0`; los factores de sitio `Fpga`, `Fa` y `Fv` se calculan con las tablas CCP-14.

La Etapa 2 ya implementa un flujo funcional para:

- `mander_classic_unconfined_concrete`.
- `mander_classic_confined_concrete`.
- `mander_adjusted_confined_concrete`.
- `attard_setunge_unconfined_concrete`.
- `attard_setunge_confined_concrete`.
- `steel_tension_mander`.
- `steel_compression_no_buckling`.
- `steel_compression_with_buckling`.
- `welded_wire_mesh` para diametros 4, 5 y 6 mm.

Convencion de signos de la Etapa 2: se define en `configs/stage_02/material_characterization.yaml`, dentro de `curve_generation.sign_convention`. Para el concreto no confinado, la compresion se grafica positiva y la rama de traccion se grafica con esfuerzo y deformacion negativos.

La Etapa 3 ya implementa la bilinealizacion ASCE/FEMA adaptada a diagramas momento-curvatura. `My` se reporta como fluencia efectiva equivalente de la seccion, no como primera fluencia fisica de una barra.
