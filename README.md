# StructureLab_PBD_RC

`StructureLab_PBD_RC` es un proyecto Python para construir, de forma progresiva, una herramienta de apoyo a talleres de diseno sismico basado en desempeno para estructuras de concreto reforzado.

La idea central es evitar scripts aislados por taller. Cada taller se modela como un workflow que orquesta modulos generales reutilizables: materiales, geometria, secciones, elementos, porticos, desempeno, IO y reportes.

## Filosofia del proyecto

- Los talleres no contienen la teoria central.
- Los modelos de materiales viven en `materials/`.
- Los modelos de secciones viven en `sections/`.
- Los modelos de elementos viven en `elements/`.
- Los modelos de porticos viven en `frames/`.
- La evaluacion de desempeno vive en `performance/`.
- Los workflows solo leen configuraciones, coordinan modulos y guardan resultados.
- Los notebooks son para exploracion y visualizacion, no para logica principal.

## Talleres previstos

1. Modelos para caracterizacion mecanica de materiales.
2. Diseno convencional de un portico plano.
3. Capacidad de desplazamiento y estados limite de una columna.
4. Relacion entre respuesta monotonica y respuesta ciclica.
5. Evaluacion integral del desempeno de una viga.
6. Diseno por capacidad, pushover y evaluacion de desempeno de un portico plano.

## Entorno virtual

El entorno virtual del proyecto se llama:

```powershell
.venv_structurelab_pbd_rc
```

Activacion manual:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\Activate.ps1
```

Tambien queda preparado:

- `.vscode/settings.json` para que VS Code use ese interprete y abra una terminal local `StructureLab CMD` con el entorno activado.
- `.envrc` para usuarios de `direnv`.
- `scripts/Enter-StructureLab.cmd` para abrir una terminal en el proyecto con el entorno activado sin cambiar politicas globales de PowerShell.
- `scripts/Register-StructureLabAutoActivate.ps1` para instalar, si se aprueba despues, un hook de PowerShell que active el entorno al entrar al proyecto.

## Instalacion local

Desde la raiz del proyecto:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe -m pip install setuptools
.\.venv_structurelab_pbd_rc\Scripts\python.exe -m pip install -e ".[dev]" --no-build-isolation
```

## Ejecucion del Taller 1

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_workshop_01.py
```

Tambien puede indicarse una configuracion especifica:

```powershell
.\.venv_structurelab_pbd_rc\Scripts\python.exe scripts\run_workshop_01.py --config configs\workshops\workshop_01_material_characterization.yaml
```

El script lee `configs/workshops/workshop_01_material_characterization.yaml`, valida los datos principales, calcula geometria y confinamiento, genera curvas de materiales, calcula metricas comparativas y exporta resultados en `outputs/workshop_01/`.

Archivos principales generados:

- `outputs/workshop_01/data/concrete_curves.csv`
- `outputs/workshop_01/data/steel_curves.csv`
- `outputs/workshop_01/data/mesh_curves.csv`
- `outputs/workshop_01/data/curve_metrics.csv`
- `outputs/workshop_01/data/workshop_01_results.json`
- `outputs/workshop_01/tables/*.xlsx`
- `outputs/workshop_01/figures/*.png`
- `outputs/workshop_01/reports/workshop_01_report.pdf`

## Estado actual

El Taller 1 ya implementa un flujo funcional para:

- Concreto no confinado.
- Concreto confinado con Mander clasico.
- Concreto confinado con Mander ajustado.
- Attard-Setunge no confinado y confinado con advertencia de coeficientes pendientes de verificacion por perdida de formato en el PDF.
- Acero longitudinal a traccion.
- Acero longitudinal a compresion sin pandeo.
- Acero longitudinal a compresion con degradacion por pandeo.
- Malla electrosoldada para diametros 4, 5 y 6 mm.

Convencion de signos del Taller 1: compresion positiva para concreto y acero en compresion; traccion positiva para acero en traccion y malla.

No se implementan todavia momento-curvatura, pushover ni diseno de porticos. Esos bloques quedan reservados para talleres posteriores.
