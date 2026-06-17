# Alcance del proyecto

`StructureLab_PBD_RC` organiza los talleres como una herramienta progresiva. Cada taller debe aportar modelos, datos o resultados reutilizables por talleres posteriores.

## Principios

- Los talleres no son scripts independientes.
- Los workflows solo orquestan lectura de datos, llamadas a modulos y escritura de resultados.
- La teoria central se implementa una sola vez en los paquetes generales.
- Los datos del problema se leen desde YAML.
- Los resultados se guardan bajo `outputs/workshop_xx/`.

## Capas principales

- `core/`: unidades, constantes, validacion, excepciones y registro de modelos.
- `materials/`: concreto, acero, barras, mallas y propiedades mecanicas.
- `geometry/`: secciones, nucleo confinado y distribucion de refuerzo.
- `sections/`: fibras, momento-curvatura, interaccion y capacidad seccional.
- `elements/`: vigas, columnas, rotulas plasticas y estados limite.
- `frames/`: porticos, cargas, diseno convencional, diseno por capacidad y pushover.
- `performance/`: demanda/capacidad, dano, ductilidad y energia.
- `reporting/`: tablas, graficas y reportes.

