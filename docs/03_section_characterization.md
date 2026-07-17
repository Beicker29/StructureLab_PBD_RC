# Caracterizacion de seccion

La Etapa 3 usa diagramas momento-curvatura para obtener una idealizacion bilineal equivalente de la respuesta seccional.

## Entrada

El archivo de entrada se define en `configs/stage_03/section_characterization.yaml`.

La configuracion indica:

- Archivo `.xlsx` fuente.
- Hojas de calculo a procesar, o `all` para procesar todo el libro.
- Reglas para detectar pares de columnas de curvatura y momento.
- Criterio para definir `phi_u`.
- Tolerancia de energia equivalente.

Cada hoja se procesa como un diagrama independiente. En cada ejecucion se borra la salida previa de `outputs/stage_03/` y se reconstruyen las carpetas de las hojas del Excel vigente.

## Metodo

La idealizacion adoptada es:

```text
(0, 0) -> (phi_y, My) -> (phi_u, Mu)
```

Donde `My` no es necesariamente la primera fluencia fisica del acero. En esta etapa, `My` es la resistencia de fluencia efectiva del sistema bilineal equivalente.

El procedimiento implementado es:

1. Leer la curva real `(phi_i, M_i)`.
2. Definir `phi_u` por criterio de desempeno, limite del analisis o caida post-pico.
3. Interpolar `Mu = M(phi_u)`.
4. Calcular `A_real` por integracion trapezoidal.
5. Iterar sobre valores candidatos de `My`.
6. Para cada `My`, calcular `M_60My = 0.60 * My`.
7. Interpolar `phi_60My` sobre la rama ascendente.
8. Calcular `Ke = M_60My / phi_60My`.
9. Calcular `phi_y = My / Ke`.
10. Calcular `Kp = (Mu - My) / (phi_u - phi_y)`.
11. Calcular `alpha = Kp / Ke`.
12. Calcular `A_bilinear`.
13. Seleccionar el `My` que minimiza `abs(A_bilinear - A_real) / A_real`.

## Salidas

La Etapa 3 genera un indice agregado y una subcarpeta por hoja:

- `outputs/stage_03/data/stage_03_results.json`
- `outputs/stage_03/<hoja>/data/moment_curvature_curves.csv`
- `outputs/stage_03/<hoja>/data/bilinear_curves.csv`
- `outputs/stage_03/<hoja>/data/bilinearization_parameters.csv`
- `outputs/stage_03/<hoja>/data/stage_03_sheet_results.json`
- `outputs/stage_03/<hoja>/figures/moment_curvature_real.png`
- `outputs/stage_03/<hoja>/figures/moment_curvature_bilinearization.png`
- `outputs/stage_03/<hoja>/figures/moment_curvature_real_vs_bilinear.png`
- `outputs/stage_03/<hoja>/reports/<curva>/<curva>_bilinearization.yaml`

Los parametros reportados son:

- `Ke`
- `My`
- `phi_y`
- `Kp`
- `alpha`
- `Mu`
- `phi_u`
- `A_real`
- `A_bilinear`
- Error relativo de energia
- Ductilidad de curvatura `phi_u / phi_y`
