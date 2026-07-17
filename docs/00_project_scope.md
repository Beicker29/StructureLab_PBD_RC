# Alcance del proyecto

`StructureLab_PBD_RC` organiza el proyecto por etapas tecnicas. La Etapa 1 implementa el calculo de amenaza, comenzando por espectros sismicos. La Etapa 2 implementa una herramienta reproducible de caracterizacion mecanica de materiales y la Etapa 3 caracteriza secciones a partir de diagramas momento-curvatura.

## Principios

- Cada etapa no es un script aislado.
- El flujo de cada etapa solo orquesta lectura de datos, llamadas a modulos y escritura de resultados.
- La teoria central se implementa una sola vez en los paquetes generales.
- Los datos del problema se leen desde YAML.
- Los resultados se guardan bajo `outputs/stage_01/`, `outputs/stage_02/`, `outputs/stage_03/`, etc.
- Los supuestos editables viven en los YAML de entrada; los valores calculados y ecuaciones usadas se reportan en los YAML de salida.

## Capas principales

- `cli/`: entrada por consola para ejecutar las etapas disponibles.
- `core/`: unidades, constantes, validacion, excepciones y registro de modelos.
- `design/`: orquestacion de los flujos de calculo por etapa.
- `io/`: lectura de configuraciones y escritura de resultados.
- `mechanics/`: ecuaciones mecanicas, modelos constitutivos, geometria basica, metricas de curvas y herramientas de seccion.
- `reports/`: tablas, graficas, YAML, PDF y artefactos de salida.

## Documentacion

Los archivos de `docs/` documentan alcance, arquitectura y responsabilidades de cada capa. Los supuestos editables deben estar cerca de los datos que controlan, en los YAML de `configs/<stage_id>/`, o en los reportes generados bajo `outputs/<stage_id>/reports/`.

## Referencias

Las referencias externas se organizan por etapa:

- `references/stage_02/`: documentos, imagenes y ecuaciones fuente para caracterizacion de materiales.
- `references/stage_03/`: documentos, hojas de calculo e imagenes fuente para caracterizacion de seccion.
- `references/unassigned/`: referencias historicas conservadas que todavia no pertenecen a una etapa vigente.

## Roadmap

- Etapa 1: calculo de amenaza, con primer modulo sismico implementado.
- Etapa 2: caracterizacion mecanica de materiales.
- Etapa 3: caracterizacion de la seccion mediante bilinealizacion del diagrama momento-curvatura.
- Etapas posteriores: se definiran cuando la Etapa 3 este consolidada.
