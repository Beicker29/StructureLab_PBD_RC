# Modelos de secciones

Los modelos seccionales deben vivir en `src/structurelab_pbd_rc/mechanics/sections/`.

Esta capa recibira materiales y geometria ya definidos. No debe leer directamente YAML ni repetir datos de talleres.

Los supuestos geometricos editables deben entrar por los YAML de taller. Las secciones deben recibir datos ya resueltos desde los workflows o desde objetos de geometria.

Modelos previstos:

- Secciones de fibras.
- Curvas momento-curvatura.
- Diagramas de interaccion axial-momento.
- Capacidad seccional.
