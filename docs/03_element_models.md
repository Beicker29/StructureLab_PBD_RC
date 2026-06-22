# Modelos de elementos

Los modelos de elementos deben vivir en `src/structurelab_pbd_rc/mechanics/elements/`.

Esta capa usara secciones y materiales para representar vigas, columnas, rotulas plasticas, estados limite y capacidad de deformacion.

Los talleres posteriores deben importar estos modelos en lugar de reescribirlos dentro de cada workflow.

Los supuestos de modelacion de elementos deben ser parametros explicitos del taller que los use, no documentos paralelos dentro de `docs/`.
