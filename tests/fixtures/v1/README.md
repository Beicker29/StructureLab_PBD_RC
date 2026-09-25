# Fixtures numéricas V1 — V2-004 a V2-006

Estas fixtures fijan los resultados de los dos YAML de amenaza, los cuatro JSON de materiales y el libro M–φ canónico con la implementación V1 posterior a V2-003R. Se generaron en una raíz temporal aislada; `outputs/stage_01`, `outputs/stage_02` y `outputs/stage_03` no se usaron como destino.

- `hazard/manifest.json`, `materials/manifest.json` y `sections/manifest.json` guardan inputs y SHA-256, unidades, convenciones de signo, estados, warnings, parámetros y métricas. Las rutas absolutas de la corrida se excluyen de esos contratos.
- Los subárboles `stage_01/`, `stage_02/` y `stage_03/` copian **solo datos científicos textuales**: CSV y TXT ETABS; además, YAML de parámetros/métricas de materiales y YAML de resultados seccionales. Se conserva el orden de filas y columnas, sin redondear valores.
- Cada archivo copiado tiene en su manifiesto un `sha256_lf`, calculado tras convertir CRLF a LF. Así se puede verificar contenido lógico en checkouts Windows con `core.autocrlf=true`. Para ETABS también se registran dos columnas, tabulador, cero encabezados y ocho decimales.
- Los XLSX generados no se duplican: su manifiesto registra hoja, columnas y filas, y se verificó que las celdas coinciden con CSV y con los XLSX históricos. Los JSON/YAML con rutas de corrida se representan mediante campos científicos normalizados y esquemas; los PNG/PDF figuran solo en el inventario de presentación, sin tratar su hash binario como oráculo numérico.

Las comparaciones de esta captura fueron exactas para CSV/YAML y campos estructurados bajo Python 3.12.10, NumPy 2.5.1 y Matplotlib 3.11.1. Los seis TXT ETABS históricos difieren solo en CRLF frente a LF del archivo recién generado; las líneas coinciden. La [suite completa posterior](../../../docs/migration/pytest_v2_004_006.log) aprobó 120/120 tests. El comportamiento histórico, incluidos `best_effort` y parámetros cíclicos sintéticos, se registra sin aprobarlo como modelo físico.

Estas fixtures son oráculos de compatibilidad V1, no pruebas de validez científica. Las tres memorias de [amenaza](../../../docs/migration/BASELINE_HAZARD_V2.md), [materiales](../../../docs/migration/BASELINE_MATERIALS_V2.md) y [secciones](../../../docs/migration/BASELINE_SECTIONS_V2.md) explican alcance y límites. Su integración en pruebas adicionales corresponde a tareas posteriores, no a V2-004–006.
