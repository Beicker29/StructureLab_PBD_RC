# StructureLab_PBD_RC

`StructureLab_PBD_RC` es un proyecto Python para construir, de forma progresiva, una herramienta de apoyo a talleres de diseno sismico basado en desempeno para estructuras de concreto reforzado.

La idea central es evitar scripts aislados por taller. Cada taller se modela como un flujo de `design/workshops/` que orquesta modulos reutilizables: mecanica, IO y reportes.

## Filosofia del proyecto

- Los talleres no contienen la teoria central.
- Las ecuaciones mecanicas y modelos constitutivos viven en `mechanics/`.
- La orquestacion de talleres vive en `design/workshops/`.
- La lectura y escritura de datos vive en `io/`.
- Las tablas, graficas y reportes viven en `reports/`.
- Los flujos de taller solo leen configuraciones, coordinan modulos y guardan resultados.
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
- `outputs/workshop_01/data/models/<modelo>/<modelo>.csv`
- `outputs/workshop_01/data/models/<modelo>/<modelo>.xlsx`
- `outputs/workshop_01/figures/*.png`
- `outputs/workshop_01/figures/models/*.png`
- `outputs/workshop_01/reports/<modelo>/<modelo>.yaml`
- `outputs/workshop_01/reports/mander_classic_unconfined_concrete/mander_classic_unconfined_concrete_memoria.pdf`

## Estado actual

El Taller 1 ya implementa un flujo funcional para:

- `mander_classic_unconfined_concrete`.
- `mander_classic_confined_concrete`.
- `mander_adjusted_confined_concrete`.
- `attard_setunge_unconfined_concrete`.
- `attard_setunge_confined_concrete`.
- `steel_tension_mander`.
- `steel_compression_no_buckling`.
- `steel_compression_with_buckling`.
- `welded_wire_mesh` para diametros 4, 5 y 6 mm.

Convencion de signos del Taller 1: se define en `configs/workshops/workshop_01_material_characterization.yaml`, dentro de `curve_generation.sign_convention`. Para el concreto no confinado, la compresion se grafica positiva y la rama de traccion se grafica con esfuerzo y deformacion negativos.

No se implementan todavia momento-curvatura, pushover ni diseno de porticos. Esos bloques quedan reservados para talleres posteriores.
