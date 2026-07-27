# Alcance del proyecto

`StructureLab_PBD_RC` organiza calculos de analisis basado en desempeno para estructuras de concreto reforzado.

## Flujos vigentes

- Etapa 1: calculo de amenaza sismica.
- Etapa 2: caracterizacion constitutiva de materiales.
- Etapa 3: caracterizacion de secciones mediante diagramas momento-curvatura.

La Etapa 2 esta preparada para cuatro familias de material y dos protocolos de carga. Los modelos constitutivos se incorporaran posteriormente.

## Principios

- Los flujos coordinan lectura, validacion, calculo y escritura; no contienen la teoria central.
- Los modelos y ecuaciones reutilizables viven en `mechanics/`.
- Cada modelo constitutivo de Stage 2 se define en un unico JSON bajo su material y comportamiento.
- Cada JSON declara sus unidades; la convencion es `mm`, `kN` y `MPa`.
- Las salidas de materiales se separan por `project_id/case_id`; solo se reemplazan los casos incluidos en la ejecucion.
- Los notebooks son para exploracion y visualizacion, no para logica principal.

## Capas principales

- `cli/`: entrada por consola para las etapas vigentes.
- `core/`: validacion, excepciones, unidades y registro.
- `design/`: orquestacion de flujos.
- `io/`: lectura y escritura.
- `mechanics/`: amenaza, secciones y futuros modelos constitutivos.
- `reports/`: figuras, tablas y documentos.

## Referencias

- `references/stage_03/`: documentos y hojas de calculo para caracterizacion de secciones.
- `references/unassigned/`: referencias conservadas que todavia no pertenecen a un dominio vigente.

## Roadmap

- Consolidar los flujos de amenaza y seccion existentes.
- Incorporar modelos constitutivos por material y protocolo de carga.
- Definir etapas posteriores cuando sus contratos de entrada y salida esten establecidos.
