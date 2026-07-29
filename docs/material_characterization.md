# Caracterizacion de materiales

La Etapa 2 organiza los modelos constitutivos por material y protocolo de carga. Actualmente implementa RDM 2019 para acero ductil y modelos monotonico y ciclico para acero no ductil.

## Familias

| Directorio | Material |
|---|---|
| `confined_concrete` | Concreto confinado |
| `unconfined_concrete` | Concreto no confinado |
| `ductile_reinforcing_steel` | Acero de refuerzo ductil |
| `nonductile_reinforcing_steel` | Acero de refuerzo no ductil |

Cada familia contiene:

- `monotonic/`: modelos para historias de carga monotonica.
- `cyclic/`: modelos para historias de carga ciclica.

## Contrato de ubicacion

El codigo de cada modelo debe ubicarse en:

```text
src/structurelab_pbd_rc/mechanics/materials/<material>/<behavior>/<model>/
```

Cada modelo tiene un unico JSON directamente bajo su familia y comportamiento:

```text
configs/stage_02/<material>/<monotonic|cyclic>/<model>.json
```

El nombre base del archivo y `inputs.model_id` deben coincidir exactamente. Los
identificadores implementados son:

| Identificador | Formulacion | Material | Comportamiento |
|---|---|---|---|
| `Mon_RDM2019` | RDM 2019 | Acero ductil | Monotonico |
| `Mon_MRO` | Ramberg-Osgood modificado | Acero no ductil | Monotonico |
| `Cyc_MP` | Menegotto-Pinto | Acero no ductil | Ciclico |

`configs/stage_02/` no admite archivos sueltos ni directorios diferentes de las cuatro familias. Cada familia debe contener exactamente `monotonic/` y `cyclic/`. Un JSON incluye:

- `stage_id`, `enabled`, `title` y `units`;
- `inputs.project_id`, `inputs.case_id` e `inputs.model_id`;
- `inputs.parameters` y los controles particulares del modelo;
- procedencia y estado de calibracion cuando corresponda.

Los resultados se escriben en:

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

El ejecutor carga todos los JSON habilitados y agrupa sus modelos por `project_id/case_id`. Primero calcula y escribe cada caso en una carpeta temporal. Solo cuando todos sus modelos terminan correctamente reemplaza la carpeta del caso. Otros proyectos y casos existentes no se modifican.

## Convenciones

- Traccion: deformacion y esfuerzo positivos.
- Los modelos con historia firmada representan compresion con deformacion y esfuerzo negativos.
- RDM 2019 calcula internamente la compresion con magnitudes positivas. El CSV y la figura usan signos fisicos: traccion positiva y compresion negativa.
- Longitud: `mm`.
- Esfuerzo y modulo: `MPa`.
- Deformacion: `mm/mm`.
- Cada JSON concentra los parametros, unidades, procedencia y controles de un modelo.
- Un modelo constitutivo no puede estar definido en mas de un JSON.

## RDM 2019

El modelo `Mon_RDM2019` implementa la Tabla 2 de Akkaya, Guner y Vecchio (2019). Representa:

Guia detallada de aplicacion:
[PDF](stage_02/ductile_reinforcing_steel/monotonic/Mon_RDM2019/guia_aplicacion_rdm_2019.pdf) |
[fuente HTML](stage_02/ductile_reinforcing_steel/monotonic/Mon_RDM2019/guia_aplicacion_rdm_2019.html).

- la envolvente monotona de referencia del acero;
- el inicio del pandeo inelastico para `L/D >= 5`;
- la degradacion pospandeo bilineal;
- el piso residual `0.2fy`.

La envolvente de referencia usa:

```text
fs = Es*epsilon                         para epsilon <= epsilon_y
fs = fy                                para epsilon_y < epsilon <= epsilon_sh
fs = fu + (fy-fu)*((epsilon_u-epsilon)/(epsilon_u-epsilon_sh))^P
```

