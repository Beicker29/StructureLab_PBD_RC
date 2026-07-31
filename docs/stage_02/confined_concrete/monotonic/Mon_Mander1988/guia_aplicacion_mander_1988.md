# Mon_Mander1988

Modelo monotonico de concreto confinado basado en:

Mander, J. B., Priestley, M. J. N. y Park, R. (1988), *Theoretical
Stress-Strain Model for Confined Concrete*.

Fuente local:

`references/stage_02/confined_concrete/monotonic/Mander_Priestley_Park_StressStrainModelforConfinedConcrete.pdf`

## Alcance

La implementacion contiene:

- secciones rectangulares confinadas por flejes;
- secciones circulares confinadas por aros;
- secciones circulares confinadas por espiral;
- envolvente monotonica de compresion de Popovics;
- segmento elastico de traccion definido por `f_t` y `Ec`;
- deformacion ultima mediante la expresion simplificada seleccionada para
  el proyecto.

No contiene reglas ciclicas ni la superficie multiaxial de William-Warnke.

## Presion efectiva rectangular

Para una seccion rectangular:

```text
rho_s = rho_x + rho_y
f_l = 0.5 * k_e * rho_s * fyh
```

`f_lx` y `f_ly` se calculan y reportan como diagnosticos, pero la resistencia
confinada usa la presion escalar `f_l`.

## Envolvente

```text
Ec = input
f_cc = f_co * (-1.254 + 2.254*sqrt(1 + 7.94*f_l/f_co) - 2*f_l/f_co)
epsilon_cc = epsilon_co * (1 + 5*(f_cc/f_co - 1))
Esec = f_cc / epsilon_cc
r = Ec / (Ec - Esec)
x = epsilon_c / epsilon_cc
f_c = f_cc*x*r / (r - 1 + x^r)
```

La rama de traccion usa:

```text
epsilon_t = f_t / Ec
f_c = Ec * epsilon_c       para -epsilon_t <= epsilon_c <= 0
```

El criterio ultimo adoptado es:

```text
epsilon_cu = 0.004 + 1.4*rho_s*fyh*epsilon_su/f_cc
```

Esta ultima expresion es el criterio simplificado elegido para el proyecto;
no corresponde a la solucion por balance energetico de las ecuaciones 59 a
64 del articulo.

## Convencion

Stage 02 exporta deformacion y esfuerzo de compresion con signo positivo.
La traccion se representa con deformacion y esfuerzo negativos.
