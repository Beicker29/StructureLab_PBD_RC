# Alcance del proyecto

`StructureLab_PBD_RC` organiza los talleres como una herramienta progresiva. Cada taller debe aportar modelos, datos o resultados reutilizables por talleres posteriores.

## Principios

- Los talleres no son scripts independientes.
- Los flujos de taller solo orquestan lectura de datos, llamadas a modulos y escritura de resultados.
- La teoria central se implementa una sola vez en los paquetes generales.
- Los datos del problema se leen desde YAML.
- Los resultados se guardan bajo `outputs/workshop_xx/`.
- Los supuestos editables viven en los YAML de entrada; los valores calculados y ecuaciones usadas se reportan en los YAML de salida.

## Capas principales

- `cli/`: entrada por consola y seleccion de talleres.
- `core/`: unidades, constantes, validacion, excepciones y registro de modelos.
- `design/`: orquestacion de talleres y flujos de calculo.
- `io/`: lectura de configuraciones y escritura de resultados.
- `mechanics/`: ecuaciones mecanicas, modelos constitutivos, geometria, secciones, elementos, porticos y metricas de desempeno.
- `reports/`: tablas, graficas, YAML, PDF y artefactos de salida.

## Documentacion

Los archivos de `docs/` documentan alcance, arquitectura y responsabilidades de cada capa. No se mantiene una carpeta separada de supuestos por taller: esa informacion debe estar cerca de los datos que controla, en `configs/workshops/`, o en los reportes generados bajo `outputs/workshop_xx/reports/`.