El parametro de pandeo es:

```text
rb = (L/D)*sqrt(fy/100)
```

`epsilon_y`, `buckling_intervals`, `unsupported_length_mm`, `L/D` y `rb` son resultados calculados. El JSON canonico suministra:

- `longitudinal_bar_diameter_mm = D`;
- `tie_bar_diameter_mm = dt`;
- `tie_spacing_mm = s`;
- `effective_tie_leg_length_mm = le`;
- `effective_tie_legs = nl`;
- `restrained_longitudinal_bars = nb`, numero de barras de una cara en la
  direccion evaluada;
- `tie_steel_modulus_MPa = Et`;
- `buckling_restraint_case`, inicialmente `bending` o `pure_compression`.

El usuario debe determinar la longitud efectiva de rama, las ramas efectivas, las barras restringidas y la direccion de pandeo a partir del detalle estructural. El programa no las deduce desde una imagen.

El calculo se ejecuta una sola vez al construir el modelo:

```text
epsilon_y = fy/Es
At = pi*dt^2/4
I = pi*D^4/64
ErI = 0.5*Es*I*sqrt(fy/400)
k = pi^4*ErI/s^3
nb_eff = nb                         para bending
nb_eff = 2*nb                       para pure_compression
kt = (Et*At/le)*(nl/nb_eff)
keq = kt/k
```

El factor `2` de `pure_compression` considera las barras de las dos caras,
tal como se muestra en el ejemplo de viga/columna del boletin B3. Por tanto,
el input `restrained_longitudinal_bars` no debe incluir previamente esa
duplicacion.

La definicion implementada es `keq=kt/k`. La primera pagina de
`B3_VT5UnsupportedLengthRatio_V1.1.pdf` imprime `k/kt`, pero se trata de una
errata interna: el articulo original de Dhakal y Maekawa (2002), la pagina 2
del mismo boletin y todos sus ejemplos numericos emplean `kt/k`.

La seleccion de `n` usa:

| n | Intervalo de keq |
|---:|---:|
| 1 | `keq > 0.7500` |
| 2 | `0.1649 < keq <= 0.7500` |
| 3 | `0.0976 < keq <= 0.1649` |
| 4 | `0.0448 < keq <= 0.0976` |
| 5 | `0.0084 < keq <= 0.0448` |
| 6 | `0.0063 < keq <= 0.0084` |
| 7 | `0.0037 < keq <= 0.0063` |
| 8 | `0.0031 < keq <= 0.0037` |
| 9 | `0.0013 < keq <= 0.0031` |
| 10 | `0.0009 <= keq <= 0.0013` |

Un limite compartido se asigna al `n` mayor, que es la opcion conservadora. Para `keq < 0.0009` se genera un error; no se extrapola a modos mayores que 10. Una restriccion con mayor `kt` aumenta `keq` y solo puede reducir o mantener `n`.

Finalmente:

```text
L = n*s
L/D = n*s/D
rb = (L/D)*sqrt(fy/100)
```

La configuracion incluida produce `keq=1.0018573`, `n=1`, `L=100 mm`, `L/D=5` y `rb=10.24695`. Las pruebas de referencia reproducen tambien:

- boletin B3, viga/columna en flexion: `k=9210.88 N/mm`,
  `kt=40863.03 N/mm`, `keq=4.44`, `n=1` y `L/D=10.23`;
- boletin B3, compresion pura: `kt=5621.52 N/mm`, `keq=0.61`,
  `n=2` y `L/D=20.47`;
- Dhakal y Maekawa (2002), prisma: `keq=1.126` y `n=1`;
- Dhakal y Maekawa (2002), columna a flexion: `keq=0.1015` y `n=3`.

El procedimiento de rigidez implementado aplica inicialmente a secciones
rectangulares con refuerzo transversal. Secciones circulares, losas,
secciones sin refuerzo transversal y otras restricciones requieren
estrategias independientes.

