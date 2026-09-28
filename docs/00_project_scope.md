# Alcance del proyecto

`StructureLab_PBD_RC` organiza calculos de analisis basado en desempeno para estructuras de concreto reforzado.

**Estado V2:** la [arquitectura 00–12](ARCHITECTURE_V2.md) tiene cuatro módulos operativos: `project_objectives`, `site_hazard`, `material_characterization` y `section_component_characterization` para curvas M–φ importadas. Los demás módulos siguen pendientes. Las «Etapas» que se describen a continuación son las interfaces V1 conservadas; su numeración no se traslada a V2. La [memoria de cierre](migration/V2_MIGRATION_CLOSURE.md) registra las limitaciones y pruebas.

## Flujos vigentes

- Etapa 1: calculo de amenaza sismica.
- Etapa 2: caracterizacion constitutiva de materiales.
- Etapa 3: caracterizacion de secciones mediante diagramas momento-curvatura.

La Etapa 2 contiene modelos constitutivos independientes por familia y protocolo de carga. Incluye Mander 1988 para concreto confinado, RDM 2019 para acero ductil y modelos monotonico y ciclico para acero no ductil.

## Principios

- Los flujos coordinan lectura, validacion, calculo y escritura; no contienen la teoria central.
- Los modelos y ecuaciones reutilizables viven en `mechanics/`.
- Cada modelo constitutivo de Stage 2 se define en un unico JSON bajo su material y comportamiento.
- Cada JSON de materiales declara `mm`, `MPa` y `mm/mm`; `kN` es una unidad de fuerza global y no se infiere de la combinación mm/MPa sin conversión explícita.
- Las salidas de materiales se separan por proyecto, caso, material, comportamiento y modelo. Stage 02 se reconstruye transaccionalmente desde su caso compartido.
- Los notebooks son para exploracion y visualizacion, no para logica principal.

## Capas principales

- `cli/`: entradas V1 y CLI del workflow V2.
- `core/`: validacion, excepciones, unidades y registro.
- `design/`: orquestación V1; `workflow/`, contratos y DAG V2.
- `services/` y `presentation/`: cálculo vigente preparado en memoria y sus artefactos presentables.
- `io/`: lectura y escritura.
- `mechanics/`: amenaza, secciones y futuros modelos constitutivos.
- `reports/`: figuras, tablas y documentos.

## Referencias

- `references/stage_03/`: documentos y hojas de calculo para caracterizacion de secciones.
- `references/unassigned/`: referencias conservadas que todavia no pertenecen a un dominio vigente.

## Roadmap

El [plan V2](MIGRATION_PLAN_V2.md) reserva para el Frente 2 el modelo base, el motor de fibras, movimientos sísmicos, modelo no lineal neutral, análisis, EDP, fragilidad, pérdidas, riesgo y reporte integral. Esas capacidades no están implementadas por el cierre V1→V2.
