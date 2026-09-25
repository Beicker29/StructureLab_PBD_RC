# Tareas preparadas V2-001 a V2-009 — línea base V1

**Estado:** V2-001 a V2-009 ejecutadas; V2-003R se completó antes de V2-004. Las memorias de V2-004 a V2-006 están en [amenaza](migration/BASELINE_HAZARD_V2.md), [materiales](migration/BASELINE_MATERIALS_V2.md) y [secciones](migration/BASELINE_SECTIONS_V2.md), con fixtures bajo `tests/fixtures/v1/`. V2-007 a V2-009 se documentan en [interfaces](migration/BASELINE_INTERFACES_V2.md), [publicación](migration/BASELINE_PUBLICATION_V2.md) y [fronteras](migration/BASELINE_BOUNDARIES_V2.md). V2-010 y posteriores no se han ejecutado.  
**Referencia:** [plan de migración](MIGRATION_PLAN_V2.md), secciones 8 a 10.  
**Alcance:** congelar y validar los resultados actuales antes de mover código. Las Issues V2-010 y posteriores permanecen solo en el backlog del plan.

Cada ficha puede copiarse a un gestor de Issues cuando se decida usarlo. Los IDs son locales al plan; este archivo no crea Issues remotas. Registrar en cada entrega el entorno efectivo, los archivos añadidos y el resultado de la prueba. Los fallos por permisos y por el antiguo renderer Quarto permanecen en el registro histórico V2-003; V2-003R retiró ese renderer por decisión aprobada.

## V2-001 — Cerrar decisiones de arquitectura y alcance de la línea base

**Depende de:** revisión de este documento.  
**Objetivo:** dejar un registro único de decisiones adoptadas y pendientes antes de capturar fixtures.

**Trabajo previsto:**

1. Registrar como adoptados: módulos 00–12 con IDs semánticos; Stage 04 nativo por fibras con Excel de compatibilidad/benchmark; cinco funciones de Stage 05; modelo neutral anterior a adaptadores de Stage 06; separación normativa/probabilística de Stage 01; `references/` como biblioteca con catálogo previo a cualquier traslado.
2. Registrar como pendientes de decisión: namespace definitivo de configs y outputs V2, política `best_effort`, uso de modelos sintéticos en QA, periodo de compatibilidad V1 y backend concreto.
3. Fijar la frontera de línea base: dos casos espectrales, cuatro materiales constitutivos, libro M–φ canónico, interfaces CLI/imports, salidas y procedencia. El motor de fibras pertenece al desarrollo posterior.

**Entregable:** acta breve de decisiones enlazada desde `MIGRATION_PLAN_V2.md`; ninguna implementación.  
**Aceptación:** no quedan decisiones de numeración o alcance implícitas; los puntos pendientes tienen responsable o Issue posterior sin bloquear la captura V1.

## V2-002 — Congelar árbol efectivo, entorno y fuentes

**Depende de:** V2-001.  
**Objetivo:** identificar exactamente qué código, datos y herramientas generan la línea base.

**Trabajo previsto:**

1. Registrar commit y estado real del árbol, incluidos archivos no versionados relevantes. El hash leído de `.git/refs/heads/main` durante la revisión previa no basta para establecer el árbol efectivo.
2. Guardar hashes de los siete configs, dos Excel y de las referencias efectivamente citadas; verificar las 28 entradas iniciales de `references/catalog.yaml`, sin cambiar rutas.
3. Registrar Python, dependencias instaladas, SO, Matplotlib y versión/disponibilidad de Quarto/Typst. Identificar fuentes de variación numérica o visual.
4. Registrar inventario previo de `outputs/stage_01`, `stage_02` y `stage_03` sin ejecutar sobre ellos; usar una raíz nueva y aislada para futuras corridas.

**Entregable:** manifiesto de línea base con hashes, estado del árbol, entorno e inventario de salidas.  
**Aceptación:** cada input canónico tiene un identificador verificable; la ficha distingue fuentes originales, ejemplos y artefactos generados; ninguna fuente ni resultado histórico fue sobrescrito.

## V2-003 — Habilitar y repetir la suite V1 completa

