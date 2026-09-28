# Estado de la línea base V2 — V2-001 a V2-003

**Fecha:** 25 de septiembre de 2026. **Alcance inicial de este informe:** V2-001, V2-002 y V2-003 de [las fichas de línea base](../BASELINE_TASKS_V2.md). Después se ejecutaron [V2-003R](REMOVE_QUARTO_REPORTING_DEPENDENCY.md) y V2-004 a V2-009. Las secciones originales siguientes conservan el estado observado antes de esas capturas; el estado posterior se enlaza al final. V2-010 a V2-012 se documentan en [contratos iniciales](CONTRACTS_V2_010_012.md), V2-013 a V2-014 en [fronteras y publicación](BOUNDARIES_PUBLICATION_V2_013_014.md), V2-015 en [runner y DAG](WORKFLOW_RUNNER_V2_015.md), V2-016 en [invalidación y reutilización](INVALIDATION_REUSE_V2_016.md), V2-017 en [servicio de amenaza](HAZARD_SERVICE_V2_017.md), V2-018 en [servicio de materiales](MATERIAL_SERVICE_V2_018.md), V2-019 en [publicación de materiales](MATERIAL_PUBLICATION_V2_019.md), V2-020 en [servicio de secciones importadas](SECTION_SERVICE_V2_020.md) y V2-021 en [publicación de secciones](SECTION_PUBLICATION_V2_021.md).

| Tarea | Estado | Evidencia |
|---|---|---|
| V2-001 | Cerrada para la captura V1 | Acta de decisiones de este documento, enlazada desde [el plan](../MIGRATION_PLAN_V2.md) |
| V2-002 | Captura documental realizada | [Manifiesto de línea base](../../tests/fixtures/v1/metadata/BASELINE_MANIFEST_V2.json), con hashes por archivo, entorno e inventario de salidas previo a las pruebas |
| V2-003 | Preparación temporal resuelta; suite completa ejecutada antes de V2-003R | Corrida histórica de pytest: 116 aprobados, 4 fallidos por ausencia de Quarto, 0 errores de preparación |
| V2-003R | Renderer Quarto/Typst retirado de Stage 01 | [Ficha de la Issue](REMOVE_QUARTO_REPORTING_DEPENDENCY.md) y suite posterior: 120 aprobados |
| V2-004 | Dos casos espectrales capturados | [Memoria de amenaza](BASELINE_HAZARD_V2.md) y fixtures completas |
| V2-005 | Cuatro materiales capturados | [Memoria de materiales](BASELINE_MATERIALS_V2.md) y fixtures completas |
| V2-006 | Diez hojas M–φ capturadas | [Memoria de secciones](BASELINE_SECTIONS_V2.md) y fixtures completas |
| V2-007 | CLI, imports y rutas V1 caracterizados | [Matriz de interfaces](BASELINE_INTERFACES_V2.md) |
| V2-008 | Fallos de publicación V1 caracterizados | [Matriz de fallos y centinelas](BASELINE_PUBLICATION_V2.md) |
| V2-009 | Fronteras de datos y algoritmos ejecutadas | [Registro de casos límite](BASELINE_BOUNDARIES_V2.md) |

## V2-001 — Acta de decisiones

Se registran como **aprobadas** las decisiones expresas de la revisión V2:

1. Arquitectura de trece módulos 00–12 con IDs internos semánticos; la numeración es visible y no redefine los `stage_0x` de V1.
2. Módulo 04 con motor nativo de análisis seccional por fibras. El importador Excel M–φ existente se conserva como compatibilidad y benchmark, con límites de comparabilidad explícitos. El motor nuevo no forma parte de esta línea base.
3. Módulo 05 organizado conceptualmente en Target Spectrum, External Record Acquisition, Amplitude Scaling, optional External Spectral Matching y Suite QA.
4. Módulo 06 con representación de modelo no lineal neutral respecto al solver antes de los adaptadores ETABS, Perform-3D u OpenSees; no se elige aún un backend.
5. Módulo 01 separa espectros normativos de resultados probabilísticos importados de OpenQuake/SGC. Los espectros V1 no se etiquetan como curva de tasas de excedencia.
6. `references/` permanece como biblioteca científica. El catálogo ya creado se verifica antes de cualquier reorganización física; no se mueven fuentes en esta tarea.
7. La frontera de línea base V1 comprende los dos casos espectrales, cuatro configuraciones de materiales, el libro M–φ canónico, interfaces CLI/imports, salidas actuales y procedencia. Las fixtures detalladas correspondían a V2-004 a V2-006 y, al cerrar esta acta inicial, aún no se habían capturado.

