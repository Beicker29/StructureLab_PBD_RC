# V2-007 — Interfaces CLI, imports y rutas V1

**Estado:** caracterización ejecutada el 25 de septiembre de 2026. Se conservaron intactos `src/`, los inputs canónicos, `outputs/stage_0x/` y `tests/fixtures/v1/`. Pruebas: [test_v1_cli.py](../../tests/test_characterization/test_v1_cli.py).

## Contrato observado

| Entrada | Argumentos | Resultado / código de salida |
|---|---|---|
| `stage_01_hazard.run`, `stage_02_material_characterization.run`, `stage_03_section_characterization.run` | `config_path` opcional; `output_root="outputs"` | Devuelven `dict` con `stage_id`, `status="completed"`, `config`, `config_path`, `output_dirs`, `results_path`, `generated_files`, `warnings`. Stage 01 añade `case_id`/`case_result`; Stage 02 añade `cases`, `case_summaries`, `model_reports`; Stage 03 añade `source`, `method`, `sheet_count`, `curve_count`, `sheets`. Stage 02 usa **directorio** para `results_path`; Stage 01/03, archivo JSON. |
| `scripts/run_stage_01.py`, `run_stage_02.py`, `run_stage_03.py` | Pasan `stage_0x` y `sys.argv[1:]` a `cli.run.main()` | `--config` y `--output-root` funcionan; éxito 0; error de carga no capturado 1. |
| `python -m structurelab_pbd_rc.cli.run stage_0x` | Parser compartido; etapa opcional, default `stage_01` | `--help` 0; etapa inválida 2; error de configuración/ejecución no capturado 1; éxito 0. |
| `structurelab-stage-01/02/03` instalados | Wrappers `main_stage_0x()` llaman `main(["stage_0x"])` | Los argumentos de usuario se ignoran; ejecutados desde un CWD temporal sin configs predeterminadas, fallan con 1 por buscar `configs/stage_0x`, aunque se les pase `--config` absoluto. Con configs predeterminadas controladas en el temporal, terminan con 0 y escriben en `./outputs/stage_0x`, dejando vacío el `--output-root` solicitado. **Defecto V1**, corrección prevista en V2-026. |

Los imports públicos probados incluyen los tres `run()`, `cli.run.main`, el mapa `STAGES` y los módulos existentes de `tests/test_imports.py`. La firma exacta de cada `run()` tiene solo `config_path` y `output_root`; no se asume un contrato V2 a partir de la estructura interna de sus diccionarios. La suite existente cubre importaciones y contenido de resultados; las pruebas nuevas congelan firma, dispatch, argumentos y códigos de salida.

## Resolución de rutas

Los tres flujos aceptaron `--config` absoluto y `--output-root` absoluto desde otro CWD cuando todos los archivos referenciados también fueron absolutos. Se ejecutó Stage 01 mediante script, Stage 02 mediante `python -m` y Stage 03 mediante script, todos con resultados en temporales distintos. Stage 01 también aceptó config relativa desde la raíz y desde un CWD temporal que contenía una copia del YAML; `--output-root` relativo se resolvió contra ese CWD.

Las rutas relativas **no** se resuelven respecto al archivo de configuración. Stage 03, invocado desde otro CWD con su YAML canónico absoluto, no encontró `references/stage_03/excel/M-curvatura.xlsx`: devolvió código 1 y ya había creado `output_root/stage_03/data`. Al usar una copia temporal del YAML que referenciaba el libro por ruta absoluta, ejecutó correctamente. Stage 02 resuelve su raíz de config respecto al CWD al cargarla; sus JSON no son un archivo de proyecto V2.

Los sondeos de fallos pasaron rutas a temporales y comprobaron que no existía el `--output-root` suministrado cuando el error ocurría antes de preparar salidas. Las ejecuciones correctas escribieron exclusivamente en sus raíces temporales. Los entrypoints instalados se probaron desde un CWD temporal primero sin configs y luego con defaults controlados: Stage 01 usó una malla corta, Stage 02 un único modelo Mon_MRO y Stage 03 una hoja del libro por ruta absoluta. Así se verificó el fallo y el éxito del dispatch antiguo sin activar los `outputs/` históricos. No se ejecutó ningún comando por defecto desde la raíz del repositorio.

**Clasificación:** el descarte de argumentos de entrypoints y la dependencia del CWD para el libro de Stage 03 son defectos/limitaciones V1 observados; rechazo de una etapa inexistente con código 2 y de una configuración ausente con código 1 son rechazos esperados. No se corrigió ninguno.
