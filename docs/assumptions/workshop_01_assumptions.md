# Supuestos del Taller 1

Fuente inicial: PDF `references/pdfs/ACTIVIDAD 1 CARACTERIZACIA_N MECA_NICA DE MATERIALES.pdf`.

## Datos base

- Columna cuadrada de 75 cm x 75 cm.
- Concreto con `f_c = 28 MPa`.
- Modulo elastico inicial del concreto: `E_c = 4700 * sqrt(f_c_mpa)`.
- Recubrimiento libre al fleje: 4.0 cm.
- Refuerzo longitudinal: 16 barras #7.
- Refuerzo transversal: flejes #4 cada 10 cm.
- Acero esperado: `fy = 470 MPa`.
- Modulo elastico del acero: `Es = 200000 MPa`.

## Supuestos abiertos

- Las dimensiones internas no explicitas se adoptan por simetria y se parametrizan en el YAML.
- El nucleo confinado se mide por defecto al eje del fleje: dimension exterior menos dos veces el recubrimiento libre y medio diametro de fleje por lado.
- Las 16 barras #7 se interpretan como una distribucion simetrica perimetral de 5 barras por lado, contando las esquinas en dos lados.
- Las ramas efectivas de flejes se toman como 2 en x y 2 en y, editable desde `base_section.geometry_assumptions`.
- La separacion libre de flejes para el factor de efectividad se adopta como `s_clear = s_center_to_center - tie_diameter`.
- Los parametros de deformacion ultima, endurecimiento y pandeo son editables.
- Las propiedades de malla electrosoldada se dejan en YAML/base interna para elegir diametro 4, 5 o 6 mm.

## Implementado

- Geometria bruta, nucleo confinado, area de acero longitudinal y cuantias.
- Cuantia volumetrica, factor de efectividad y presion lateral efectiva.
- Mander clasico y Mander ajustado.
- Curvas de acero en traccion, compresion sin pandeo y compresion con pandeo.
- Curva de malla electrosoldada.
- Metricas comparativas, CSV, XLSX, PNG, JSON y PDF minimo.

## Limitaciones y trazabilidad

- Attard-Setunge se implementa con la forma general `fcc * (As*x + Bs*x^2) / (1 + Cs*x + Ds*x^2)` y las ramas ascendente/descendente suministradas para concreto no confinado y confinado.
- El reporte PDF generado es minimo y automatico; una memoria de calculo completa queda como extension futura.
- Todos los datos del caso base deben modificarse desde `configs/workshops/workshop_01_material_characterization.yaml`, no desde el codigo.