**Depende de:** V2-002.  
**Objetivo:** eliminar el impedimento ambiental que dejó 16 tests sin ejecutar.

**Trabajo previsto:**

1. Reproducir el error de `tmp_path` con un directorio temporal verificablemente escribible y permisos adecuados; documentar la causa. El intento anterior bajo `.pytest_cache/` también fue denegado.
2. Ejecutar pytest con directorio temporal y configuración Matplotlib aislados, sin modificar código productivo ni `outputs/` históricos.
3. Registrar total recolectado, aprobados, fallidos, omitidos y errores. Mantener separadas las causas de preparación de los fallos de assertions.
4. Si el renderizador de amenaza requiere Quarto, registrar su disponibilidad y separar su prueba de integración de la suite puramente numérica.

**Entregable:** comando reproducible, log de suite y diagnóstico ambiental.  
**Aceptación:** los 120 casos observados en la revisión inicial pueden prepararse y ejecutarse; cualquier fallo funcional restante queda descrito con test, causa y Issue, sin afirmar una suite verde indebidamente.

## V2-004 — Congelar los dos casos de espectros y el formato ETABS

**Depende de:** V2-003 y V2-003R.  
**Objetivo:** disponer de oráculos numéricos y de artefactos para Stage 01 V1.

**Trabajo previsto:**

1. Ejecutar ambos YAML canónicos en una raíz de salida aislada.
2. Guardar vector de periodos, valores por nivel, factores/parámetros de transición, nombres de columnas, unidades, `stage_id`, `case_id` y rutas de artefactos.
3. Congelar los TXT ETABS: orden, ausencia de encabezado, delimitación y ocho decimales.
4. Congelar el esquema y contenido de YAML/JSON, CSV/XLSX y figuras que Stage 01 sigue produciendo; registrar explícitamente que nuevas corridas ya no generan QMD/PDF.

**Entregable:** fixtures de datos de los dos casos y nota de tolerancias/volatilidad.  
**Aceptación:** los espectros y TXT se reproducen en el entorno registrado; los valores SGC usados en el caso CCP-14 conservan su procedencia y no se reetiquetan como curvas probabilísticas completas.

## V2-005 — Congelar respuestas de los cuatro modelos de materiales

**Depende de:** V2-003.  
**Objetivo:** capturar el contrato científico y de archivos de Stage 02 V1.

**Trabajo previsto:**

1. Ejecutar juntos los cuatro JSON habilitados en una raíz aislada; registrar sus hashes y el par proyecto/caso resuelto.
2. Guardar para cada modelo filas de deformación, esfuerzo, tangente, rama, dominio, falla, inversión y warnings; parámetros calculados, métricas, notas de fuente y estado de calibración.
3. Incluir las dos condiciones de restricción RDM, el signo particular de Mander, la idealización efectiva Mon_MRO y la historia ordenada Cyc_MP.
4. Capturar esquema de CSV/XLSX/YAML/JSON y lista de figuras/PDF sin exigir igualdad binaria de imágenes.

**Entregable:** fixtures por modelo y comparación de resultados canónicos.  
**Aceptación:** todos los campos numéricos y semánticos críticos tienen valor esperado y tolerancia declarada; `Cyc_MP` conserva `synthetic_algorithm_verification_only`; la salida histórica no se altera.

## V2-006 — Congelar el libro M–φ canónico

**Depende de:** V2-003.  
**Objetivo:** preservar la importación e idealización existentes como compatibilidad futura de Stage 04.

**Trabajo previsto:**

1. Registrar hash, diez nombres exactos de hojas, orden, columnas detectadas y ramas por hoja de `M-curvatura.xlsx`.
2. Ejecutar el config actual en salida aislada. Capturar entradas resueltas, modo de `phi_u`, cortes configurados/auto y la salida `monotonica/` y `ciclica/` de cada hoja.
3. Comparar `Ke`, `My`, `phi_y`, `Mu`, `phi_u`, `Kp`, área real/bilineal, error, estado y advertencias, más esquema de CSV/JSON/YAML.
4. Registrar qué información geométrica, axial o material falta para comparar posteriormente con una sección por fibras. No declarar validación del motor futuro por coincidencia de formas.

