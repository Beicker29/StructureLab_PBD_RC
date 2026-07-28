# StructureLab_PBD_RC

`StructureLab_PBD_RC` es un proyecto Python para analisis basado en desempeno de estructuras de concreto reforzado.

El repositorio contiene actualmente:

- Etapa 1: amenaza sismica mediante espectros NSR-10 y SGC + CCP-14.
- Etapa 2: caracterizacion constitutiva de acero de refuerzo ductil y no ductil.
- Etapa 3: caracterizacion de secciones mediante bilinealizacion de diagramas momento-curvatura.

La Etapa 2 esta organizada por material, protocolo de carga y modelo constitutivo.

## Arquitectura

- `core/`: validacion, excepciones, unidades y registro de modelos.
- `design/stages/`: orquestacion de las etapas vigentes.
- `io/`: lectura y escritura de datos.
- `mechanics/materials/`: modelos constitutivos y estado de historia.
- `mechanics/hazard/`: calculos de amenaza.
- `mechanics/sections/`: calculos de seccion.
- `reports/`: tablas, figuras y reportes.
- `configs/stage_02/<material>/<behavior>/`: un JSON independiente por modelo.
- `outputs/stage_02/`: resultados aislados por proyecto y caso.

La teoria central se implementa en `mechanics/`. Los flujos solo deben validar entradas, coordinar calculos y escribir resultados.

## Etapa 2: materiales

Los cuatro materiales previstos son:

- `confined_concrete`: concreto confinado.
- `unconfined_concrete`: concreto no confinado.
- `ductile_reinforcing_steel`: acero de refuerzo ductil.
- `nonductile_reinforcing_steel`: acero de refuerzo no ductil.

`configs/stage_02/` contiene unicamente las cuatro carpetas de material. Cada una contiene `monotonic/` y `cyclic/`, y cada modelo constitutivo dispone de un unico JSON:

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

Cada JSON declara `stage_id`, `enabled`, `title`, `units` e `inputs`. El bloque `inputs` exige `project_id`, `case_id`, `model_id`, `parameters` y los bloques adicionales requeridos por el modelo. Las unidades son `mm`, `MPa` y `mm/mm`; la fuerza global del proyecto se expresa en `kN`.

```text
outputs/stage_02/<project_id>/<case_id>/<behavior>/<material>/<model_id>/
|-- data/
|   |-- resolved_inputs.json
|   |-- calculated_parameters.yaml
|   |-- metrics.yaml
|   |-- curve.csv
|   `-- curve.xlsx
|-- figures/
|   `-- response.png
`-- reports/
    |-- model_report.yaml
    `-- model_report.pdf
```

Una ejecucion procesa conjuntamente todos los JSON habilitados y los agrupa por `project_id/case_id`. Cada caso procesado se construye completo y reemplaza su carpeta anterior; los demas proyectos y casos se conservan. La carga rechaza mas de un JSON para el mismo modelo, identificadores duplicados por diferencias de mayusculas, combinaciones repetidas y colisiones de ruta.

Modelos implementados para `nonductile_reinforcing_steel`:

- `monotonic/modified_ramberg_osgood`: envolvente a traccion de Carrillo et al. (2019).
- `cyclic/menegotto_pinto`: algoritmo con historia compatible con Steel02. La configuracion incluida es sintetica y sirve solamente para verificar el software; no es una calibracion NTC 5806.

Modelo implementado para `ductile_reinforcing_steel`:

- `monotonic/steel_compression_rdm_2019_monotonic`: envolvente de traccion de referencia y envolvente RDM 2019 de compresion con pandeo inelastico y degradacion pospandeo. Para restriccion transversal rectangular calcula `epsilon_y`, las rigideces `k` y `kt`, `keq=kt/k`, el modo `n`, `L=n*s`, `L/D` y `rb` a partir de variables fisicas. `epsilon_y`, `buckling_intervals`, `L/D` y `rb` no son inputs canonicos.

## Entorno virtual

El entorno virtual del proyecto se llama:

```powershell
.venv_structurelab_pbd_rc
```

Activacion manual desde PowerShell:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\Activate.ps1
```

Instalacion local:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe -m pip install setuptools
.\.venv_structurelab_pbd_rc\Scripts\python.exe -m pip install -e ".[dev]" --no-build-isolation
```

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

El flujo importa el Excel definido en `source.workbook`, procesa las hojas seleccionadas y genera salidas monotonicas y ciclicas por hoja. Los resultados se guardan bajo `outputs/stage_03/`.

La bilinealizacion produce:

```text
(0, 0) -> (phi_y, My) -> (phi_u, Mu)
```

`My` representa la fluencia efectiva equivalente de la seccion, no la primera fluencia fisica de una barra.
