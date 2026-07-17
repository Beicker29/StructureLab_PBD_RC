# Etapa 1: Amenaza

La Etapa 1 agrupa los calculos de amenaza. La implementacion inicial cubre amenaza sismica, pero la estructura se deja preparada para incorporar otras amenazas en el futuro.

## Configuracion

Cada caso vive en `configs/stage_01/` y usa esta organizacion:

```yaml
hazard:
  seismic:
    source: ...
    period_range: ...
```

Los casos disponibles son:

- `case_01_nsr10`: espectro NSR-10 de 475 anos escalado para niveles de amenaza de 31, 475 y 2500 anos.
- `case_02_sgc_ccp14`: valores SGC independientes por periodo de retorno, factores de sitio calculados por interpolacion tabular y forma espectral CCP-14.

El caso SGC + CCP-14 no inventa valores faltantes. Si `PGA`, `Sa_0_2` o `Sa_1_0` estan vacios, el workflow se detiene y pide completar esos datos. Los factores `Fpga`, `Fa` y `Fv` se calculan desde las tablas CCP-14 para perfiles `A` a `E`; el perfil `F` queda bloqueado porque requiere estudio especifico.

Para mantener el mismo formato de amenaza que NSR-10, CCP-14 organiza sus valores por nivel:

```yaml
hazard_levels:
  service: ...
  design: ...
  maximum_considered: ...
```

## Mecanica

Las ecuaciones del espectro viven en `mechanics/hazard/seismic/spectra.py`. El workflow de la etapa vive en `design/stages/stage_01_hazard.py` y solo orquesta:

- lectura del YAML;
- validacion de campos;
- calculo de parametros;
- generacion de tablas;
- generacion de graficas;
- escritura de reportes YAML y JSON.

## Salidas

Los resultados se escriben bajo dos subcarpetas principales de `outputs/stage_01/`:

- `nsr10_spectra/`: espectros, parametros, figura y reporte del caso NSR-10.
- `ccp14_spectra/`: espectros, parametros, figura y reporte del caso SGC + CCP-14.

Cada subcarpeta conserva internamente la misma organizacion:

- `data/`: tablas y JSON resumen del caso ejecutado.
- `figures/`: grafica comparativa y una grafica individual por nivel de amenaza con puntos notables.
- `reports/`: YAML del caso ejecutado.