**Entregable:** fixtures de las diez hojas y matriz de comparabilidad con el motor de fibras.  
**Aceptación:** todas las hojas y ramas esperadas están identificadas; la semántica heredada de `ciclica/` queda descrita como envolvente recortada cuando corresponda.

## V2-007 — Caracterizar CLI, imports y resolución de rutas V1

**Depende de:** V2-004 a V2-006.  
**Objetivo:** fijar interfaces públicas antes de introducir wrappers V2.

**Trabajo previsto:**

1. Registrar firmas y estructura de retorno de los tres `run()` y exports/imports públicos usados por tests y scripts.
2. Probar `scripts/run_stage_01.py`, `run_stage_02.py`, `run_stage_03.py`, `python -m` y entrypoints instalados con `--config` y `--output-root` en raíces temporales.
3. Probar rutas relativas desde la raíz y desde otro CWD, y rutas absolutas. Evitar una ejecución por defecto que escriba `outputs/` históricos.
4. Documentar el defecto conocido: scripts propagan argumentos; `main_stage_01/02/03()` no los propagan. La corrección corresponde a V2-026.

**Entregable:** matriz de interfaces y comportamientos observados, con tests de caracterización.  
**Aceptación:** cada diferencia entre invocaciones se reproduce y se conoce qué API debe conservar el adaptador V1.

## V2-008 — Caracterizar publicación y fallos V1

**Depende de:** V2-004 a V2-006.  
**Objetivo:** saber qué resultados persisten cuando una etapa falla a mitad de ejecución.

**Trabajo previsto:**

1. Crear únicamente árboles de salida temporales con archivos centinela de otros casos y otras etapas.
2. Inyectar fallos controlados antes de escribir, a mitad de cálculo/render y durante promoción donde aplique. Registrar inventario y hash antes/después.
3. Verificar por separado amenaza (borra caso activo), materiales (temporal/respaldo/reemplazo de toda la etapa) y secciones (borrado previo del árbol).
4. Documentar rollback real y límites de aislamiento en Windows, sin reparar las políticas heredadas en esta Issue.

**Entregable:** matriz por etapa y punto de fallo, más tests de caracterización sobre temporales.  
**Aceptación:** se conoce qué archivos sobreviven, se pierden o quedan parciales; ninguna prueba toca salidas históricas ni pretende que la publicación V1 sea ya segura por caso.

## V2-009 — Completar tests de fronteras de datos y algoritmos actuales

**Depende de:** V2-005 y V2-006; usa los oráculos de V2-004 y hallazgos de V2-007/008 cuando correspondan.  
**Objetivo:** cubrir entradas y estados límite antes de extraer lógica.

**Trabajo previsto:**

1. Ejercitar el motor compartido de energía con origen ausente, puntos repetidos, NaN/Inf, área nula, ablandamiento, meseta, ausencia de candidato y `best_effort`.
2. Ejercitar signos/unidades y fronteras de Mander, RDM, Mon_MRO y Cyc_MP, incluyendo historia repetida, trial/commit/revert/reset y dos instancias independientes.
3. Probar XLSX independiente del writer: shared/inline strings, blancos, columnas amplias, hoja ausente y valor cacheado de fórmula, sin atribuir al lector recálculo de Excel.
4. Probar identificadores, colisiones case-insensitive, saneamiento de nombres de hojas, rutas relativas y protecciones de salida. Registrar las diferencias V1 encontradas como defectos separados.

**Entregable:** tests y lista de casos límite con comportamiento observado y esperado.  
**Aceptación:** los casos límite relevantes para mover los tres flujos están documentados; ningún xfail general oculta una regresión; los cambios científicos o de validación se posponen a Issues específicas.

## Puerta de cierre de la línea base

V2-001 a V2-009 se consideran completas solo con manifiesto de entorno/inputs, fixtures de los dos espectros, cuatro materiales y libro M–φ, caracterización de interfaces y fallos, y suite reproducible sin errores de preparación. La etapa 04 nativa, la amenaza probabilística, las cinco funciones de 05 y los adaptadores de 06 comienzan después, con sus contratos y validaciones propios.
