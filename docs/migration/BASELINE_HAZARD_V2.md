# V2-004 — Línea base de amenaza espectral V1

**Estado:** capturada y comparada con los outputs históricos; sin cambios de formulación. Corrida canónica registrada en [el log](canonical_run_v1.log), con salida aislada fuera de `outputs/`. Los datos completos están en [las fixtures de amenaza](../../tests/fixtures/v1/hazard/manifest.json) y sus CSV/TXT asociados.

## Inputs y contrato

| Caso | Input canónico | SHA-256 |
|---|---|---|
| `case_01_nsr10` | `configs/stage_01/case_01_nsr10_spectra.yaml` | `71e6d729c10f75607b459634f7f86ade69398044919510a6450be25dc20cf289` |
| `case_02_sgc_ccp14` | `configs/stage_01/case_02_sgc_ccp14_spectra.yaml` | `b6cfb6ece04eae78fd4280f20d8f1d520d906ca52875d2bbc262b67ef0f71d4c` |

Ambos retornaron `stage_id=stage_01`, `status=completed`, `warnings=[]`, 501 períodos entre **0 y 5 s** con paso de **0,01 s**, y tres columnas de aceleración espectral en **g** para 31, 475 y 2500 años. Las ordenadas son no negativas; no son historias con signo. El caso NSR-10 conserva `Aa=0,35`, `Av=0,30`, `Fa=1,15`, `Fv=1,70`, `T0=0,12670807453416152 s`, `Tc=0,6081987577639753 s` y `TL=4,08 s`. En SGC + CCP-14, el perfil es D y el manifiesto contiene `PGA`, `Ss`, `S1`, `Fpga`, `Fa`, `Fv`, `As`, `SDS`, `SD1`, `T0` y `Ts` por período de retorno.

| Caso / Tr [años] | Sa(0) [g] | Sa(1 s) [g] | máximo tabulado [g] | primer T del máximo [s] |
|---|---:|---:|---:|---:|
| NSR-10 / 31 | 0,140875 | 0,2142 | 0,3521875 | 0,13 |
| NSR-10 / 475 | 0,4025 | 0,612 | 1,00625 | 0,13 |
| NSR-10 / 2500 | 0,60375 | 0,918 | 1,509375 | 0,13 |
| SGC + CCP-14 / 31 | 0,11080058813095094 | 0,06484641283750534 | 0,2287165403366089 | 0,06 |
| SGC + CCP-14 / 475 | 0,35743376391856246 | 0,2851040449996466 | 0,8043393591776179 | 0,08 |
| SGC + CCP-14 / 2500 | 0,582956075668335 | 0,4958266458597606 | 1,2285121047643541 | 0,09 |

La tabla es un índice humano; las **501 filas completas por caso**, los parámetros y los campos `datos_de_entrada`/`datos_de_salida` están congelados sin redondeo adicional en las fixtures. Los valores SGC son inputs configurados a los que se aplica la forma CCP-14; **no** constituyen una curva probabilística de excedencia ni una importación OpenQuake.

## Artefactos científicos y formato

- Se copiaron **cuatro CSV** (espectros y parámetros de ambos casos) y **seis TXT ETABS** a `tests/fixtures/v1/hazard/stage_01/`. Cada CSV guarda nombre y orden de columnas, filas y `sha256_lf` en el manifiesto.
- Cada TXT ETABS contiene **501 líneas, dos columnas separadas por tabulador, cero líneas de encabezado y ocho decimales** tanto para T [s] como para Sa [g]. Se conserva el orden de los períodos y de los niveles.
- Cuatro XLSX generados tienen una hoja cada uno (`case_01_spectra`, `case_01_parameters`, `case_02_spectra`, `case_02_parameters`). Sus celdas y encabezados se compararon con el CSV correspondiente y con el XLSX histórico: sin diferencias semánticas. No se copian los binarios XLSX a las fixtures.
- Los dos YAML de reporte y los dos JSON de resultado mantienen datos de entrada/salida, estado y warnings. Sus esquemas figuran en el manifiesto; las rutas absolutas de `generated_files` no se congelan como datos científicos.
- Se inventariaron **ocho figuras PNG** originales, sin copiarlas ni exigir igualdad binaria. La corrida nueva produjo 26 archivos Stage 01 frente a 38 históricos: faltan únicamente los dos QMD, dos PDF y ocho copias de figuras en `reports/<case_id>/assets` retirados en V2-003R. Los PDF/QMD históricos permanecen en `outputs/`.

## Comparación y límites

Los cuatro CSV nuevos son idénticos byte a byte a los históricos. Las 501 líneas de cada uno de los seis TXT son idénticas; el checkout histórico usa CRLF y la nueva escritura LF. Git informa `i/lf w/crlf attr/text=auto` y `core.autocrlf=true` para esos TXT, por lo que se compara su contenido tras normalizar fin de línea, sin ocultar la diferencia de bytes. Los campos científicos de ambos YAML también coinciden. Los hashes de los outputs históricos registrados en V2-002 permanecen intactos.

Esta captura fija **resultados V1**, no certifica la fuente SGC ni el uso de los espectros como amenaza probabilística para riesgo. Una comparación futura en otro entorno debe separar tolerancia numérica por magnitud del redondeo ETABS de ocho decimales. La [suite completa posterior](pytest_v2_004_006.log) terminó con **120 passed**. No se ejecutó V2-007 ni se probó CLI desde otro directorio.