Los casos antiguos que suministran `buckling_intervals` siguen funcionando en modo `legacy_explicit_buckling_intervals`, generan una advertencia de obsolescencia y no pueden mezclar ese valor con las nuevas variables fisicas.

`curve_generation.include_tension` y `curve_generation.include_compression` controlan las ramas exportadas. Una rama de compresion solo se dibuja cuando el modelo la soporta y el input no la deshabilita.

Los autores informan aplicabilidad amplia para `200 < fy < 900 MPa`, `10 < D < 36 mm`, `fu/fy < 2`, `P <= 4`, `epsilon_u > 14epsilon_y`, `8 < rb < 56` y `L/D >= 5`. El modelo emite advertencias cuando un caso de pandeo queda fuera de esos limites, sin alterar silenciosamente la respuesta.

Para `L/D < 5`, no se activa pandeo RDM y la compresion coincide en magnitud con la envolvente de referencia. Para deformaciones mayores que `epsilon_su`, `stress_at_strain` devuelve `0.0`; la curva exportada termina exactamente en su propio `epsilon_su`.

La implementacion RDM 2019 corresponde a una envolvente constitutiva uniaxial monotonica. No incluye reglas historicas ciclicas.

Referencias locales auditadas:

- `references/stage_02/ductile_reinforcing_steel/monotonic/RDM2019/jp116.pdf`: Akkaya,
  Guner y Vecchio (2019), Tabla 2, DOI `10.14359/51711143`;
- `references/stage_02/ductile_reinforcing_steel/monotonic/RDM2019/12587353_2002_ASCESTR_2__Stability.pdf`:
  Dhakal y Maekawa (2002), Tablas 1 a 3, DOI
  `10.1061/(ASCE)0733-9445(2002)128:10(1253)`;
- `references/stage_02/ductile_reinforcing_steel/monotonic/RDM2019/B3_VT5UnsupportedLengthRatio_V1.1.pdf`:
  Salgado y Guner (2014), Tablas 1 y 2 y ejemplos resueltos.

## Ramberg-Osgood modificado

El modelo `Mon_MRO` implementa la envolvente monotonica Ramberg-Osgood modificada:

Guia detallada de aplicacion:
[PDF](stage_02/nonductile_reinforcing_steel/monotonic/Mon_MRO/guia_aplicacion_mon_mro.pdf) |
[fuente HTML](stage_02/nonductile_reinforcing_steel/monotonic/Mon_MRO/guia_aplicacion_mon_mro.html).

```text
epsilon = sigma / Es + (eps_u - fu / Es) * (sigma / fu)^n
```

El dominio publicado que se usa es `0 <= sigma <= fu`, con `n = 20` y `Es = 200000 MPa`. La inversion `sigma(epsilon)` se realiza por biseccion acotada y la tangente se obtiene de la derivada analitica.

La fuente publica los siguientes valores P2 en la Tabla 4 de Carrillo et al.:

| Diametro [mm] | fu [MPa] | eps_u [mm/mm] |
|---:|---:|---:|
| 4 | 538 | 0.0124 |
| 5 | 650 | 0.0113 |
| 6 | 573 | 0.0095 |

No se agrega una meseta de fluencia ni una rama descendente. El JSON incluido usa el perfil de 6 mm y deja `fy_MPa` nulo porque la curva publicada selecciona `fu` P2 y la deformacion ultima media; mezclar un `fy` de otro estadistico produciria un perfil no documentado.

El modelo Ramberg-Osgood modificado implementado para malla electrosoldada representa la respuesta monotonica en traccion. La respuesta monotonica en compresion no cuenta con una calibracion especifica para malla NTC 5806; por defecto se considera no soportada. La opcion simetrica, si se activa, constituye una hipotesis prepandeo y no una validacion experimental.