Siguen **pendientes**, sin impedir congelar V1: el namespace definitivo de configs y outputs V2 (V2-010 a V2-014), la política de avance para `best_effort` y modelos sintéticos (contratos/QA V2-012 y V2-015), el período de compatibilidad V1 (V2-025 y revisión V2-065) y la elección/versionado del backend (Issue de contrato de solver). Las rutas mostradas en el plan son propuestas hasta esas decisiones. Ninguna pendiente se interpreta como autorización de implementar, renombrar o mover módulos.

## V2-002 — Estado efectivo congelado

El manifiesto se capturó **antes** de ejecutar V2-003 y de crear este informe. Es una instantánea de contenido, no la afirmación de que el árbol estuviera limpio o de que corresponda íntegramente a `HEAD`. Contiene SHA-256, tamaño y condición de indexado de cada uno de los **436 archivos efectivos** capturados (432 versionados y cuatro no versionados). Los nuevos documentos y logs de esta entrega quedan fuera de esa instantánea por diseño.

- Rama `main`; `HEAD` efectivo `1d1490e17a8cbcd1ee65e3d78d989e19bae7a18f`; Git `2.53.0.windows.4`, localizado en la instalación de GitHub Desktop. No había diferencias indexadas ni modificaciones de archivos versionados al comenzar. Los cuatro archivos no versionados iniciales eran `AGENTS.md`, `docs/BASELINE_TASKS_V2.md`, `docs/MIGRATION_PLAN_V2.md` y `references/catalog.yaml`; están identificados y hasheados en el manifiesto. La presencia de estos archivos impide describir la línea base solo mediante el commit.
- Python `3.12.10` del entorno `.venv_structurelab_pbd_rc`; Windows 11, compilación `10.0.26200`; paquete `structurelab-pbd-rc 0.1.0`; pytest `9.1.1`, Matplotlib `3.11.1`, NumPy `2.5.1`, PyYAML `6.0.3`. El manifiesto registra todas las distribuciones instaladas. Las versiones de Python, NumPy, Matplotlib y del renderizador pueden afectar resultados numéricos, formato o figuras; no se compararon resultados científicos entre entornos en esta tarea.
- Quarto y Typst no estaban disponibles en `PATH`; tampoco se encontró un ejecutable Quarto en las ubicaciones de usuario inspeccionadas. Su versión no puede congelarse para este entorno. El renderizado PDF de amenaza queda sin validar.
- Las **28 entradas** de `references/catalog.yaml` (23 PDF, dos XLSX y tres textos de procedencia) existen y coincidieron con sus SHA-256. El catálogo muestra tres enlaces binarios duplicados. Esto verifica integridad de archivos, no validez científica de cada fuente.

### Inputs canónicos

Los hashes completos de todos los archivos están en el manifiesto. Esta tabla permite identificar de forma inmediata los nueve inputs principales sin alterar sus rutas:

| Archivo | SHA-256 |
|---|---|
| `configs/stage_01/case_01_nsr10_spectra.yaml` | `71e6d729c10f75607b459634f7f86ade69398044919510a6450be25dc20cf289` |
| `configs/stage_01/case_02_sgc_ccp14_spectra.yaml` | `b6cfb6ece04eae78fd4280f20d8f1d520d906ca52875d2bbc262b67ef0f71d4c` |
| `configs/stage_02/confined_concrete/monotonic/Mon_Mander1988.json` | `f15e494be1c496e2a30e8c02432292fe3d28f911dcda4d6b0428ab7b9e91b032` |
| `configs/stage_02/ductile_reinforcing_steel/monotonic/Mon_RDM2019.json` | `dba8a6e78c58974838bca7601201e14690faafd6270625231bff16bc995f5d3b` |
| `configs/stage_02/nonductile_reinforcing_steel/cyclic/Cyc_MP.json` | `ca97e22b5c4a14fe5dfe7f2ef5c4a55dc2c566f10bca4ac67` |
| `configs/stage_02/nonductile_reinforcing_steel/monotonic/Mon_MRO.json` | `bb5974e305c9f91870b4f986967ce1df2c8f05890a229d341a953a268b0aa9c9` |
| `configs/stage_03/section_characterization.yaml` | `42dd8e6ae65cae24911224aeae11bbdae8a60f9f0a678458a2773142f2f337ab` |
| `references/stage_03/excel/M-curvatura.xlsx` | `ce38cc1aca600805cc852e46d7c564ba5646ed5fdcb4ba1bafdbcdddbd27f427` |
| `references/stage_03/excel/M-curvatura tALLER #3.xlsx` | `2bb3b835791e56f6683608b69c1346cf973ea2abc1088d11c6d33e16af510c52` |

