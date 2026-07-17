# Modelos de materiales

Los modelos de materiales deben vivir en `src/structurelab_pbd_rc/mechanics/materials/`.

Las ecuaciones mecanicas reutilizables de los modelos constitutivos deben vivir
en modulos explicitos como `mechanics/materials/concrete/equations.py`.

Los parametros de entrada de cada modelo se definen en
`configs/stage_02/material_characterization.yaml`. Los parametros
derivados, ecuaciones evaluadas y funciones constitutivas se reportan en
`outputs/stage_02/reports/`.

## Etapa 2

El documento base de la Etapa 2 pide preparar curvas esfuerzo-deformacion para:

- Concreto no confinado.
- Concreto confinado con modelo clasico de Mander.
- Concreto confinado con modelo ajustado de Mander.
- Concreto confinado y no confinado con Attard-Setunge.
- Acero longitudinal a traccion.
- Acero longitudinal a compresion con y sin degradacion por pandeo.
- Malla electrosoldada con datos de Carrillo et al. 2019.

## Implementado

- Concreto no confinado con curva esfuerzo-deformacion de compresion positiva y rama de traccion negativa.
- Mander clasico para concreto confinado con `fcc`, `eps_cc`, `eps_cu`, `Esec`, `r`, `rho_s`, `ke` y `fl_eff`.
- Mander ajustado con resistencia confinada ajustada y deformacion ultima conservadora.
- Attard-Setunge no confinado y confinado con ramas ascendente y descendente explicitas.
- Acero longitudinal en traccion con ramas elastica, fluencia y endurecimiento.
- Acero longitudinal en compresion sin pandeo.
- Acero longitudinal en compresion con expresiones de perdida de resistencia, deformacion de pandeo y degradacion exponencial.
- Malla electrosoldada con tabla del PDF para diametros 4, 5 y 6 mm.

## Convencion de signos

Para las curvas comparativas de la Etapa 2 la convencion editable vive en
`configs/stage_02/material_characterization.yaml`, dentro de
`curve_generation.sign_convention`.

- Concreto no confinado: compresion positiva y traccion negativa.
- Acero en compresion: compresion positiva.
- Acero en traccion y malla: traccion positiva.

## Limitaciones

- La curva de malla electrosoldada usa la forma de alto orden legible del PDF y se limita a `fu` para evitar sobre-resistencia no fisica por el termino elastico.
- Los modelos son monotonicamente orientados a la Etapa 2.
- Cualquier supuesto necesario para reproducir una curva debe quedar como input editable o como parametro calculado en el reporte del modelo correspondiente.
