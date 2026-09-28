# V2-020 — servicio de importación M–φ y caracterización de secciones

**Estado:** ejecutada el 26 de septiembre de 2026.  
**Alcance:** extracción del procesamiento científico de las curvas M–φ importadas hacia un servicio completamente en memoria.  
**Fuera de alcance:** V2-021 y posteriores, handler/publicación V2 de secciones, presentación nueva y motor nativo de fibras.

## Frontera del servicio

`services/section_characterization.py` recibe dos tipos de entrada ya resueltos:

- `SectionWorksheetInput`: nombre visible y filas estructuradas de una hoja ya leída;
- `SectionCharacterizationInput`: configuración resuelta, hojas seleccionadas y procedencia declarada.

La lectura XLSX queda fuera del servicio. El llamador puede usar el lector V1 existente o construir las filas desde otra fuente, pero el cálculo nunca recibe una ruta ni abre el libro. El servicio tampoco importa CLI, `pathlib`, gráficos, reporting, escritores ni publicación.

`SectionCharacterizationService` detecta los pares curvatura–momento y delega toda operación científica a los kernels existentes:

- `mechanics.sections.moment_curvature.bilinearize_moment_curvature`;
- `mechanics.sections.moment_curvature.truncate_moment_curvature_curve_at_point`;
- indirectamente, `mechanics.idealization.energy_equivalent`.

No se modificaron esos kernels ni se copiaron sus ecuaciones al servicio. También permanecen intactos `stage_03_section_characterization.py`, sus configuraciones y sus outputs históricos.

## Resultado estructurado

El resultado en memoria contiene, por hoja y ramal:

- metadata del ramal detectado y los puntos fuente;
- caracterizaciones `monotonica` y `ciclica`;
- curvas reales y bilineales;
- `phi_u`, `Mu`, `My`, `Ke`, `Kp`, `alpha` y ductilidad;
- áreas real y bilineal, error relativo y error absoluto;
- estado `converged` o `best_effort`;
- warnings y procedencia;
- selección del corte con modo `configured`, `auto`, `absent` o `disabled`.

Las unidades nativas son exclusivamente `1/m` y `kN-m`; el servicio rechaza otras unidades para que cualquier conversión ocurra en las fronteras trazables V2-013. Los signos de los ramales positivo y negativo se preservan en las tablas visibles, mientras el kernel continúa operando con magnitudes positivas como en V1.

## Semántica de `ciclica`

Se conserva el nombre histórico `ciclica` para permitir equivalencia con Stage 03 V1, pero todos los contratos lo identifican como:

```text
response_semantics = truncated_or_reused_monotonic_backbone
is_hysteretic = false
```

Un corte explícito trunca la envolvente y vuelve a ejecutar la misma idealización. Un corte `auto`, ausente o deshabilitado reutiliza exactamente el resultado monotónico. El contrato conserva la razón estructurada; la tabla compatible con V1 continúa serializando esos tres casos sin punto como `mode=auto`. No se introdujeron reglas de descarga, recarga, memoria ni disipación cíclica.

## Compatibilidad V2-006

La regresión recorre las diez hojas canónicas en el orden original y sus 20 ramales. Se compararon directamente los 70 CSV científicos congelados:

- curvas M–φ reales y bilineales de ambos modos;
- parámetros, puntos últimos, rigideces y áreas;
- cortes explícitos y automáticos;
- estados y errores de idealización.

La hoja `V1 (2-3)T` conserva el único resultado `best_effort` en el ramal negativo, incluido el error absoluto `0.008371918583139567` y el warning textual congelado. Los tres cortes positivos explícitos y todos los casos de reutilización coinciden con V1.

Las pruebas adicionales cubren corte ausente, `enabled: false`, ausencia de afirmaciones histeréticas, unidades no nativas, procedencia y ejecución sin efectos sobre filesystem. Al cierre de V2-020 el registro V2 todavía no contenía el handler; su integración y publicación se implementaron posteriormente en [V2-021](SECTION_PUBLICATION_V2_021.md), sin modificar este servicio científico.

## Verificación

Las pruebas específicas terminaron con **8 passed, 0 failed, 0 errors, 0 skipped**:

```text
python -m pytest tests/contracts/test_v2_section_service.py -q -ra
8 passed in 2.00s
```

La suite completa V1+V2 recolectó 275 casos:

| Resultado | Cantidad |
|---|---:|
| Passed | 269 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

```text
python -m pytest -q -ra
269 passed, 6 skipped in 48.01s
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

Las seis omisiones pertenecen a pruebas V1 de entrypoints instalados. No hubo skips V2, fallos, errores de colección ni errores de preparación. Los hashes de `outputs/stage_03` se mantuvieron antes y después de invocar el servicio.
