# Frente 2 · 1A — `MaterialDefinition`

`MaterialDefinition` es el contrato V2 del **material físico**, ubicado en `structurelab_pbd_rc.contracts.materials`. Sirve para identificar materiales creados en StructureLab o nombrados por software externo, sin calcular leyes constitutivas ni incorporar curvas. Esta entrega no conecta el contrato con el handler actual de `material_characterization`.

| Campo | Significado |
|---|---|
| `schema_version` | Versión del contrato; actualmente `"2"` |
| `material_id` | Identidad interna estable, independiente de nombres de programas externos |
| `source` | Origen declarado, por ejemplo `structurelab`, `etabs`, `sap2000` o `user` |
| `external_name` | Nombre original opcional; se conserva literalmente y nunca sustituye a `material_id` |
| `material_type` | `concrete` o `reinforcing_steel`; otro tipo exige una extensión explícita del contrato |
| `nominal_strengths` | Solo propiedades básicas: `fc` para concreto; `fy` y `fu` opcional para acero |
| `units` | Sistema interno fijo: longitud `mm`, esfuerzo `MPa`, fuerza `kN` |
| `constitutive_references` | Cero o más vínculos con resultados científicos publicados por el módulo 03 |

`fc`, `fy` y `fu` son **magnitudes positivas en MPa**, no los signos de una historia esfuerzo–deformación. El contrato rechaza `fu < fy`, claves de otro tipo de material y parámetros de formulaciones introducidos como propiedades nominales. El mapa de propiedades permite añadir en el futuro nuevas propiedades básicas reconocidas sin cambiar la forma serializada; cada ampliación deberá definir su unidad y validación. Las conversiones de unidades y signos se realizan en las fronteras V2 o en futuros adapters, nunca de forma implícita aquí.

Cada `ConstitutiveReference` declara un `role` único dentro del material (por ejemplo `confined`, `unconfined`, `tension` o `compression`), `model_id`, proyecto, revisión, caso y corrida. Contiene el `ArtifactManifest` del **resultado científico** de Stage 03, con `artifact_id`, URI relativa, SHA-256 y `ProcessProvenance`. Su propiedad `dependency` expone el par `ArtifactDependency` existente. Un material puede vincular resultados distintos del mismo modelo para roles distintos; no se duplica ninguna curva. Una referencia sin resultado publicado suficiente, sin procedencia o repetida se rechaza. El consumidor deberá comprobar que el artefacto publicado existe y que sus bytes coinciden con el manifiesto antes de usarlo.

Quedan fuera de 1A las reglas ACI/ASCE, la evaluación de formulaciones, múltiples conjuntos de parámetros en Stage 03, `SectionDefinition`, fibras, importación/exportación ETABS o SAP2000, API CSI, rótulas y análisis estructural. Los resultados V1 y la implementación científica actual permanecen intactos.

**Verificación:** 28 tests del contrato y suite V1+V2 completa: **314 passed, 0 failed, 0 errors, 0 skipped**. Los 268 outputs históricos y las fixtures científicas V1 conservaron sus hashes.
