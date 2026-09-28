# V2-013 a V2-014 — fronteras y publicación aislada

**Estado:** ejecutadas el 26 de septiembre de 2026.
**Alcance:** contratos de unidades/signos/coordenadas y publicación transaccional de corridas V2.
**Fuera de alcance:** runner y DAG V2-015, invalidación/reutilización V2-016, conversión de proyectos V1→V2 y cambios en kernels científicos.

## V2-013 — unidades, signos y coordenadas en fronteras

`contracts/boundaries.py` incorpora contratos explícitos para:

- magnitud física;
- unidad;
- convención de signo;
- sistema de referencia y eje;
- unidad de origen y destino;
- factor de unidades, factor de signo y fórmula de la conversión.

El registro inicial cubre longitud (`mm`, `cm`, `m`), fuerza (`N`, `kN`), curvatura (`1/mm`, `1/m`), aceleración (`g`, `m/s^2` con gravedad estándar 9,80665 m/s²), esfuerzo (`Pa`, `kPa`, `MPa`), deformación, momento y tiempo. Cada unidad está ligada a una magnitud y se rechazan contratos dimensionalmente incompatibles.

Las convenciones nativas V1 permanecen intactas. Una copia V2 puede declarar y transformar explícitamente `compression_positive_tension_negative` —Mander— a `tension_positive_compression_negative` —aceros— mediante un factor de signo `-1`; no se cambia ninguna respuesta del kernel ni se reescriben CSV V1. Los cambios de sistema de coordenadas o eje se rechazan porque requieren una transformación geométrica explícita que no forma parte de esta Issue.

Toda conversión devuelve un `BoundaryArtifact` nuevo con:

- `artifact_id` propio;
- valores convertidos sin mutar la fuente;
- `ConversionRecord` completo;
- dependencia al artefacto fuente por ID y SHA-256;
- `ArtifactManifest` con unidad, signo, referencia/eje y procedencia.

## V2-014 — publicación transaccional aislada

`io/artifacts.py` publica exclusivamente bajo:

```text
<output_root>/v2/<project_id>/<design_revision>/<case_id>/<run_id>/
```

Cada corrida escribe primero en `<output_root>/v2/.staging/<run_id>.<uuid>.tmp`, en el mismo volumen. Antes de promover se verifica:

- al menos un `StageResult`;
- `execution_status=completed` para cada resultado;
- identidades de etapa no duplicadas;
- IDs/dependencias de artefactos;
- existencia, URI relativa y SHA-256 de cada archivo;
- ausencia de archivos no declarados;
- manifiesto final de corrida escrito como señal de publicación completa.

La validación no exige `performance_acceptance=accepted`. `execution_status`, `numerical_quality`, `applicability` y `performance_acceptance` se serializan por separado; una corrida completada y todavía `not_evaluated` se publica sin reclasificarla.

La promoción usa un rename de directorio en el mismo volumen y prohíbe reemplazar un `run_id` existente. Los fallos antes o durante escritura y antes de promoción eliminan solo el temporal de esa transacción. Un fallo durante la promoción conserva el temporal en estado `ready`; la recuperación vuelve a validar manifiesto, identidad y hashes antes de promoverlo. Los temporales incompletos se descartan únicamente dentro de `.staging`. Una colisión deja tanto la corrida publicada como el temporal recuperable intactos.

Los tests verifican una corrida anterior, dos casos, dos revisiones, colisión de `run_id`, recuperación y rechazo de rutas que intenten escapar del temporal. También mantienen un centinela V1 en `outputs/stage_01` para comprobar que la publicación V2 no lo borra ni reemplaza.

## Evidencia de tests

Las 21 pruebas nuevas de V2-013/014 aprobaron. La suite completa V1+V2 recolectó 206 casos y terminó así:

| Resultado | Cantidad |
|---|---:|
| Passed | 200 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 6 |

Comando y duración:

```text
python -m pytest -q -ra
200 passed, 6 skipped in 32.67s
```

Cada omisión fue reportada individualmente por pytest:

| Test omitido | Razón |
|---|---|
| `test_installed_entrypoint_discards_cli_arguments[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_installed_entrypoint_discards_cli_arguments[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |
| `test_exe_defaults[01]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-01.exe`. |
| `test_exe_defaults[02]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-02.exe`. |
| `test_exe_defaults[03]` | No existe `.venv_structurelab_pbd_rc/Scripts/structurelab-stage-03.exe`. |

Las omisiones pertenecen a la caracterización V1 de entrypoints instalados y conservan la razón histórica ya documentada. No hubo omisiones V2, fallos ni errores de preparación.
