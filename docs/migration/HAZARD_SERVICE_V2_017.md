# V2-017 — servicio de espectros preservando Stage 01 V1

**Estado:** ejecutada el 26 de septiembre de 2026.  
**Alcance:** extracción en memoria de los dos casos espectrales existentes e integración del handler V2 `site_hazard`.  
**Fuera de alcance:** V2-018 y posteriores, OpenQuake, PSHA, curvas de excedencia, UHS, desagregación, Conditional Spectrum y cualquier cambio de formulación científica.

## Servicio científico en memoria

`services/hazard_spectra.py` define `HazardSpectraInput`, `HazardSpectraResult` y `compute_hazard_spectra()`. La capa:

- recibe estructuras Python ya resueltas;
- valida los dos casos y sus unidades nativas `s` y `g`;
- invoca directamente el kernel existente `mechanics/hazard/seismic/spectra.py`;
- devuelve períodos, espectros, parámetros de transición, factores y metadatos en memoria;
- no importa CLI, YAML, filesystem, gráficos ni reporting.

El kernel científico no fue movido ni modificado. Stage 01 V1 conserva sus comandos, configuraciones, rutas, publicación y outputs.

Las fronteras V2 declaran:

- período: magnitud `time`, unidad `s`, escalar no negativo;
- ordenada espectral: magnitud `acceleration`, unidad `g`, escalar no negativo;
- producto: espectro normativo NSR-10 o valores SGC con forma CCP-14;
- `probabilistic_hazard_result=false` y `exceedance_curve_available=false`.

Los inputs SGC configurados no se reclasifican como resultado probabilístico.

## Handler y artefactos V2

El registro por defecto contiene ahora `project_objectives` y `site_hazard`; ningún otro módulo científico fue registrado. El handler exige:

- `ProjectSpec` consistente con `RunContext`;
- una referencia de configuración `site_hazard` cuyo hash coincida con los hashes resueltos;
- resultado completado y artefacto de Stage 00;
- procedencia V2-016 completa.

Stage 00 publica una copia explícita de `ProjectSpec`, permitiendo que el hash agregado de su contenido forme parte de la procedencia de Stage 01. La firma de `site_hazard` incluye solo su configuración relevante, versión `spectra-kernel-v1+service-v2-017.1`, hash del input, hash de Stage 00, unidades y convención de signo.

Cada ejecución de `site_hazard` produce nueve artefactos en memoria antes de entregarlos a `TransactionalPublisher`:

1. configuración resuelta JSON;
2. resultado científico JSON;
3. espectros CSV;
4. espectros XLSX;
5. parámetros CSV;
6. parámetros XLSX;
7. TXT ETABS para 31 años;
8. TXT ETABS para 475 años;
9. TXT ETABS para 2500 años.

Todos tienen `ArtifactManifest`, dependencias explícitas, `content_hash`, firma de procedencia, unidades y signo. Los XLSX se construyen determinísticamente en memoria. Los TXT mantienen tabulador, cero encabezados y ocho decimales; CRLF y LF se normalizan solo al comparar contenido científico.

## Equivalencia con V2-004

Se ejecutaron mediante el servicio y el workflow V2:

- `case_01_nsr10`;
- `case_02_sgc_ccp14`.

La regresión compara las 501 filas de cada espectro, todas las filas de parámetros, períodos 0–5 s, parámetros de transición, factores de escalamiento/interpolación y los seis TXT ETABS contra `tests/fixtures/v1/hazard/`. Los CSV coinciden tras normalizar únicamente fin de línea. Los cuatro XLSX V2 reproducen encabezados, cantidad de filas y todas las celdas del CSV congelado.

La publicación V2 contiene Stage 00 → Stage 01 en ese orden. Una segunda corrida con la misma identidad científica reutiliza ambos módulos sin invocar el servicio; un cambio de configuración invalida la cadena conforme a V2-016. Las corridas históricas y `outputs/stage_01` permanecen físicamente intactos.

## Cobertura añadida

Los ocho casos recolectados en `tests/contracts/test_v2_hazard_service.py` verifican:

- equivalencia científica completa de NSR-10 y SGC + CCP-14;
- períodos, espectros, parámetros, escalamiento, CSV, XLSX y TXT ETABS;
- límites de unidades/signos y metadatos no probabilísticos;
- planificación y ejecución Stage 00 → Stage 01;
- publicación transaccional V2;
- provenance en todos los artefactos;
- reutilización sin recalcular;
- invalidación por cambio de configuración;
- registro de `site_hazard` y conservación de outputs V1.

Las pruebas específicas terminaron con **8 passed, 0 failed, 0 errors, 0 skipped**. La suite completa V1+V2 recolectó 246 casos:

| Resultado | Cantidad |
|---|---:|
| Passed | 240 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

Resultado:

```text
python -m pytest -q -ra
240 passed, 6 skipped in 36.51s
```

Cada omisión fue reportada individualmente:

| Test omitido | Razón |
|---|---|
| `test_installed_entrypoint_discards_cli_arguments[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |
| `test_exe_defaults[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_exe_defaults[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_exe_defaults[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |

Las seis omisiones pertenecen a la caracterización V1 de entrypoints instalados. No hubo skips V2, fallos ni errores de colección o preparación.