Los YAML/JSON y libros Excel son entradas; los PDF y notas del catálogo son fuentes científicas/de procedencia; `outputs/stage_0x/` son artefactos generados existentes, no fixtures verificadas. Antes de las pruebas había 38 archivos y 4 278 365 bytes en `outputs/stage_01`, 39 y 3 524 954 bytes en `stage_02`, y 191 y 8 533 805 bytes en `stage_03`. El manifiesto registra las rutas y hashes de estos archivos. Las pruebas se ejecutaron con salidas bajo un temporal aislado; no se lanzaron runners por defecto contra `outputs/stage_0x/`.

## V2-003 — Diagnóstico de pytest y resultado

El error inicial de `tmp_path` se reprodujo sin tocar tests ni producto: en este entorno restringido, `Path.mkdir(mode=0o700)` devuelve éxito pero la identidad del proceso no puede listar ni escribir dentro de esa carpeta (`PermissionError [WinError 5]`). Con `mode=0o777` en un directorio nuevo del mismo temporal, lectura y escritura sí funcionan. El `--basetemp` de pytest también crea una carpeta `0700`; cambiar solo `TEMP` o apuntar a `.pytest_cache/` no resolvía el problema. La caché preexistente `.pytest_cache/` también rechaza acceso, por lo que se desactivó su plugin en la ejecución.

Se aplicó **solo en el proceso de pytest** un adaptador de `os.mkdir`: cambia `0700` a `0777` únicamente cuando la ruta resuelta está dentro de una raíz temporal nueva y aislada. `TEMP`, `TMP` y `MPLCONFIGDIR` apuntaron a esa raíz. Ninguna formulación ni archivo de `src/` o `tests/` se modificó. En el primer intento con el permiso corregido, una raíz temporal demasiado larga produjo `WinError 206` en cuatro tests de materiales; una raíz corta eliminó ese problema. La secuencia documentada fue: error de permisos, luego cuatro fallos por Quarto y cuatro por ruta larga, y finalmente cuatro fallos solo por Quarto con la raíz corta.

Comando PowerShell reproducible desde la raíz del repositorio, con el mismo entorno y alcance de la corrida final:

```powershell
$runRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('s' + [guid]::NewGuid().ToString('N').Substring(0, 6))
New-Item -ItemType Directory -Path $runRoot | Out-Null
$env:STRUCTURELAB_PYTEST_RUN_ROOT = $runRoot
$env:TEMP = $runRoot
$env:TMP = $runRoot
$env:MPLCONFIGDIR = Join-Path $runRoot 'm'
$env:PYTHONDONTWRITEBYTECODE = '1'
$pythonCode = @'
import os
import sys
from pathlib import Path
import pytest

root = Path(os.environ['STRUCTURELAB_PYTEST_RUN_ROOT']).resolve()
original_mkdir = os.mkdir

def compatible_mkdir(path, mode=0o777, *, dir_fd=None):
    if mode == 0o700 and Path(path).resolve().is_relative_to(root):
        mode = 0o777
    return original_mkdir(path, mode, dir_fd=dir_fd)

os.mkdir = compatible_mkdir
sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '--tb=short', '--basetemp', str(root / 'p')]))
'@
& .\.venv_structurelab_pbd_rc\Scripts\python.exe -c $pythonCode
```

| Corrida | Aprobados | Fallidos | Errores de preparación | Causa de lo no aprobado |
|---|---:|---:|---:|---|
| Revisión previa, sin corrección ambiental | 104 | 0 | 16 | Permisos del temporal de `tmp_path` |
| Permiso corregido, ruta temporal larga | 112 | 8 | 0 | Cuatro ausencias de Quarto y cuatro rutas demasiado largas (`WinError 206`) |
| **Final, raíz temporal corta** | **116** | **4** | **0** | Solo Quarto ausente en cuatro tests de integración Stage 01 |

En la corrida histórica V2-003, pytest clasificó cuatro casos como **`FAILED`** porque `render_quarto_pdf()` lanzó `FileNotFoundError: Quarto was not found as an external system tool.` Fueron fallos durante la ejecución por una dependencia externa ausente, **no fallos de aserción** y no errores de preparación de `tmp_path`. Los tests afectados fueron `test_stage_01_case_01_scales_design_spectrum`, `test_stage_01_case_01_scaling_factors_are_editable`, `test_stage_01_case_02_uses_independent_sgc_values` y `test_stage_01_case_02_requires_sgc_values_only_for_that_case`. No hubo tests omitidos. Esta constatación describe la línea base anterior; la decisión posterior V2-003R eliminó ese renderer en vez de instalarlo. No se sustituyó Quarto por un mock ni se omitieron tests para mejorar el recuento.

