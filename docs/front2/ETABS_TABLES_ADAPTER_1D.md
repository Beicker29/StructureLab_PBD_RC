# Frente 2 · 1D — `ETABSTablesAdapter`

`ETABSTablesAdapter`, en `structurelab_pbd_rc.adapters.etabs.tables`, lee un **XLSX de Database Tables exportado por ETABS** y devuelve `ETABSImportResult` con `StructuralElementRef`, `SectionForceState`, conectividad, procedencia y diagnósticos. No invoca ETABS, no crea `SectionDefinition` y no exige un catálogo ni un mapping de secciones de StructureLab. Puede recibir `element_ids_by_unique_name`; de lo contrario, el ID interno estable es `ETABS_FRAME_<UniqueName>` (o una codificación hexadecimal reversible para caracteres incompatibles con los IDs V2). `external_name` conserva `UniqueName`, mientras `external_section_name` conserva `Analysis Section` como **metadata externa únicamente**. `Label`, `Story`, `Design Type` y longitud quedan en metadata. `Label` nunca se usa como identidad global del frame. **ETABS identifica el objeto; StructureLab define posteriormente la sección definitiva.**

```python
from structurelab_pbd_rc.adapters.etabs import ETABSTablesAdapter

result = ETABSTablesAdapter().import_xlsx("export_etabs_mm_kn.xlsx")
```

La primera versión exige exactamente estas diez tablas; la resolución prioriza el título `TABLE: ...` dentro de la hoja y acepta pestañas abreviadas:

| Modelo y conectividad | Resultados |
|---|---|
| Program Control | Element Forces - Beams |
| Frame Assignments - Summary | Element Forces - Columns |
| Frame Assignments - Section Properties | |
| Frame Assignments - End Length Offsets | |
| Frame Assignments - Output Stations | |
| Beam Bays | |
| Column Bays | |
| Point Object Connectivity | |

Las filas de unidades de las columnas físicas deben declarar **`mm` para longitud, `kN` para fuerza y `kN-m` para momento/torsión**. Se verifican, entre otras, `Length`, offsets, espaciamientos, coordenadas de puntos, `Station`, `P`, `V2`, `V3`, `T`, `M2` y `M3`. Una unidad incorrecta o ausente provoca `ETABSImportError` con indicación de reexportar desde ETABS; el adaptador no convierte. `Program Control.CurrUnits` queda registrado y una discrepancia con las unidades **verificadas en las columnas** produce warning, pues describe una configuración del programa y no sustituye los encabezados dimensionales del archivo.

Los ejes locales ETABS `1, 2, 3` se asocian a los ejes neutrales `x, y, z` sin giro hacia ejes globales: `V2→Vy`, `V3→Vz`, `T→T`, `M2→My`, `M3→Mz`. La convención de **análisis** ETABS usa `P > 0` en tracción, mientras 1C exige `P > 0` en compresión; por eso **`P_StructureLab = −P_ETABS`**. El valor axial original y la fórmula quedan en `ProcessProvenance.resolved_configuration` de cada estado. La [referencia oficial de CSI para fuerzas internas](https://docs.csiamerica.com/help-files/sap/Output/Frame_Element_Internal_Forces_Output_Conventions.htm) describe la cara positiva, ejes y estaciones, y la [ayuda de interacción de ETABS](https://docs.csiamerica.com/help-files/etabs/Menus/Define/Section_Properties/Frame_Nonlinear_Hinge_Properties/Interaction_Surface_Definition.htm) explicita tracción positiva/compresión negativa en su convención de análisis. El mapping de nombres de componentes no implica equivalencia global de orientación entre programas.

La estación física ETABS se conserva en `station_etabs_mm` y se normaliza como `s = Station / Length`; `s=0` designa I y `s=1` J. No se exige que existan filas en ambos extremos. Se admite una discrepancia máxima de `max(10⁻⁶ mm, 10⁻⁹·Length)` al borde por redondeo y se limita solo el valor normalizado dentro de `[0,1]`, conservando el original. Se guardan longitud, offsets I/J, opción de offsets, `Output Stations` y espaciamiento para QA y trazabilidad, sin uso mecánico. `Beam Bays`, `Column Bays` y `Point Object Connectivity` conservan bay I/J, historia declarada, puntos y coordenadas. Un `Label` repetido no vincula el bay a un frame; `IEndStory=Below` tampoco se interpreta como un punto de la planta actual.

**Se importan todas las filas de fuerza.** `OutputCase` se ubica en `load_combination` si `CaseType=Combination`, y en `load_case` en otro caso; `CaseType`, `StepType` y `StepNum` originales permanecen en la procedencia de cada fila, junto con tabla, hoja, número de fila, `UniqueName`, versión ETABS y SHA-256 del XLSX. Así se conservan dos filas `Max`/`Min` de la misma combinación y estación. La identidad simple de `validate_section_force_states()` de 1C no incluye pasos; por eso el adaptador comprueba duplicados usando caso, tipo, paso, número de paso, estación y elemento ETABS, y **no** aplica ese helper a resultados ETABS multivaluados. `LinRespSpec / Max` produce un warning: los máximos por componente no se declaran simultáneos ni se selecciona una demanda gobernante.

Los errores de tablas/columnas obligatorias, unidades, `UniqueName` duplicado, longitud/estación inválida, fuerza no numérica, frame desconocido, tipo inconsistente y conflicto entre nombres de sección no vacíos de Summary y Section Properties impiden la importación. Si falta `Analysis Section`, el elemento se importa con `external_section_name=None` y un warning; no se infiere un nombre a partir de otra tabla. Los offsets/output stations faltantes, bays no vinculables y ausencia de filas de fuerza también se registran como warnings cuando los datos restantes siguen siendo trazables. `ETABSImportError.diagnostics` contiene códigos y ubicaciones; los warnings del resultado son diagnósticos estructurados.

El libro de referencia local `docs/modelo infromacion.xlsx` (SHA-256 `e427e82dca0ded2bbbc4f553b6965f744c31e6ed456f2093ae3def9c6559bc44`) se inspeccionó sin modificarlo. Declara `cm`, `kgf` y `kgf-cm` en sus tablas; **1D lo rechaza intencionalmente** y requiere reexportación. Las fixtures de tests reproducen su estructura de títulos, encabezados y filas con unidades estándar en un XLSX mínimo determinista; no recalculan ni alteran el libro original.

Quedan fuera: `ElementSectionAssignment`, catálogo de secciones, ETABS OAPI, escritura a ETABS, orientación global 2–3, creación automática de secciones o materiales, OpenSeesPy, fibras, `M-φ`, `P-M`, combinaciones PBSD, selección de demandas, rótulas y análisis estructural. `external_section_name` no declara una asignación definitiva: relacionar el elemento con un `section_id` del catálogo StructureLab corresponde a un subsegmento posterior. Los estados de respuesta espectral y envolventes conservan sus etiquetas sin validación de simultaneidad física.

**Verificación histórica 1D:** 37 pruebas nuevas de 1D y suite V1+V2 completa: **418 passed, 0 failed, 0 errors, 0 skipped**. Los 268 outputs históricos V1 conservaron los SHA-256 del manifiesto de línea base. La suite usó el ajuste temporal de permisos y nombres cortos de `tmp_path` requerido en este entorno Windows; no se modificó código productivo para resolver ese problema ambiental. 1D-R adapta el contrato y los tests para importar frames sin asignación de sección StructureLab.

**Verificación 1D-R:** suite V1+V2 completa: **420 passed, 0 failed, 0 errors, 0 skipped**. Los 268 outputs históricos V1 conservan sus hashes.
