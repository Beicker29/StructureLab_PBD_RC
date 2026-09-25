# V2-006 — Línea base de curvas M–φ importadas V1

**Estado:** libro canónico ejecutado en una raíz aislada; diez hojas, veinte ramas y dos árboles de salida por hoja capturados sin cambiar el importador ni la idealización. La corrida está en [el log canónico](canonical_run_v1.log); los valores completos están en [el manifiesto de fixtures](../../tests/fixtures/v1/sections/manifest.json) y en sus CSV/YAML.

## Inputs, unidades y detección

| Input | SHA-256 |
|---|---|
| `configs/stage_03/section_characterization.yaml` | `42dd8e6ae65cae24911224aeae11bbdae8a60f9f0a678458a2773142f2f337ab` |
| `references/stage_03/excel/M-curvatura.xlsx` | `ce38cc1aca600805cc852e46d7c564ba5646ed5fdcb4ba1bafdbcdddbd27f427` |

El config declara curvatura **1/m** y momento **kN-m**; por cociente, `Ke` y `Kp` se expresan en **kN-m²**, y el área ∫M dφ en **kN**. Las ramas positivas/negativas conservan el signo en `phi` y `moment`; `phi_abs` y `moment_abs` son magnitudes usadas por la idealización. La detección usa título en fila 1, encabezado en fila 2, primer dato en fila 4, columnas **A/B** para flexión positiva y **C/D** para negativa en las diez hojas. El método es `asce_fema_energy_equivalent_m_phi`, con fracción de rigidez 0,60, tolerancia 0,001, 5000 puntos de búsqueda y último por primera caída pospico a 80 %.

El orden siguiente es el orden real del libro y del procesamiento. Las comillas muestran el nombre **exacto** de la hoja; en dos nombres el espacio anterior a la comilla final forma parte del nombre. La carpeta de salida elimina ese espacio final, hecho que debe respetar cualquier futura asociación por ID.

| Nº | Nombre exacto de hoja | Carpeta de salida | Estado mono (+/−) | Estado `ciclica` (+/−) | Corte positivo `ciclica` |
|---:|---|---|---|---|---|
| 1 | `"V1 (2-3)T"` | `V1 (2-3)T` | converged / best_effort | converged / best_effort | configurado: φ=0,085863; M=753,754 |
| 2 | `"V1 (1-2 y 3-4)T"` | `V1 (1-2 y 3-4)T` | converged / converged | converged / converged | auto |
| 3 | `"V2 (2-3, C-D y A-B)L"` | `V2 (2-3, C-D y A-B)L` | converged / converged | converged / converged | configurado: φ=0,114283; M=531,501 |
| 4 | `"V2 (1-2 y 3-4)L "` | `V2 (1-2 y 3-4)L` | converged / converged | converged / converged | auto |
| 5 | `"V2 (C-B)L "` | `V2 (C-B)L` | converged / converged | converged / converged | auto |
| 6 | `"V2 (D-C y B-A)T"` | `V2 (D-C y B-A)T` | converged / converged | converged / converged | configurado: φ=0,114283; M=587,672 |
| 7 | `"V2 (C-B)T"` | `V2 (C-B)T` | converged / converged | converged / converged | auto |
| 8 | `"V3 (D-C Y B-A)T"` | `V3 (D-C Y B-A)T` | converged / converged | converged / converged | auto |
| 9 | `"V3 (C-B)T"` | `V3 (C-B)T` | converged / converged | converged / converged | auto |
| 10 | `"V2(0-1 Y 4-5)35X50"` | `V2(0-1 Y 4-5)35X50` | converged / converged | converged / converged | auto |

Todos los cortes negativos son `auto`. El CSV `cyclic_cut_points.csv` de cada hoja conserva modo, punto explícito o campos vacíos cuando aplica `auto`. Los tres cortes explícitos positivos producen una envolvente recortada y una bilineal recalculada; las otras siete hojas reutilizan la curva monotónica en esa salida. **`ciclica/` no representa una historia histérica** con descarga, recarga o disipación por ciclos.

## Parámetros, estados y warning que se conservan

Cada rama y modo conserva `Ke`, `My`, `phi_y`, `Kp`, `alpha`, `Mu`, `phi_u`, valores con signo, `M_60My`, pico, áreas real/bilineal, error relativo, ductilidad y estado. En las tres hojas con corte también se guardan `cyclic_cut_phi`, `cyclic_cut_moment`, `phi_u_ciclico` y `Mu_ciclico`. Los CSV de curva real y bilineal conservan **todos** los puntos, no solo los parámetros resumen.

La etapa y todas las hojas reportan `status=completed`, pero `V1 (2-3)T/negative_bending` tiene **`best_effort`** tanto en `monotonica` como en `ciclica`: error relativo absoluto `0,008371918583139567`, mayor que la tolerancia `0,001`. El warning agregado es exactamente `V1 (2-3)T/negative_bending: bilinearization did not reach tolerance; best error = 0.008372.` Se congela esta discrepancia entre estado de ejecución y calidad numérica; no se la corrige ni se interpreta `completed` como aceptación.

## Artefactos y comparación histórica

Se copiaron **70 CSV y 40 YAML de resultados por curva**, 110 archivos científicos textuales, bajo `tests/fixtures/v1/sections/stage_03/`. El manifiesto contiene por cada uno columnas, filas y `sha256_lf`, además de los **40 conjuntos completos de parámetros** (dos ramas × dos modos × diez hojas), advertencias, configuración resuelta, nombres exactos y mapeo de carpetas. Se registró el esquema de 21 JSON de resultado con rutas de corrida, sin congelar esas rutas absolutas. Los **60 PNG** se inventariaron por separado, sin usarlos como oráculo numérico. La etapa no produce XLSX nuevos: el libro Excel es un input.

Los 110 archivos científicos son idénticos a sus equivalentes en `outputs/stage_03/`; los parámetros, curvas detectadas, warnings y estados de los 20 JSON por hoja también coinciden semánticamente. Los 191 archivos históricos Stage 03 conservaron sus hashes de V2-002. No se ejecutó el libro alternativo ni pruebas de bordes: corresponden a tareas posteriores.

## Comparabilidad futura con un motor de fibras

| Disponible en esta línea base | Información adicional necesaria para comparar un motor nativo |
|---|---|
| Pares M–φ por rama, unidades, signo y punto último adoptado | Geometría y recubrimiento de sección, discretización de fibras y posiciones/áreas de barras |
| Envolvente externa importada e idealización de energía | Carga axial y condición de equilibrio; leyes y conjuntos de materiales realmente asignados |
| Etiquetas de hoja y cortes de posprocesamiento | Procedencia del modelo que produjo cada curva, criterios de falla y condiciones de carga equivalentes |

Por ello, una coincidencia de forma o de `My` con el futuro motor no bastaría para afirmar validación física. Esta captura es un benchmark del **importador e idealizador V1** y conserva expresamente sus límites. La [suite completa posterior](pytest_v2_004_006.log) terminó con **120 passed**.