Una carpeta de sondeo de permisos bajo `outputs/baseline_acl_probe_287b97ecba8e4f3db57cd3c909ffe65d/448` quedó inaccesible por el mismo ACL que causó el error. Tras verificar su ruta absoluta dentro de `outputs/`, se recuperó el permiso sobre esa carpeta concreta y se retiró todo el sondeo. **No pertenecía a las tres salidas históricas** ni contenía resultados científicos. No se hizo una eliminación amplia sobre `outputs/`.

## Actualización posterior — V2-003R

Por decisión arquitectónica aprobada, Quarto/Typst dejó de ser una dependencia de ejecución de Stage 01. Los **cuatro fallos anteriores correspondían al renderer Quarto eliminado**, no a las formulaciones espectrales. Se retiraron `reports/export_quarto.py`, `reports/stage_01_hazard_report.py` y la llamada obligatoria desde el flujo; los cuatro tests conservan sus verificaciones de cálculo y artefactos, mientras que las aserciones de QMD/PDF se sustituyeron por la ausencia explícita de esas salidas nuevas. Los PDF de materiales generados con Matplotlib y los PDF/QMD históricos de `outputs/stage_01/` permanecen.

La suite completa volvió a ejecutarse con el mismo ajuste ambiental de temporales: **120 passed, 0 failed, 0 setup errors, 0 skipped**. Entre las dos corridas se compararon 20 CSV/TXT Stage 01 presentes en ambas, idénticos byte a byte, y los campos científicos de cuatro YAML comunes, sin diferencias semánticas. La retirada cambia solo claves y archivos de presentación del renderer; no se detectó diferencia numérica o funcional ajena al reporting. [La Issue V2-003R](REMOVE_QUARTO_REPORTING_DEPENDENCY.md) detalla inventario, alcance y verificación. El motor definitivo de reporting se decidirá durante el módulo 12.

Al cerrar V2-003R todavía no se habían capturado las fixtures canónicas V2-004 a V2-006. La suite verde por sí sola no demostraba su equivalencia numérica.

## Actualización posterior — V2-004 a V2-006

Se ejecutaron los dos casos de amenaza, los cuatro modelos de materiales y las diez hojas del libro M–φ en una raíz temporal aislada. Las fixtures y comparaciones con `outputs/stage_0x/` están en [amenaza](BASELINE_HAZARD_V2.md), [materiales](BASELINE_MATERIALS_V2.md) y [secciones](BASELINE_SECTIONS_V2.md); los oráculos completos se guardaron bajo [`tests/fixtures/v1/`](../../tests/fixtures/v1/README.md). Los outputs históricos permanecieron intactos. La suite completa posterior terminó con **120 passed, 0 failed, 0 setup errors**. V2-007 a V2-009 y la migración arquitectónica no se iniciaron.

## Actualización posterior — V2-007 a V2-009

Se caracterizaron los tres modos de invocación CLI, sus códigos de salida, imports y rutas; se inyectaron fallos de cálculo, escritura y promoción exclusivamente en temporales; y se probaron fronteras de idealización, materiales, XLSX e identificadores. La evidencia está en [interfaces](BASELINE_INTERFACES_V2.md), [publicación](BASELINE_PUBLICATION_V2.md) y [fronteras](BASELINE_BOUNDARIES_V2.md). Se añadieron 49 tests de caracterización sin cambiar código productivo ni corregir defectos detectados.

La suite completa posterior terminó con **169 passed, 0 failed, 0 setup errors**. Se verificaron contra SHA-256 los **312 archivos** del manifiesto V2-002 correspondientes a configs, referencias y outputs históricos: **0 diferencias**. Las **133 fixtures científicas** enumeradas en los manifiestos de amenaza (10), materiales (13) y secciones (110) conservaron sus hashes LF: **0 diferencias**. Los checks de permisos temporales de V2-003 se aplicaron solo dentro del proceso de pytest; no se alteraron ACL ni código de producto.

Los defectos registrados incluyen descarte de argumentos en los entrypoints instalados, resolución del libro Stage 03 relativa al CWD, pérdida de resultados al fallar Stage 01/03 tras reset, fallo posterior a promoción de Stage 02, colisiones de carpetas saneadas y creación prematura de una ruta con `../` en Stage 03. Esta memoria termina en V2-009; V2-010 a V2-021 se ejecutaron posteriormente sin modificar la baseline V1.
