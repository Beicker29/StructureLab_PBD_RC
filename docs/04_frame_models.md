# Modelos de porticos y desempeno

Los modelos de porticos deben vivir en `src/structurelab_pbd_rc/mechanics/frames/`.

La evaluacion de desempeno debe vivir en `src/structurelab_pbd_rc/mechanics/performance/`.

Responsabilidades previstas:

- Geometria de porticos.
- Cargas y combinaciones.
- Diseno convencional.
- Diseno por capacidad.
- Analisis pushover.
- Comparacion demanda/capacidad.
- Estados de dano, ductilidad y energia.

Los criterios y supuestos de cada portico se documentaran como entradas YAML y como reportes generados por el workflow correspondiente.
