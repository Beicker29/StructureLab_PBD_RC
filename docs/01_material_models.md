# Modelos de materiales

Los modelos de materiales deben vivir en `src/structurelab_pbd_rc/materials/`.

## Taller 1

El PDF del Taller 1 pide preparar curvas esfuerzo-deformacion para:

- Concreto no confinado.
- Concreto confinado con modelo clasico de Mander.
- Concreto confinado con modelo ajustado de Mander.
- Concreto confinado y no confinado con Attard-Setunge.
- Acero longitudinal a traccion.
- Acero longitudinal a compresion con y sin degradacion por pandeo.
- Malla electrosoldada con datos de Carrillo et al. 2019.

## Implementado en Paso 4

- Concreto no confinado con curva esfuerzo-deformacion de compresion positiva.
- Mander clasico para concreto confinado con `fcc`, `eps_cc`, `eps_cu`, `Esec`, `r`, `rho_s`, `ke` y `fl_eff`.
- Mander ajustado con resistencia confinada ajustada y deformacion ultima conservadora.
- Attard-Setunge no confinado y confinado con ramas ascendente y descendente explicitas.
- Acero longitudinal en traccion con ramas elastica, fluencia y endurecimiento.
- Acero longitudinal en compresion sin pandeo.
- Acero longitudinal en compresion con expresiones de perdida de resistencia, deformacion de pandeo y degradacion exponencial.
- Malla electrosoldada con tabla del PDF para diametros 4, 5 y 6 mm.

## Convencion de signos

Para las curvas comparativas del Taller 1 se usa:

- Concreto: compresion positiva.
- Acero en compresion: compresion positiva.
- Acero en traccion y malla: traccion positiva.

## Limitaciones

- La curva de malla electrosoldada usa la forma de alto orden legible del PDF y se limita a `fu` para evitar sobre-resistencia no fisica por el termino elastico.
- Los modelos son monotonicamente orientados al Taller 1; no sustituyen todavia modelos ciclicos ni modelos de seccion.