La politica opcional `symmetric_prebuckling_assumption` exige `compression_strain_limit`, justificacion y aceptacion explicita. No representa pandeo ni degradacion pospandeo.

Fuente primaria: Carrillo et al., *Construction and Building Materials* 211 (2019), ecuacion 6 y tabla 4, DOI `10.1016/j.conbuildmat.2018.11.096`.

## Menegotto-Pinto

El modelo `Cyc_MP` implementa las reglas de historia Menegotto-Pinto de Steel02:

Guia detallada de aplicacion:
[PDF](stage_02/nonductile_reinforcing_steel/cyclic/Cyc_MP/guia_aplicacion_cyc_mp.pdf) |
[fuente HTML](stage_02/nonductile_reinforcing_steel/cyclic/Cyc_MP/guia_aplicacion_cyc_mp.html).

```text
R = R0 * (1 - cR1 * xi / (cR2 + xi))
```

Mantiene estado trial y confirmado, detecta inversiones, actualiza las asintotas y permite `commit`, `revert` y `reset`. La historia se procesa en el orden suministrado, sin ordenar ni eliminar puntos repetidos.

Los parametros `fy`, `Es`, `b`, `R0`, `cR1`, `cR2` y `a1` a `a4` son obligatorios. El repositorio no registra un perfil ciclico calibrado para NTC 5806 porque no se dispuso de la tabla completa de parametros finales de la publicacion primaria. La configuracion heredada incluida usa parametros sinteticos y su estado es `synthetic_algorithm_verification_only`.

El modelo Menegotto-Pinto representa la respuesta axial ciclica dentro del rango y protocolo respaldados por la calibracion seleccionada. No representa por si solo pandeo, degradacion pospandeo, fractura por fatiga de bajo ciclo ni falla de soldaduras.

El criterio opcional `strain_limit` es solamente un criterio de falla por deformacion. No debe interpretarse como fatiga de bajo ciclo. Fuera del rango de validez configurado la respuesta se marca como extrapolada y genera una advertencia.

Fuentes de formulacion: documentacion y codigo fuente de OpenSees Steel02. Contexto experimental NTC 5806: Miranda-Giraldo et al., *Journal of Building Engineering* 117 (2026), articulo 114698; datos experimentales asociados en Zenodo 15330675.

## Entradas y salidas

Los JSON canonicos actuales son:

```text
configs/stage_02/ductile_reinforcing_steel/monotonic/Mon_RDM2019.json
configs/stage_02/nonductile_reinforcing_steel/monotonic/Mon_MRO.json
configs/stage_02/nonductile_reinforcing_steel/cyclic/Cyc_MP.json
```

Los dos modelos de acero no ductil comparten `project_id/case_id`, por lo que se procesan como un caso con ramas monotonica y ciclica. El archivo `model_report.yaml` de cada modelo incluye:

- input completamente resuelto;
- parametros calculados, incluidos `s_over_db`, `L/D` y `rb` cuando aplican;
- metadatos, procedencia y estado de calibracion;
- metricas de respuesta y advertencias;
- rutas de todos los archivos generados.

El CSV/XLSX conserva deformacion, esfuerzo, tangente, rama, sentido incremental, estado de traccion o compresion, inversiones, dominio, falla, fuente y calibracion. El PDF resume el modelo y anexa su figura de respuesta.

## Reglas para nuevos modelos

- No asumir valores por defecto de propiedades mecanicas o unidades.
- Crear exactamente un JSON por modelo bajo su material y comportamiento.
- Exigir `project_id`, `case_id`, `model_id` y `parameters` dentro de `inputs`.
- Usar `mm`, `kN` y `MPa` como convencion base.
- Mantener separadas las formulaciones monotonicas y ciclicas.
- Usar identificadores seguros y evitar combinaciones o rutas duplicadas.
- Agregar pruebas unitarias de ecuaciones y pruebas de integracion de artefactos.
- Documentar la fuente tecnica y los limites de aplicacion de cada modelo.
